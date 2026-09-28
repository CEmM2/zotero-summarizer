"""Backend contract for PDF primitives used by ZSum's extraction pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PdfLine:
    """A line-like text fragment used for heading detection."""

    text: str
    page_index: int
    font_size: float


@dataclass(frozen=True)
class TocEntry:
    """A normalized PDF table-of-contents entry."""

    level: int
    title: str
    page_index: int  # zero-based


@runtime_checkable
class PdfBackend(Protocol):
    """Operations required by ZSum's extraction pipeline.

    Implementations must return zero-based page indices everywhere and never
    raise on missing outlines (an absent TOC is an empty list, not an error).
    """

    name: str

    def page_count(self, path: Path) -> int:
        """Return the number of pages."""
        ...

    def page_texts(self, path: Path, pages: Sequence[int]) -> dict[int, str]:
        """Return extracted plain text keyed by zero-based page index."""
        ...

    def lines(self, path: Path, pages: Sequence[int] | None = None) -> list[PdfLine]:
        """Return ordered line fragments (with font sizes) for heading detection."""
        ...

    def toc(self, path: Path) -> list[TocEntry]:
        """Return normalized outline entries, or an empty list."""
        ...
