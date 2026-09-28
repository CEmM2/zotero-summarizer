"""Default, permissively licensed PDF backend.

Uses pdfminer.six (MIT) for text and layout extraction and pypdf (BSD-3)
for page counts and document outlines. Installed with the base package.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTChar, LTTextContainer, LTTextLine
from pypdf import PdfReader

from .base import PdfLine, TocEntry


def _iter_text_lines(node: Any) -> Iterator[LTTextLine]:
    """Recursively yield text lines from a pdfminer layout tree."""
    if isinstance(node, LTTextLine):
        yield node
        return
    if isinstance(node, Iterable):
        for child in node:
            yield from _iter_text_lines(child)


class PdfMinerBackend:
    """Permissively licensed default backend (pdfminer.six + pypdf)."""

    name = "pdfminer"

    def __init__(self) -> None:
        self._laparams = LAParams()

    def page_count(self, path: Path) -> int:
        reader = PdfReader(str(path))
        return len(reader.pages)

    def page_texts(self, path: Path, pages: Sequence[int]) -> dict[int, str]:
        requested = sorted(set(pages))
        if not requested:
            return {}

        result: dict[int, str] = {}
        # extract_pages yields the selected pages in document order, so the
        # sorted request list and the yielded layouts stay aligned.
        layouts = extract_pages(str(path), page_numbers=set(requested), laparams=self._laparams)
        for page_index, layout in zip(requested, layouts, strict=False):
            chunks = [
                element.get_text() for element in layout if isinstance(element, LTTextContainer)
            ]
            result[page_index] = "\n".join(chunks)
        return result

    def lines(self, path: Path, pages: Sequence[int] | None = None) -> list[PdfLine]:
        requested = sorted(set(pages)) if pages is not None else None
        layouts = extract_pages(
            str(path),
            page_numbers=set(requested) if requested is not None else None,
            laparams=self._laparams,
        )

        result: list[PdfLine] = []
        if requested is not None:
            page_indices: Iterator[int] = iter(requested)
        else:
            page_indices = iter(range(self.page_count(path)))

        for page_index, layout in zip(page_indices, layouts, strict=False):
            for line in _iter_text_lines(layout):
                text = line.get_text().strip()
                if not text:
                    continue
                sizes = [float(char.size) for char in line if isinstance(char, LTChar)]
                result.append(
                    PdfLine(
                        text=text,
                        page_index=page_index,
                        font_size=max(sizes, default=0.0),
                    )
                )
        return result

    def toc(self, path: Path) -> list[TocEntry]:
        reader = PdfReader(str(path))
        total = len(reader.pages)
        result: list[TocEntry] = []

        def walk(items: list[Any], level: int = 1) -> None:
            for item in items:
                if isinstance(item, list):
                    walk(item, level + 1)
                    continue
                try:
                    page_index = reader.get_destination_page_number(item)
                except Exception:
                    continue
                if page_index is None:
                    continue
                # Clamp like the historical extractor: never negative.
                page_index = max(int(page_index), 0)
                if page_index >= total:
                    continue
                result.append(TocEntry(level=level, title=str(item.title), page_index=page_index))

        try:
            walk(reader.outline)
        except Exception:
            # A missing or malformed outline is not fatal: ZSum falls back to
            # heading-based section detection.
            return []
        return result
