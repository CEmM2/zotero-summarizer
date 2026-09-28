"""Optional PyMuPDF backend.

PyMuPDF is licensed under the AGPL-3.0 (or an Artifex commercial license).
It is NOT installed by default; ``pip install "zotero-summarizer[pymupdf]"``
opts in. This module must only be imported after the user selects the
``pymupdf`` backend explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .base import PdfLine, TocEntry


class PyMuPDFBackend:
    """Backend using PyMuPDF (fitz). Optional, AGPL-licensed dependency."""

    name = "pymupdf"

    def __init__(self) -> None:
        try:
            import pymupdf
        except ImportError:
            try:
                # Older PyMuPDF releases only expose the legacy 'fitz' name.
                import fitz as pymupdf  # type: ignore[no-redef]
            except ImportError as exc:
                raise RuntimeError(
                    "The 'pymupdf' PDF backend was selected but PyMuPDF is not installed.\n"
                    "Install it with:\n\n"
                    '    uv tool install --reinstall "zotero-summarizer[pymupdf]"\n\n'
                    "or switch to the default backend in config.yaml:\n\n"
                    "    extraction:\n"
                    "      backend: pdfminer\n"
                ) from exc

        self._fitz = pymupdf

    def page_count(self, path: Path) -> int:
        with self._fitz.open(path) as doc:
            return len(doc)

    def page_texts(self, path: Path, pages: Sequence[int]) -> dict[int, str]:
        result: dict[int, str] = {}
        with self._fitz.open(path) as doc:
            for page_index in pages:
                if 0 <= page_index < len(doc):
                    result[page_index] = doc[page_index].get_text("text")
        return result

    def lines(self, path: Path, pages: Sequence[int] | None = None) -> list[PdfLine]:
        result: list[PdfLine] = []
        with self._fitz.open(path) as doc:
            page_indices = pages if pages is not None else range(len(doc))
            for page_index in page_indices:
                if not 0 <= page_index < len(doc):
                    continue
                text_dict = doc[page_index].get_text("dict")
                for block in text_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        text = "".join(str(span.get("text", "")) for span in spans).strip()
                        if not text:
                            continue
                        result.append(
                            PdfLine(
                                text=text,
                                page_index=page_index,
                                font_size=max(
                                    (float(span.get("size", 0.0)) for span in spans),
                                    default=0.0,
                                ),
                            )
                        )
        return result

    def toc(self, path: Path) -> list[TocEntry]:
        with self._fitz.open(path) as doc:
            raw_toc = doc.get_toc() or []
            total = len(doc)
        entries: list[TocEntry] = []
        for entry in raw_toc:
            if len(entry) < 3:
                continue
            level, title, page_number = entry[:3]
            # Clamp like the historical extractor: page 0 maps to index 0.
            page_index = max(int(page_number) - 1, 0)
            if page_index >= total:
                continue
            entries.append(TocEntry(level=int(level), title=str(title), page_index=page_index))
        return entries
