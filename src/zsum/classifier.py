"""Paper-type heuristics for review/survey/tutorial/meta-analysis detection.

The heuristic runs at index time against metadata only (title, venue, tags). LLM
confirmation during card generation may override the classification.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .models import PAPER_TYPES, Item

_META_ANALYSIS_RE = re.compile(r"\bmeta[- ]analysis\b", re.IGNORECASE)
_SURVEY_RE = re.compile(r"\bsurvey(s|ed|ing)?\b", re.IGNORECASE)
_TUTORIAL_RE = re.compile(r"\btutorial\b", re.IGNORECASE)

REVIEW_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\breview\b",
        r"\bsurvey\b",
        r"\boverview\b",
        r"\bstate[- ]of[- ]the[- ]art\b",
        r"\btutorial\b",
        r"\bmeta[- ]analysis\b",
        r"\bsystematic review\b",
        r"\bcomprehensive review\b",
        r"\bcritical review\b",
        r"\bliterature review\b",
        r"\brecent (advances|progress|developments)\b",
        r"\bperspective(s)?\b",
    )
)

REVIEW_VENUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\breview(s)?\b",
        r"\bsurvey(s)?\b",
        r"\bprogress in\b",
        r"\badvances in\b",
    )
)

REVIEW_TAGS: frozenset[str] = frozenset({"review", "survey", "meta-analysis", "overview"})

# Phrases whose presence in a title is a strong negative — they contain the word
# "review" but do not indicate a review paper.
_FALSE_POSITIVE_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bpeer[- ]review",
        r"\bcode review",
        r"\bunder review\b",
    )
)


def _specific_type(text: str) -> str:
    """Disambiguate review/survey/tutorial/meta-analysis from a lowercased string."""
    if _META_ANALYSIS_RE.search(text):
        return "meta-analysis"
    if _TUTORIAL_RE.search(text):
        return "tutorial"
    if _SURVEY_RE.search(text):
        return "survey"
    return "review"


def _matches_any(patterns: Iterable[re.Pattern[str]], text: str) -> bool:
    return any(p.search(text) for p in patterns)


def classify_by_metadata(item: Item) -> str:
    """Return one of: research | review | survey | meta-analysis | tutorial.

    Applies the title pattern set first (most informative), then venue, then tags.
    Returns ``"research"`` when none of the patterns match or when a known
    false-positive phrase is present in the title.
    """
    title = item.title or ""
    venue = item.venue or ""
    tags = item.tags or []

    if _matches_any(_FALSE_POSITIVE_TITLE_PATTERNS, title):
        return "research"

    if _matches_any(REVIEW_TITLE_PATTERNS, title):
        return _specific_type(title)

    if _matches_any(REVIEW_VENUE_PATTERNS, venue):
        return "review"

    for tag in tags:
        tag_lower = tag.lower()
        if tag_lower in REVIEW_TAGS:
            return _specific_type(tag_lower)

    return "research"


def normalize_paper_type(value: str | None, fallback: str = "research") -> str:
    """Return value if it is one of ``PAPER_TYPES``, otherwise ``fallback``."""
    if isinstance(value, str) and value.strip().lower() in PAPER_TYPES:
        return value.strip().lower()
    return fallback if fallback in PAPER_TYPES else "research"
