"""Prompt template loading with 4-tier resolution.

Tier 0 (highest precedence) is the ``ZSUM_PROMPT_DIR`` environment variable,
added so external orchestrators can drop a directory of overlay
prompts in front of the
package's built-in resolution chain without touching subprocess working
directories.
"""

from __future__ import annotations

import importlib.resources as pkg_resources
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def load_prompt(filename: str) -> str:
    """Load a prompt template with 4-tier fallback.

    Resolution order (highest precedence first):
      0. ``$ZSUM_PROMPT_DIR/<filename>`` if the env var is set and the file
         exists. Allows external orchestrators to overlay
         prompts without touching the subprocess CWD or the
         installed package data.
      1. Package data via importlib.resources (works in wheel installs)
      2. ``prompts/`` directory relative to CWD
      3. Built-in defaults for known filenames

    Tier 0 is **strictly additive**: when ``ZSUM_PROMPT_DIR`` is unset, or
    set but the specific file is absent, every later tier behaves exactly
    as before this change (no regression in existing callers).

    Raises FileNotFoundError for unknown filenames with no built-in default.
    """
    # Tier 0: ZSUM_PROMPT_DIR env-var overlay for external orchestrators.
    # Strictly additive — falls through silently when
    # the env var is unset or the file is absent.
    prompt_dir = os.environ.get("ZSUM_PROMPT_DIR")
    if prompt_dir:
        env_path = Path(prompt_dir) / filename
        if env_path.exists():
            return env_path.read_text(encoding="utf-8")

    # Tier 1: package data
    try:
        ref = pkg_resources.files("zsum") / "prompts" / filename
        text = ref.read_text(encoding="utf-8")
        if text:
            return text
    except (FileNotFoundError, TypeError, ModuleNotFoundError):
        pass

    # Tier 2: CWD prompts directory
    cwd_path = Path("prompts") / filename
    if cwd_path.exists():
        return cwd_path.read_text(encoding="utf-8")

    # Tier 3: built-in defaults
    defaults = _builtin_defaults()
    if filename in defaults:
        logger.warning("Using built-in default for prompt '%s'", filename)
        return defaults[filename]

    raise FileNotFoundError(f"Prompt template not found: {filename}")


def _builtin_defaults() -> dict[str, str]:
    return {
        "paper_card.txt": _default_paper_card_prompt(),
        "collection_digest.txt": _default_digest_prompt(),
        "collection_digest_structured.txt": _default_digest_structured_prompt(),
        "collection_redigest.txt": _default_redigest_prompt(),
    }


def _default_paper_card_prompt() -> str:
    return (
        "You are a research paper summarizer. Given the metadata and extracted "
        "text of an academic paper, produce a structured JSON summary.\n\n"
        "Return ONLY valid JSON matching this schema exactly. "
        "Do not include markdown fences or any other text.\n\n"
        "Schema:\n{\n"
        '  "problem": "1-3 sentences describing the research question or gap",\n'
        '  "methods": ["concise bullet point", ...],\n'
        '  "key_findings": ["concise bullet point", ...],\n'
        '  "limitations": ["concise bullet point", ...],\n'
        '  "keywords": ["keyword", ...]\n}\n\n'
        "Rules:\n- Only use information from the provided text.\n"
        '- If not supported by the text, use "unknown" or an empty list.\n'
        "- Keep bullets concise (1 sentence each).\n"
        "- Keywords should be 3-8 specific terms, not generic.\n"
    )


def _default_digest_prompt() -> str:
    return (
        "You are a research librarian summarizing a collection of academic papers. "
        "Given structured summaries (paper cards) for each paper, write a concise digest.\n\n"
        "Output format (Markdown):\n\n"
        "## Summary\n"
        "1-3 paragraphs synthesizing the collection. Cite papers using citekeys in parentheses, "
        "e.g., (smith2017PhaseField; zhao2020CrackProp). Group by themes.\n\n"
        "## Key Themes\n- Bullet points identifying major research themes\n\n"
        "## Common Methods\n- Bullet points on shared methodologies\n\n"
        "## Gaps and Limitations\n- Bullet points on what is missing or limited\n\n"
        "Rules:\n- Every factual claim must cite at least one citekey.\n"
        "- Do not invent information not present in the paper cards.\n"
        "- Prefer synthesis over enumeration.\n"
    )


def _default_digest_structured_prompt() -> str:
    return (
        "You are a research librarian writing a concise digest of an academic paper collection. "
        "You are given structured summaries (paper cards) for every paper in the collection.\n\n"
        "Return structured content matching the provided schema.\n\n"
        "Field requirements:\n"
        '- "summary": 1-3 paragraphs that synthesize the collection as a whole. '
        "Identify the overarching research questions, how the papers relate to each other, "
        "and what the collective body of work achieves. Cite papers inline using Obsidian "
        "wikilinks such as [[@smith2017PhaseField]]. Group discussion by theme rather than "
        "listing papers one by one.\n"
        '- "key_themes": concise bullet-style items capturing the major research themes or '
        "questions addressed across the collection.\n"
        '- "common_methods": concise bullet-style items capturing methodologies, tools, or '
        "frameworks shared by multiple papers.\n"
        '- "gaps_and_limitations": concise bullet-style items describing what is missing, '
        "underexplored, or limited across the collection as a whole.\n\n"
        "Rules:\n"
        "- Every factual claim in summary must cite at least one citekey using [[@citekey]].\n"
        "- Do not cite a citekey that was not provided in the input.\n"
        "- Do not invent findings or methods not present in the paper cards.\n"
        "- Prefer synthesis and pattern recognition over enumeration.\n"
        "- If papers contradict each other, note the disagreement and cite both sides.\n"
        "- Keep the total content concise enough to fit comfortably within the requested schema.\n"
    )


def _default_redigest_prompt() -> str:
    return (
        "You are a research librarian refining an existing collection digest into its final "
        "published form.\n\n"
        "You are given:\n"
        "- collection metadata\n"
        "- the current first-pass digest markdown\n"
        "- an optional compact grounding list of collection papers\n\n"
        "Your job is to improve clarity, flow, structure, and final readability while preserving "
        "the factual content of the source digest.\n\n"
        "Output Markdown only, intended for final publish use.\n\n"
        "Rules:\n"
        "- Treat the first-pass digest as the primary factual source.\n"
        "- Use only the supplied digest and explicitly provided collection context.\n"
        "- Do not invent claims, methods, limitations, or citations that are not grounded in the "
        "provided material.\n"
        "- Preserve citekeys and supporting references already present in the digest.\n"
        "- If you strengthen wording or reorganize sections, keep the underlying claims"
        " unchanged.\n"
        "- Keep the output concise and publication-ready.\n"
        "- Return only the final markdown with no preamble or commentary.\n"
    )
