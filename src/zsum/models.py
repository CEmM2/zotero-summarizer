"""Data models for zotero-summarizer."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field


class TextQuality(StrEnum):
    """Quality flag for PDF text extraction."""

    GOOD = "good"
    DEGRADED = "degraded"
    NO_PDF = "no_pdf"
    FALLBACK = "fallback"


PAPER_TYPES: frozenset[str] = frozenset(
    {"research", "review", "survey", "meta-analysis", "tutorial"}
)


class Item(BaseModel):
    """A single Zotero library item (paper)."""

    citekey: str
    zotero_key: str
    library_id: int | None = Field(default=None, ge=0)
    item_id: int | None = Field(default=None, ge=0)
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    abstract: str = ""
    url: str = ""
    tags: list[str] = Field(default_factory=list)
    pdf_path: Path | None = None
    paper_type: str = "research"
    model_config = {"arbitrary_types_allowed": True}

    @property
    def has_pdf(self) -> bool:
        """Return True if pdf_path is set and the file exists on disk."""
        return self.pdf_path is not None and self.pdf_path.exists()

    @property
    def is_review(self) -> bool:
        """Return True for review/survey/meta-analysis classifications."""
        return self.paper_type in {"review", "survey", "meta-analysis"}


class Collection(BaseModel):
    """A Zotero collection (folder) with hierarchy and members."""

    key: str
    name: str
    parent_key: str | None = None
    path: str = ""
    item_citekeys: list[str] = Field(default_factory=list)
    child_keys: list[str] = Field(default_factory=list)


class LibraryIndex(BaseModel):
    """Unified index: all items and collections."""

    items: dict[str, Item] = Field(default_factory=dict)
    collections: dict[str, Collection] = Field(default_factory=dict)
    model_config = {"arbitrary_types_allowed": True}

    @property
    def stats(self) -> dict:
        """Return a dict with total_items, with_pdf, missing_pdf, and total_collections counts."""
        total_items = len(self.items)
        with_pdf = sum(1 for item in self.items.values() if item.has_pdf)
        return {
            "total_items": total_items,
            "with_pdf": with_pdf,
            "missing_pdf": total_items - with_pdf,
            "total_collections": len(self.collections),
        }


class CardMeta(BaseModel):
    """Provenance metadata stored inside cached paper card JSON."""

    model: str = ""
    prompt_version: int = 1
    generated_at: str = ""


class PaperCard(BaseModel):
    """Structured summary of a single paper, produced by the LLM."""

    citekey: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    problem: str = "unknown"
    methods: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    text_quality: str = TextQuality.GOOD
    paper_type: str = "research"
    extraction_method: str | None = None

    # Fields populated by the LLM that we warn about if returned empty.
    LLM_CONTENT_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {"problem", "methods", "key_findings", "limitations"}
    )

    @property
    def is_review(self) -> bool:
        return self.paper_type in {"review", "survey", "meta-analysis"}


class CitationRecord(BaseModel):
    """Citation count for a single paper, fetched from an external provider."""

    citekey: str
    citation_count: int | None = None
    source: str = ""
    fetched_at: str = ""
    external_id: str = ""


class StructureSuggestion(BaseModel):
    """A single structural change proposed by the advisor."""

    type: str
    target: str | list[str] = ""
    proposed: str | list[str] = ""
    rationale: str = ""


class StructureAdvice(BaseModel):
    """Full advisory output: overall assessment, suggestions, proposed tree."""

    overall_assessment: str = ""
    suggestions: list[StructureSuggestion] = Field(default_factory=list)
    proposed_hierarchy: dict = Field(default_factory=dict)
