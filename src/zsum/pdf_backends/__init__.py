"""PDF backend registry.

The default ``pdfminer`` backend (pdfminer.six + pypdf) is permissively
licensed and always installed. The optional ``pymupdf`` backend is
AGPL-licensed and only imported after the user explicitly selects it, so a
normal installation never imports or requires PyMuPDF.
"""

from __future__ import annotations

from .base import PdfBackend, PdfLine, TocEntry

KNOWN_BACKENDS: tuple[str, ...] = ("pdfminer", "pymupdf")


def get_pdf_backend(name: str) -> PdfBackend:
    """Return a PdfBackend instance for ``name`` ('pdfminer' or 'pymupdf')."""
    normalized = name.strip().lower()

    if normalized == "pdfminer":
        from .pdfminer_backend import PdfMinerBackend

        return PdfMinerBackend()

    if normalized == "pymupdf":
        # Lazy import: a normal installation never imports PyMuPDF.
        from .pymupdf_backend import PyMuPDFBackend

        return PyMuPDFBackend()

    raise ValueError(
        f"Unknown PDF backend: {name!r}. Expected one of: {', '.join(KNOWN_BACKENDS)}."
    )


__all__ = [
    "KNOWN_BACKENDS",
    "PdfBackend",
    "PdfLine",
    "TocEntry",
    "get_pdf_backend",
]
