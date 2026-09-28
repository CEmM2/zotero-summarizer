"""LLM provider dispatch: Claude Code CLI, OpenAI-compatible endpoints, Codex CLI."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import ValidationError as PydanticValidationError

from .config import CodexExecConfig, Config, GeminiCliConfig, LLMProviderConfig, LLMStage

logger = logging.getLogger(__name__)


class LLMRetryExhausted(RuntimeError):
    """Raised when LLM retry limit is exhausted."""

    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"LLM call failed after {attempts} attempts: {last_error}")


class CodexExecError(RuntimeError):
    """Raised when a Codex CLI invocation fails."""

    def __init__(self, message: str, *, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class AnthropicCliError(RuntimeError):
    """Raised when a Claude Code CLI (`claude -p`) invocation fails."""

    def __init__(self, message: str, *, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


class GeminiCliError(RuntimeError):
    """Raised when a Gemini CLI (`gemini -p`) invocation fails."""

    def __init__(self, message: str, *, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message)


_openai_client = None


def _reset_clients() -> None:
    """Reset cached clients. Useful for testing and library usage with changing configs."""
    global _openai_client
    _openai_client = None


@dataclass
class LLMResponse:
    """Wrapper for LLM completion response."""

    text: str
    model: str
    input_tokens: int
    output_tokens: int


def complete(
    system_prompt: str,
    user_prompt: str,
    config: Config,
    *,
    stage: LLMStage = "cards",
    max_tokens: int | None = None,
    output_schema: dict | None = None,
) -> LLMResponse:
    """Send a completion request to the configured LLM provider."""
    provider = config.llm.provider_for_stage(stage)
    if provider == "anthropic":
        return _complete_anthropic(
            system_prompt,
            user_prompt,
            config,
            stage,
            max_tokens,
            output_schema=output_schema,
        )
    elif provider == "openai_compat":
        return _complete_openai_compat(
            system_prompt,
            user_prompt,
            config,
            stage,
            max_tokens,
            output_schema=output_schema,
        )
    elif provider == "codex_exec":
        return _complete_codex_exec(
            system_prompt,
            user_prompt,
            config,
            stage,
            max_tokens,
            output_schema=output_schema,
        )
    elif provider == "gemini_cli":
        return _complete_gemini_cli(
            system_prompt,
            user_prompt,
            config,
            stage,
            max_tokens,
            output_schema=output_schema,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def _get_openai_client(config: Config):  # noqa: ANN201 – returns openai.OpenAI
    """Return a cached OpenAI-compatible client, creating one on first call."""
    global _openai_client
    if _openai_client is None:
        import openai

        prov = config.llm.openai_compat
        _openai_client = openai.OpenAI(
            base_url=prov.base_url,
            api_key=prov.api_key,
        )
    return _openai_client


def _extract_cli_status_code(text: str) -> int | None:
    """Best-effort extraction of an HTTP-style status code from CLI output.

    Shared between the Claude Code (`claude -p`) and Gemini (`gemini -p`)
    error paths. Both surface HTTP statuses through error envelopes that
    match `"status":NNN` or `"status_code":NNN`, and both produce the same
    network-failure phrasings on stderr.
    """
    match = re.search(r'"status(?:_code)?"\s*:\s*(\d{3})', text)
    if match:
        return int(match.group(1))
    if any(
        needle in text
        for needle in (
            "Could not resolve host",
            "stream disconnected before completion",
            "timed out",
            "Temporary failure",
            "ECONNRESET",
            "ETIMEDOUT",
        )
    ):
        return 503
    return None


def _complete_anthropic(
    system_prompt: str,
    user_prompt: str,
    config: Config,
    stage: LLMStage,
    max_tokens: int | None,
    *,
    output_schema: dict | None = None,
) -> LLMResponse:
    """Call Claude Code CLI (`claude -p`) non-interactively and parse its JSON output."""
    prov = cast(LLMProviderConfig, config.llm.config_for_stage(stage))
    max_tok = max_tokens or prov.max_tokens_card

    user_payload = user_prompt
    if max_tok:
        user_payload = f"{user_prompt}\n\nKeep the output within roughly {max_tok} tokens."

    with tempfile.TemporaryDirectory(prefix="zsum-claude-cli-") as tmpdir:
        run_dir = Path(tmpdir)
        # Use long form `--print` (boolean) to avoid any chance of an argv parser
        # treating the next flag as a value. `claude -p` and `claude --print` are
        # equivalent per `claude --help`.
        cmd = [
            prov.binary,
            "--print",
            "--output-format",
            "json",
            "--system-prompt",
            system_prompt,
            "--setting-sources",
            "",
            "--disable-slash-commands",
            "--tools",
            "",
            "--strict-mcp-config",
        ]
        if prov.model:
            cmd.extend(["--model", prov.model])
        if output_schema is not None:
            cmd.extend(["--json-schema", json.dumps(output_schema)])
        try:
            result = subprocess.run(
                cmd,
                input=user_payload,
                text=True,
                capture_output=True,
                cwd=run_dir,
                check=False,
            )
        except FileNotFoundError as e:
            # Map "binary missing" to a fatal status (404 -> not retryable)
            # so the user sees a clean error instead of a Python traceback.
            raise AnthropicCliError(
                f"claude CLI binary not found: {prov.binary!r}. "
                "Install Claude Code (https://claude.com/claude-code) and "
                "ensure it is on PATH, or set llm.anthropic.binary in config.yaml.",
                status_code=404,
            ) from e
        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if result.returncode != 0:
            status_code = _extract_cli_status_code(combined_output)
            detail = combined_output.strip().splitlines()[-1] if combined_output.strip() else ""
            raise AnthropicCliError(
                f"claude CLI failed with exit code {result.returncode}: {detail}",
                status_code=status_code,
            )

        # Use the same noise-tolerant brace walker as the Gemini path; future
        # versions of `claude -p` could prepend update notices or warnings to
        # stdout, and naive json.loads would silently break.
        payload = _extract_last_json_object(result.stdout)
        if payload is None:
            raise AnthropicCliError(
                "claude CLI returned no parseable JSON object",
                status_code=502,
            )

        text = str(payload.get("result") or "").strip()
        if not text:
            raise AnthropicCliError("claude CLI returned no result text", status_code=502)

        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return LLMResponse(
            text=text,
            model=prov.model or "claude-cli-default",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _complete_openai_compat(
    system_prompt: str,
    user_prompt: str,
    config: Config,
    stage: LLMStage,
    max_tokens: int | None,
    *,
    output_schema: dict | None = None,
) -> LLMResponse:
    """Call OpenAI-compatible endpoint (LM Studio, mlx-lm serve, Ollama, etc.)."""
    prov = cast(LLMProviderConfig, config.llm.config_for_stage(stage))
    client = _get_openai_client(config)
    max_tok = max_tokens or prov.max_tokens_card

    using_structured = output_schema is not None and prov.structured_output
    kwargs: dict = dict(
        model=prov.model,
        max_tokens=max_tok,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    # Sampling parameters — only include when explicitly set in config.
    if prov.temperature is not None:
        kwargs["temperature"] = prov.temperature
    if prov.top_p is not None:
        kwargs["top_p"] = prov.top_p
    if prov.seed is not None:
        kwargs["seed"] = prov.seed
    # top_k is not part of the OpenAI API spec but LM Studio and vLLM
    # accept it via extra_body.
    extra_body: dict = {}
    if prov.enable_thinking is not None:
        extra_body["enable_thinking"] = prov.enable_thinking
    if prov.top_k is not None:
        extra_body["top_k"] = prov.top_k
    if extra_body:
        kwargs["extra_body"] = extra_body
    if using_structured:
        # Use the OpenAI response_format API for schema-validated JSON output.
        # Compatible with LM Studio, vLLM, and other servers that implement the
        # structured output extension of the OpenAI chat completions API.
        schema_name = (
            output_schema.get("title", "response") if output_schema is not None else "response"
        )
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": output_schema,
            },
        }

    # --- Debug: log the request ---
    logger.debug(
        "OpenAI-compat request: model=%s, max_tokens=%s, structured_output=%s, "
        "response_format=%s, extra_body=%s",
        prov.model,
        kwargs.get("max_tokens"),
        prov.structured_output,
        kwargs.get("response_format", {}).get("type", "none"),
        kwargs.get("extra_body"),
    )
    if output_schema is not None and not prov.structured_output:
        logger.debug(
            "output_schema was provided but structured_output=false in config — "
            "schema NOT sent to server"
        )

    response = client.chat.completions.create(**kwargs)

    # --- Debug: log the raw response ---
    msg = response.choices[0].message
    reasoning = getattr(msg, "reasoning_content", None)
    finish = response.choices[0].finish_reason
    logger.debug(
        "OpenAI-compat response: finish_reason=%s, content_len=%d, "
        "has_reasoning=%s, reasoning_len=%d",
        finish,
        len(msg.content or ""),
        reasoning is not None,
        len(reasoning or ""),
    )
    if reasoning:
        logger.debug("Reasoning (first 300 chars): %s", reasoning[:300])

    text = msg.content or ""
    if not text and reasoning:
        # Thinking models (Qwen3, DeepSeek-R1) with enable_thinking may route
        # the entire useful response into reasoning_content instead of content,
        # both for structured JSON and plain-text / markdown outputs.
        # Recover the response from reasoning_content in all cases.
        label = "Structured output" if using_structured else "Response text"
        logger.info(
            "%s found in reasoning_content (%d chars) — using as response text.",
            label,
            len(reasoning),
        )
        text = reasoning
    usage = response.usage
    return LLMResponse(
        text=text,
        model=prov.model,
        input_tokens=usage.prompt_tokens if usage else 0,
        output_tokens=usage.completion_tokens if usage else 0,
    )


def _combine_codex_exec_prompt(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int | None,
    *,
    structured_output: bool,
) -> str:
    """Build a single prompt for Codex CLI from the system and user prompts."""
    parts = [
        "You are generating content for zotero-summarizer.",
        "Answer using only the provided prompt content.",
        "Do not inspect local files, run commands, or use any tools.",
    ]
    if structured_output:
        parts.append("Return only schema-valid JSON with no surrounding commentary.")
    else:
        parts.append("Return only the requested final answer with no preamble or commentary.")
    if max_tokens:
        parts.append(f"Keep the output within roughly {max_tokens} tokens.")
    parts.extend(
        [
            "",
            "<system_prompt>",
            system_prompt,
            "</system_prompt>",
            "",
            "<user_prompt>",
            user_prompt,
            "</user_prompt>",
        ]
    )
    return "\n".join(parts)


def _extract_codex_usage(stdout: str) -> tuple[int, int]:
    """Return input/output token counts from Codex JSONL output."""
    input_tokens = output_tokens = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "turn.completed":
            continue
        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
    return input_tokens, output_tokens


def _extract_codex_last_message(stdout: str) -> str:
    """Return the final agent message from Codex JSONL output."""
    final_text = ""
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "item.completed":
            continue
        item = payload.get("item") or {}
        if item.get("type") == "agent_message":
            final_text = str(item.get("text") or "")
    return final_text


def _extract_codex_status_code(text: str) -> int | None:
    """Best-effort extraction of an HTTP-style status code from Codex output."""
    match = re.search(r'"status"\s*:\s*(\d{3})', text)
    if match:
        return int(match.group(1))
    if any(
        needle in text
        for needle in (
            "Could not resolve host",
            "stream disconnected before completion",
            "timed out",
            "Temporary failure",
        )
    ):
        return 503
    return None


def _complete_codex_exec(
    system_prompt: str,
    user_prompt: str,
    config: Config,
    stage: LLMStage,
    max_tokens: int | None,
    *,
    output_schema: dict | None = None,
) -> LLMResponse:
    """Call Codex CLI non-interactively and parse its JSONL output."""
    prov = cast(CodexExecConfig, config.llm.config_for_stage(stage))
    prompt = _combine_codex_exec_prompt(
        system_prompt,
        user_prompt,
        max_tokens,
        structured_output=output_schema is not None,
    )
    with tempfile.TemporaryDirectory(prefix="zsum-codex-exec-") as tmpdir:
        run_dir = Path(tmpdir)
        last_message_path = run_dir / "last-message.txt"
        cmd = [
            prov.binary,
            "exec",
            "--sandbox",
            prov.sandbox,
            "--skip-git-repo-check",
            "--ephemeral",
            "--json",
            "-o",
            str(last_message_path),
        ]
        if prov.model:
            cmd.extend(["-m", prov.model])
        if output_schema is not None:
            schema_path = run_dir / "output-schema.json"
            schema_path.write_text(json.dumps(output_schema), encoding="utf-8")
            cmd.extend(["--output-schema", str(schema_path)])
        cmd.append("-")
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                cwd=run_dir,
                check=False,
            )
        except FileNotFoundError:
            raise
        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if result.returncode != 0:
            status_code = _extract_codex_status_code(combined_output)
            detail = combined_output.strip().splitlines()[-1] if combined_output.strip() else ""
            raise CodexExecError(
                f"Codex CLI failed with exit code {result.returncode}: {detail}",
                status_code=status_code,
            )
        text = ""
        if last_message_path.exists():
            text = last_message_path.read_text(encoding="utf-8").strip()
        if not text:
            text = _extract_codex_last_message(result.stdout).strip()
        if not text:
            raise CodexExecError("Codex CLI returned no final message", status_code=502)
        input_tokens, output_tokens = _extract_codex_usage(result.stdout)
        return LLMResponse(
            text=text,
            model=prov.model or "codex-exec-default",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def _extract_last_json_object(text: str) -> dict | None:
    """Return the last balanced top-level JSON object in *text*, or None.

    Gemini CLI prepends startup notices (skill conflicts, MCP warnings) to stdout
    before the JSON payload, so naive json.loads(stdout) fails. This walks the
    string once tracking brace depth (string-aware) to recover the final object.
    """
    starts: list[int] = []
    candidates: list[tuple[int, int]] = []
    depth = 0
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                starts.append(i)
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and starts:
                candidates.append((starts.pop(), i + 1))
    for start, end in reversed(candidates):
        try:
            obj = json.loads(text[start:end])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _sum_gemini_token_field(stats: dict, field_name: str) -> int:
    """Sum tokens.<field> across stats.models.*.tokens (gemini emits per-model)."""
    total = 0
    models = (stats or {}).get("models") or {}
    for model_stats in models.values():
        tokens = (model_stats or {}).get("tokens") or {}
        try:
            total += int(tokens.get(field_name, 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def _complete_gemini_cli(
    system_prompt: str,
    user_prompt: str,
    config: Config,
    stage: LLMStage,
    max_tokens: int | None,
    *,
    output_schema: dict | None = None,
) -> LLMResponse:
    """Call Gemini CLI (`gemini -p`) non-interactively and parse its JSON output.

    Gemini CLI has no --system-prompt or --json-schema flags, so we combine the
    system + user prompts (codex_exec style) and inline schema instructions.
    """
    prov = cast(GeminiCliConfig, config.llm.config_for_stage(stage))
    prompt = _combine_codex_exec_prompt(
        system_prompt,
        user_prompt,
        max_tokens,
        structured_output=output_schema is not None,
    )
    if output_schema is not None:
        prompt = f"{prompt}\n\n<output_schema>\n{json.dumps(output_schema)}\n</output_schema>"
    with tempfile.TemporaryDirectory(prefix="zsum-gemini-cli-") as tmpdir:
        run_dir = Path(tmpdir)
        cmd = [
            prov.binary,
            "-p",
            "",
            "-o",
            "json",
            "--approval-mode",
            prov.approval_mode,
        ]
        if prov.model:
            cmd.extend(["-m", prov.model])
        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                text=True,
                capture_output=True,
                cwd=run_dir,
                check=False,
            )
        except FileNotFoundError as e:
            raise GeminiCliError(
                f"gemini CLI binary not found: {prov.binary!r}. "
                "Install Gemini CLI (https://github.com/google-gemini/gemini-cli) "
                "and ensure it is on PATH, or set llm.gemini_cli.binary in config.yaml.",
                status_code=404,
            ) from e
        combined_output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        if result.returncode != 0:
            status_code = _extract_cli_status_code(combined_output)
            detail = combined_output.strip().splitlines()[-1] if combined_output.strip() else ""
            raise GeminiCliError(
                f"gemini CLI failed with exit code {result.returncode}: {detail}",
                status_code=status_code,
            )

        payload = _extract_last_json_object(result.stdout)
        if payload is None:
            raise GeminiCliError(
                "gemini CLI returned no parseable JSON object",
                status_code=502,
            )

        text = str(payload.get("response") or "").strip()
        if not text:
            raise GeminiCliError("gemini CLI returned empty response", status_code=502)

        stats = payload.get("stats") or {}
        input_tokens = _sum_gemini_token_field(stats, "input")
        output_tokens = _sum_gemini_token_field(stats, "candidates")
        return LLMResponse(
            text=text,
            model=prov.model or "gemini-cli-default",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_FATAL_STATUS_CODES = frozenset({400, 401, 403, 404, 422})

# Python built-in network/IO errors that are always transient
_TRANSIENT_BUILTIN = (
    ConnectionError,
    TimeoutError,
)

# Python built-in errors that indicate a configuration/logic problem (fatal)
_FATAL_BUILTIN = (
    ValueError,
    TypeError,
    AttributeError,
    NotImplementedError,
    OSError,
    FileNotFoundError,
    PermissionError,
    KeyError,
    IndexError,
    json.JSONDecodeError,
    PydanticValidationError,
)


def _is_transient(exc: Exception) -> bool:
    """Return True if *exc* is a transient error that should be retried.

    Classification rules (in priority order):
    1. If the exception has a ``status_code`` attribute, use the HTTP status code:
       - 429, 5xx  → transient (rate-limit / server error)
       - 400, 401, 403, 404, 422 → fatal (auth / bad config / not found)
       - anything else with a status_code → transient (unknown, err on retry side)
       Both Anthropic and OpenAI SDK exceptions always carry ``status_code``
       (inherited from ``APIStatusError``), so this rule handles all SDK errors.
    2. Python built-in types: ConnectionError, TimeoutError → transient
    3. Python built-in types: OSError (and subclasses FileNotFoundError,
       PermissionError), ValueError, TypeError, KeyError, IndexError,
       json.JSONDecodeError, pydantic.ValidationError → fatal
    4. Everything else (unknown) → transient (backward-compatible default)
    """
    # --- 1. HTTP status_code attribute (works for both Anthropic and OpenAI SDKs) ---
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        if status_code in _TRANSIENT_STATUS_CODES:
            return True
        # Unknown status code also defaults to transient
        return status_code not in _FATAL_STATUS_CODES

    # --- 2 & 3. Python built-ins ---
    if isinstance(exc, _TRANSIENT_BUILTIN):
        return True
    # --- 4. Default: unknown exceptions are treated as transient ---
    return not isinstance(exc, _FATAL_BUILTIN)


def complete_with_retry(
    system_prompt: str,
    user_prompt: str,
    config: Config,
    *,
    stage: LLMStage = "cards",
    max_tokens: int | None = None,
    max_retries: int = 3,
    base_delay: float = 2.0,
    output_schema: dict | None = None,
) -> LLMResponse:
    """Complete with exponential backoff retry on transient failures.

    Fatal errors (auth, bad config, model not found) are re-raised immediately
    without consuming retry attempts.  Transient errors (timeouts, 429, 5xx) are
    retried up to *max_retries* times with exponential backoff.
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            if output_schema is None:
                return complete(
                    system_prompt,
                    user_prompt,
                    config,
                    stage=stage,
                    max_tokens=max_tokens,
                )
            return complete(
                system_prompt,
                user_prompt,
                config,
                stage=stage,
                max_tokens=max_tokens,
                output_schema=output_schema,
            )
        except Exception as e:
            if not _is_transient(e):
                logger.error("LLM call failed with fatal error (no retry): %s", e)
                raise

            last_error = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s. Retrying in %.1fs",
                    attempt + 1,
                    max_retries,
                    e,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error("LLM call failed after %d attempts: %s", max_retries, e)

    raise LLMRetryExhausted(
        last_error=cast(Exception, last_error),
        attempts=max_retries,
    ) from last_error
