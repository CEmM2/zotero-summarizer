"""Configuration loading and validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)


@dataclass
class LLMProviderConfig:
    """Settings for a single LLM provider."""

    model: str = ""
    max_tokens_card: int = 1024
    max_tokens_digest: int = 2048
    # Anthropic path now shells out to `claude -p`. `api_key_env` is retained so
    # legacy config files don't trigger unknown-key warnings, but is unused.
    api_key_env: str = "ANTHROPIC_API_KEY"
    # Path/name of the `claude` Code CLI binary. Used by the anthropic provider only.
    binary: str = "claude"
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "lm-studio"
    # Set to False to disable extended thinking for Qwen3/DeepSeek-R1 models via
    # LM Studio or similar.  When False, passed as extra_body={"enable_thinking": False}.
    # Leave as None (the default) to let the server decide.
    enable_thinking: bool | None = None
    # Enable JSON Schema structured output via the OpenAI response_format API.
    # Requires a compatible server (LM Studio, vLLM, etc.). When True, callers
    # may pass output_schema to get schema-validated JSON instead of freeform text.
    structured_output: bool = False
    # Sampling parameters (OpenAI-compatible). Leave as None to use server defaults.
    temperature: float | None = None
    top_p: float | None = None
    top_k: float | None = None
    seed: int | None = None


_LLM_PROVIDER_FIELDS: frozenset[str] = frozenset(f.name for f in fields(LLMProviderConfig))


@dataclass
class CodexExecConfig:
    """Settings for running Codex CLI as the local LLM backend."""

    model: str = ""
    max_tokens_card: int = 1024
    max_tokens_digest: int = 2048
    binary: str = "codex"
    sandbox: str = "read-only"


_CODEX_EXEC_FIELDS: frozenset[str] = frozenset(f.name for f in fields(CodexExecConfig))


@dataclass
class GeminiCliConfig:
    """Settings for running Gemini CLI (`gemini -p`) as the LLM backend."""

    model: str = ""
    max_tokens_card: int = 1024
    max_tokens_digest: int = 2048
    binary: str = "gemini"
    # Approval mode passed via --approval-mode. "yolo" auto-approves everything
    # (safe here because we instruct the model to use no tools).
    approval_mode: str = "yolo"


_GEMINI_CLI_FIELDS: frozenset[str] = frozenset(f.name for f in fields(GeminiCliConfig))


LLMStage = Literal["cards", "digests", "redigest"]


@dataclass
class LLMRoutingConfig:
    """Stage-specific routing to concrete LLM providers."""

    cards: str = "anthropic"
    digests: str = "anthropic"
    redigest: str = "anthropic"


_LLM_ROUTING_FIELDS: frozenset[str] = frozenset(f.name for f in fields(LLMRoutingConfig))


@dataclass
class LLMConfig:
    """LLM configuration with provider selection."""

    provider: str = "anthropic"
    routing: LLMRoutingConfig = field(default_factory=LLMRoutingConfig)
    anthropic: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    openai_compat: LLMProviderConfig = field(default_factory=LLMProviderConfig)
    codex_exec: CodexExecConfig = field(default_factory=CodexExecConfig)
    gemini_cli: GeminiCliConfig = field(default_factory=GeminiCliConfig)

    def __post_init__(self) -> None:
        """Hydrate stage routing from the legacy provider when routing is untouched."""
        if self.routing == LLMRoutingConfig() and self.provider != "anthropic":
            self.routing = LLMRoutingConfig(
                cards=self.provider,
                digests=self.provider,
                redigest=self.provider,
            )

    def config_for_provider(
        self, provider: str
    ) -> LLMProviderConfig | CodexExecConfig | GeminiCliConfig:
        """Return the concrete provider config object for ``provider``."""
        if provider == "anthropic":
            return self.anthropic
        if provider == "openai_compat":
            return self.openai_compat
        if provider == "codex_exec":
            return self.codex_exec
        if provider == "gemini_cli":
            return self.gemini_cli
        raise ValueError(f"Unknown LLM provider: {provider}")

    def provider_for_stage(self, stage: LLMStage) -> str:
        """Return the routed provider name for a generation stage."""
        if stage == "cards":
            return self.routing.cards
        if stage == "digests":
            return self.routing.digests
        if stage == "redigest":
            return self.routing.redigest
        raise ValueError(f"Unknown LLM stage: {stage}")

    def config_for_stage(
        self, stage: LLMStage
    ) -> LLMProviderConfig | CodexExecConfig | GeminiCliConfig:
        """Return the concrete provider config for a generation stage."""
        return self.config_for_provider(self.provider_for_stage(stage))

    @property
    def active(self) -> LLMProviderConfig | CodexExecConfig | GeminiCliConfig:
        """Return the legacy globally selected provider config."""
        return self.config_for_provider(self.provider)


@dataclass
class CitationsConfig:
    """Citation fetcher settings."""

    enabled: bool = True
    provider: str = "openalex"
    fallback: str = "semantic_scholar"
    email: str = ""
    api_key: str = ""
    rate_limit_delay: float = 0.1
    max_age_days: int = 30
    top_n: int = 10
    timeout_seconds: float = 10.0


@dataclass
class ExtractionConfig:
    """Extraction strategy settings."""

    # PDF backend: "pdfminer" (permissive default, always installed) or
    # "pymupdf" (optional extra; AGPL-licensed, install zotero-summarizer[pymupdf]).
    backend: str = "pdfminer"
    mode: str = "pages"  # "pages" | "sections" | "notebooklm"
    target_sections: list[str] = field(
        default_factory=lambda: [
            "abstract",
            "introduction",
            "methods",
            "materials",
            "results",
            "discussion",
            "conclusion",
            "summary",
        ]
    )
    fuzzy_threshold: int = 80  # rapidfuzz ratio threshold (0-100)


_EXTRACTION_FIELDS: frozenset[str] = frozenset(f.name for f in fields(ExtractionConfig))


@dataclass
class NotebookLMConfig:
    """NotebookLM integration settings (used when extraction.mode = 'notebooklm')."""

    max_sources_per_notebook: int = 30
    query_timeout: float = 120.0
    upload_timeout: float = 600.0
    cleanup: bool = False  # delete notebooks after processing
    parse_locally: bool = False  # route NLM output through local LLM for JSON conversion
    profile: str = ""  # nlm CLI profile to use


_NOTEBOOKLM_FIELDS: frozenset[str] = frozenset(f.name for f in fields(NotebookLMConfig))


@dataclass
class RestructureConfig:
    """Structure advisor settings."""

    max_digest_chars: int = 800


@dataclass
class Config:
    """Top-level application configuration."""

    bbt_json: Path = field(default_factory=lambda: Path("~/Zotero/zot.json"))
    zotero_sqlite: Path = field(default_factory=lambda: Path("~/Zotero/zotero.sqlite"))
    zotero_pdf_base: str = ""
    vault_output: Path = field(default_factory=lambda: Path("./vault"))
    cache_dir: Path = field(default_factory=lambda: Path("./cache"))
    collections: list[str] = field(default_factory=list)
    max_first_pages: int = 3
    max_last_pages: int = 2
    max_text_chars: int = 24000
    min_text_chars: int = 500
    llm: LLMConfig = field(default_factory=LLMConfig)
    generate_paper_notes: bool = True
    prompt_version: int = 1
    max_pdf_pages: int | None = None
    citations: CitationsConfig = field(default_factory=CitationsConfig)
    restructure: RestructureConfig = field(default_factory=RestructureConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    notebooklm: NotebookLMConfig = field(default_factory=NotebookLMConfig)


def validate_config(
    config: Config,
    *,
    require_llm: bool = False,
    llm_stages: tuple[LLMStage, ...] | None = None,
) -> list[str]:
    """Check config for common problems. Returns a list of error messages (empty = OK)."""
    errors: list[str] = []
    bbt = config.bbt_json.expanduser()
    if not bbt.exists():
        errors.append(f"BBT JSON not found: {bbt}")
    sql = config.zotero_sqlite.expanduser()
    if not sql.exists():
        errors.append(f"Zotero SQLite not found: {sql}")
    if require_llm:
        stages = llm_stages or ("cards", "digests", "redigest")
        for stage in stages:
            try:
                provider = config.llm.provider_for_stage(stage)
                provider_config = config.llm.config_for_stage(stage)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if provider == "codex_exec":
                continue
            if provider == "gemini_cli" and not provider_config.model:
                # Gemini CLI auto-selects a model when none is specified.
                continue
            if not provider_config.model:
                errors.append(
                    f"LLM model not set for stage '{stage}' using provider '{provider}'. "
                    f"Set it in config.yaml under llm.{provider}.model."
                )
    return errors


def load_config(path: Path) -> Config:
    """Load config from a YAML file. Expands ~ in path fields."""
    with open(path) as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return Config()

    known_fields = {f.name for f in fields(Config)}
    unknown = set(raw.keys()) - known_fields
    if unknown:
        logger.warning("Unknown config keys ignored: %s", ", ".join(sorted(unknown)))
        raw = {k: v for k, v in raw.items() if k in known_fields}

    llm_raw = raw.pop("llm", {})
    citations_raw = raw.pop("citations", {}) or {}
    restructure_raw = raw.pop("restructure", {}) or {}
    extraction_raw = raw.pop("extraction", {}) or {}
    notebooklm_raw = raw.pop("notebooklm", {}) or {}
    _cite_fields = {f.name for f in fields(CitationsConfig)}
    _rest_fields = {f.name for f in fields(RestructureConfig)}
    citations = CitationsConfig(**{k: v for k, v in citations_raw.items() if k in _cite_fields})
    restructure = RestructureConfig(
        **{k: v for k, v in restructure_raw.items() if k in _rest_fields}
    )
    extraction = ExtractionConfig(
        **{k: v for k, v in extraction_raw.items() if k in _EXTRACTION_FIELDS}
    )
    notebooklm = NotebookLMConfig(
        **{k: v for k, v in notebooklm_raw.items() if k in _NOTEBOOKLM_FIELDS}
    )

    def _make_provider_config(section_name: str) -> LLMProviderConfig:
        provider_raw = llm_raw.get(section_name) or {}
        unknown_provider = set(provider_raw.keys()) - _LLM_PROVIDER_FIELDS
        if unknown_provider:
            logger.warning(
                "Unknown config keys in llm.%s ignored: %s (valid keys: %s)",
                section_name,
                ", ".join(sorted(unknown_provider)),
                ", ".join(sorted(_LLM_PROVIDER_FIELDS)),
            )
            provider_raw = {k: v for k, v in provider_raw.items() if k in _LLM_PROVIDER_FIELDS}
        return LLMProviderConfig(**provider_raw)

    def _make_codex_exec_config() -> CodexExecConfig:
        provider_raw = llm_raw.get("codex_exec") or {}
        unknown_provider = set(provider_raw.keys()) - _CODEX_EXEC_FIELDS
        if unknown_provider:
            logger.warning(
                "Unknown config keys in llm.codex_exec ignored: %s (valid keys: %s)",
                ", ".join(sorted(unknown_provider)),
                ", ".join(sorted(_CODEX_EXEC_FIELDS)),
            )
            provider_raw = {k: v for k, v in provider_raw.items() if k in _CODEX_EXEC_FIELDS}
        return CodexExecConfig(**provider_raw)

    def _make_gemini_cli_config() -> GeminiCliConfig:
        provider_raw = llm_raw.get("gemini_cli") or {}
        unknown_provider = set(provider_raw.keys()) - _GEMINI_CLI_FIELDS
        if unknown_provider:
            logger.warning(
                "Unknown config keys in llm.gemini_cli ignored: %s (valid keys: %s)",
                ", ".join(sorted(unknown_provider)),
                ", ".join(sorted(_GEMINI_CLI_FIELDS)),
            )
            provider_raw = {k: v for k, v in provider_raw.items() if k in _GEMINI_CLI_FIELDS}
        return GeminiCliConfig(**provider_raw)

    llm_provider = llm_raw.get("provider", "anthropic")
    routing_raw = llm_raw.get("routing", {}) or {}
    unknown_routing = set(routing_raw.keys()) - _LLM_ROUTING_FIELDS
    if unknown_routing:
        logger.warning(
            "Unknown config keys in llm.routing ignored: %s (valid keys: %s)",
            ", ".join(sorted(unknown_routing)),
            ", ".join(sorted(_LLM_ROUTING_FIELDS)),
        )
        routing_raw = {k: v for k, v in routing_raw.items() if k in _LLM_ROUTING_FIELDS}
    routing_defaults = {"cards": llm_provider, "digests": llm_provider, "redigest": llm_provider}
    routing = LLMRoutingConfig(**(routing_defaults | routing_raw))

    llm = LLMConfig(
        provider=llm_provider,
        routing=routing,
        anthropic=_make_provider_config("anthropic"),
        openai_compat=_make_provider_config("openai_compat"),
        codex_exec=_make_codex_exec_config(),
        gemini_cli=_make_gemini_cli_config(),
    )

    config_dir = path.parent
    path_fields = ["bbt_json", "zotero_sqlite", "vault_output", "cache_dir"]
    for key in path_fields:
        if key in raw:
            p = Path(raw[key]).expanduser()
            if not p.is_absolute():
                p = (config_dir / p).resolve()
            raw[key] = p

    return Config(
        llm=llm,
        citations=citations,
        restructure=restructure,
        extraction=extraction,
        notebooklm=notebooklm,
        **raw,
    )
