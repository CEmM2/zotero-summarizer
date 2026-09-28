"""Tests for the llm module."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from zsum.config import (
    CodexExecConfig,
    Config,
    GeminiCliConfig,
    LLMConfig,
    LLMProviderConfig,
    LLMRoutingConfig,
)
from zsum.llm import (
    AnthropicCliError,
    CodexExecError,
    GeminiCliError,
    LLMResponse,
    LLMRetryExhausted,
    complete,
    complete_with_retry,
)


class TestComplete:
    def test_unknown_provider_raises(self):
        config = Config(llm=LLMConfig(provider="unknown"))
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            complete("sys", "user", config)

    @patch("zsum.llm.subprocess.run")
    def test_anthropic_dispatch(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "result": "response text",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                }
            ),
            stderr="",
        )

        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                anthropic=LLMProviderConfig(model="test-model"),
            )
        )

        result = complete("system", "user", config, stage="cards")

        assert result.text == "response text"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        cmd = mock_run.call_args.args[0]
        assert cmd[:2] == ["claude", "--print"]
        assert "--output-format" in cmd
        assert cmd[cmd.index("--output-format") + 1] == "json"
        assert "--system-prompt" in cmd
        assert cmd[cmd.index("--system-prompt") + 1] == "system"
        assert "--model" in cmd
        assert cmd[cmd.index("--model") + 1] == "test-model"

    @patch("zsum.llm.subprocess.run")
    def test_anthropic_tolerates_stdout_noise(self, mock_run):
        """Ensure Claude path uses the same balanced-brace JSON walker as Gemini."""
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=(
                "WARN: update notification\n"
                + json.dumps(
                    {
                        "result": "noisy response",
                        "usage": {"input_tokens": 7, "output_tokens": 3},
                    }
                )
            ),
            stderr="",
        )
        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                anthropic=LLMProviderConfig(model="test-model"),
            )
        )

        result = complete("system", "user", config, stage="cards")

        assert result.text == "noisy response"
        assert result.input_tokens == 7
        assert result.output_tokens == 3

    @patch("zsum.llm.subprocess.run")
    def test_anthropic_raises_status_error(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr='{"error":{"status":429,"message":"rate limited"}}',
        )
        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                anthropic=LLMProviderConfig(model="test-model"),
            )
        )

        with pytest.raises(AnthropicCliError, match="exit code 1") as exc_info:
            complete("system", "user", config, stage="cards")

        assert exc_info.value.status_code == 429

    @patch("zsum.llm._get_openai_client")
    def test_openai_compat_dispatch(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="compat response"))]
        mock_response.usage.prompt_tokens = 80
        mock_response.usage.completion_tokens = 40
        mock_client.chat.completions.create.return_value = mock_response

        config = Config(
            llm=LLMConfig(
                provider="openai_compat",
                openai_compat=LLMProviderConfig(model="local-model"),
            )
        )

        result = complete("system", "user", config, stage="cards")
        assert result.text == "compat response"

    @patch("zsum.llm.subprocess.run")
    def test_codex_exec_dispatch(self, mock_run):
        def _fake_run(cmd, input, text, capture_output, cwd, check):
            output_path = Path(cmd[cmd.index("-o") + 1])
            output_path.write_text("structured response", encoding="utf-8")
            stdout = "\n".join(
                [
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {"type": "agent_message", "text": "structured response"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn.completed",
                            "usage": {"input_tokens": 12, "output_tokens": 5},
                        }
                    ),
                ]
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        mock_run.side_effect = _fake_run
        config = Config(
            llm=LLMConfig(
                provider="codex_exec",
                codex_exec=CodexExecConfig(model="gpt-5.4"),
            )
        )

        result = complete("system", "user", config, stage="digests")

        assert result.text == "structured response"
        assert result.input_tokens == 12
        assert result.output_tokens == 5
        cmd = mock_run.call_args.args[0]
        assert cmd[:2] == ["codex", "exec"]
        assert "--json" in cmd
        assert "-m" in cmd

    @patch("zsum.llm.subprocess.run")
    @patch("zsum.llm._get_openai_client")
    def test_stage_argument_selects_routed_provider(self, mock_get_client, mock_run):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        compat_response = MagicMock()
        compat_response.choices = [MagicMock(message=MagicMock(content="compat response"))]
        compat_response.usage.prompt_tokens = 80
        compat_response.usage.completion_tokens = 40
        mock_client.chat.completions.create.return_value = compat_response

        def _fake_run(cmd, input, text, capture_output, cwd, check):
            output_path = Path(cmd[cmd.index("-o") + 1])
            output_path.write_text("structured response", encoding="utf-8")
            stdout = "\n".join(
                [
                    json.dumps(
                        {
                            "type": "item.completed",
                            "item": {"type": "agent_message", "text": "structured response"},
                        }
                    ),
                    json.dumps(
                        {
                            "type": "turn.completed",
                            "usage": {"input_tokens": 12, "output_tokens": 5},
                        }
                    ),
                ]
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        mock_run.side_effect = _fake_run
        config = Config(
            llm=LLMConfig(
                provider="anthropic",
                routing=LLMRoutingConfig(cards="openai_compat", digests="codex_exec"),
                openai_compat=LLMProviderConfig(model="local-model"),
                codex_exec=CodexExecConfig(model="gpt-5.4"),
            )
        )

        cards_result = complete("system", "user", config, stage="cards")
        digests_result = complete("system", "user", config, stage="digests")

        assert cards_result.text == "compat response"
        assert digests_result.text == "structured response"
        mock_get_client.assert_called_once()
        assert mock_run.call_count == 1

    @patch("zsum.llm.subprocess.run")
    def test_gemini_cli_dispatch(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=0,
            stdout=(
                "Skill conflict detected: noise prepended to stdout"
                + json.dumps(
                    {
                        "session_id": "abc",
                        "response": "gemini answer",
                        "stats": {
                            "models": {
                                "gemini-2.5-flash-lite": {
                                    "tokens": {"input": 100, "candidates": 20}
                                },
                                "gemini-3-flash-preview": {
                                    "tokens": {"input": 200, "candidates": 30}
                                },
                            }
                        },
                    }
                )
            ),
            stderr="",
        )
        config = Config(
            llm=LLMConfig(
                provider="gemini_cli",
                gemini_cli=GeminiCliConfig(model="gemini-3-pro"),
            )
        )

        result = complete("system", "user", config, stage="cards")

        assert result.text == "gemini answer"
        # Tokens summed across models
        assert result.input_tokens == 300
        assert result.output_tokens == 50
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "gemini"
        assert cmd[1] == "-p"
        assert cmd[2] == ""
        assert "-o" in cmd
        assert cmd[cmd.index("-o") + 1] == "json"
        assert "-m" in cmd
        assert cmd[cmd.index("-m") + 1] == "gemini-3-pro"
        assert "--approval-mode" in cmd

    @patch("zsum.llm.subprocess.run")
    def test_gemini_cli_raises_status_error(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=1,
            stdout="",
            stderr='{"error":{"status":429,"message":"quota exceeded"}}',
        )
        config = Config(
            llm=LLMConfig(
                provider="gemini_cli",
                gemini_cli=GeminiCliConfig(model="gemini-3-pro"),
            )
        )

        with pytest.raises(GeminiCliError, match="exit code 1") as exc_info:
            complete("system", "user", config, stage="cards")

        assert exc_info.value.status_code == 429

    @patch("zsum.llm.subprocess.run")
    def test_codex_exec_raises_status_error(self, mock_run):
        mock_run.return_value = SimpleNamespace(
            returncode=1,
            stdout='{"type":"error","status":400,"error":{"message":"bad request"}}',
            stderr="",
        )
        config = Config(
            llm=LLMConfig(
                provider="codex_exec",
                codex_exec=CodexExecConfig(model="gpt-5.4"),
            )
        )

        with pytest.raises(CodexExecError, match="exit code 1") as exc_info:
            complete("system", "user", config, stage="cards")

        assert exc_info.value.status_code == 400


class TestCompleteWithRetry:
    @patch("zsum.llm.complete")
    def test_retries_on_failure(self, mock_complete):
        mock_complete.side_effect = [
            RuntimeError("fail 1"),
            RuntimeError("fail 2"),
            LLMResponse(text="ok", model="test", input_tokens=10, output_tokens=5),
        ]
        config = Config()
        result = complete_with_retry("sys", "user", config, max_retries=3, base_delay=0.01)
        assert result.text == "ok"
        assert mock_complete.call_count == 3

    @patch("zsum.llm.complete")
    def test_raises_after_max_retries(self, mock_complete):
        root_error = RuntimeError("always fails")
        mock_complete.side_effect = root_error
        config = Config()
        with pytest.raises(LLMRetryExhausted) as exc_info:
            complete_with_retry("sys", "user", config, max_retries=2, base_delay=0.01)
        assert exc_info.value.attempts == 2
        assert exc_info.value.last_error is root_error
        assert "failed after 2 attempts" in str(exc_info.value)
