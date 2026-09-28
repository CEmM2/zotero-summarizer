"""Contract tests for the PDF backend abstraction (pdfminer default, pymupdf optional)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from zsum.cache import extraction_signature
from zsum.config import Config, ExtractionConfig
from zsum.pdf_backends import KNOWN_BACKENDS, PdfLine, TocEntry, get_pdf_backend


def _available_backends() -> list[str]:
    names = ["pdfminer"]
    try:
        import fitz  # noqa: F401

        names.append("pymupdf")
    except ImportError:
        pass
    return names


@pytest.fixture
def contract_pdf(tmp_path: Path) -> Path:
    """A 3-page PDF with wrapped, fully on-page text.

    conftest's real_pdf fixture writes unwrapped lines that overflow the page,
    which PyMuPDF clips at the page boundary while pdfminer does not — useless
    for cross-backend contract tests. This fixture uses insert_textbox so every
    backend sees the same on-page content.
    """
    fitz = pytest.importorskip("fitz")

    pdf_path = tmp_path / "contract_paper.pdf"
    doc = fitz.open()
    pages = [
        "Introduction\n\nThis paper presents a novel phase field model for crack "
        "propagation in brittle materials. We develop a variational formulation "
        "that couples the displacement field with a damage order parameter. The "
        "phase field method has emerged as a powerful tool for modeling fracture "
        "due to its ability to handle complex crack topologies without explicit "
        "tracking of crack surfaces.",
        "Methods\n\nThe phase field approach regularizes sharp crack "
        "discontinuities using a diffuse damage variable. We implement the model "
        "using finite element discretization with adaptive mesh refinement. The "
        "governing equations are solved using a staggered scheme that alternates "
        "between the displacement and phase field equations, validated against "
        "benchmark problems including single edge notch tension and shear tests.",
        "Conclusions\n\nThe proposed model accurately captures crack nucleation "
        "and propagation in brittle materials. Fracture toughness predictions "
        "agree within five percent of experimental measurements. Adaptive mesh "
        "refinement reduces computational cost by an order of magnitude compared "
        "to uniform fine meshes. Future work will extend the model to ductile "
        "fracture and coupled multi-physics settings.",
    ]
    for text in pages:
        page = doc.new_page()
        rect = fitz.Rect(72, 72, page.rect.width - 72, page.rect.height - 72)
        page.insert_textbox(rect, text, fontsize=11)
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def _make_item(pdf_path: Path):
    from zsum.models import Item

    return Item(
        citekey="test2020",
        zotero_key="ABC123",
        item_id=1,
        title="Backend Contract Test",
        abstract="Fallback abstract",
        pdf_path=pdf_path,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    @pytest.mark.unit
    def test_unknown_backend_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown PDF backend"):
            get_pdf_backend("ghostscript")

    @pytest.mark.unit
    def test_known_backends_resolve(self):
        backend = get_pdf_backend("pdfminer")
        assert backend.name == "pdfminer"

    @pytest.mark.unit
    def test_name_is_normalized(self):
        assert get_pdf_backend("  PdfMiner ").name == "pdfminer"

    @pytest.mark.unit
    def test_registry_names_match_known_backends(self):
        assert set(KNOWN_BACKENDS) == {"pdfminer", "pymupdf"}

    @pytest.mark.unit
    def test_missing_pymupdf_raises_helpful_error(self, monkeypatch):
        """When PyMuPDF is absent, selecting it must fail with install guidance."""
        import builtins

        real_import = builtins.__import__

        def _blocked(name, *args, **kwargs):
            if name in {"fitz", "pymupdf"}:
                raise ImportError(f"No module named {name!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _blocked)
        with pytest.raises(RuntimeError, match=r"zotero-summarizer\[pymupdf\]"):
            get_pdf_backend("pymupdf")


# ---------------------------------------------------------------------------
# Backend contract (run against every installed backend)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("backend_name", _available_backends())
class TestBackendContract:
    def test_page_count(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        assert backend.page_count(contract_pdf) == 3

    def test_page_texts_selected_pages(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        texts = backend.page_texts(contract_pdf, [0, 2])

        assert set(texts.keys()) == {0, 2}
        assert "introduction" in texts[0].lower()
        assert "conclusions" in texts[2].lower()

    def test_page_texts_empty_request(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        assert backend.page_texts(contract_pdf, []) == {}

    def test_page_texts_out_of_range_pages_are_omitted(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        texts = backend.page_texts(contract_pdf, [0, 99])
        assert 0 in texts
        assert 99 not in texts

    def test_lines_have_text_pages_and_fonts(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        lines = backend.lines(contract_pdf)

        assert lines, "expected at least one line fragment"
        assert all(isinstance(line, PdfLine) for line in lines)
        assert {line.page_index for line in lines} == {0, 1, 2}
        assert all(line.text.strip() for line in lines)
        assert any(line.font_size > 0 for line in lines)
        # Page indices must be non-decreasing (reading order across pages).
        page_order = [line.page_index for line in lines]
        assert page_order == sorted(page_order)

    def test_lines_page_filter(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        lines = backend.lines(contract_pdf, pages=[1])
        assert lines
        assert {line.page_index for line in lines} == {1}

    def test_toc_is_list_of_entries(self, contract_pdf: Path, backend_name: str):
        backend = get_pdf_backend(backend_name)
        toc = backend.toc(contract_pdf)
        # The fixture PDF has no outline; the contract is an empty list, not an error.
        assert isinstance(toc, list)
        assert all(isinstance(entry, TocEntry) for entry in toc)


@pytest.mark.integration
def test_backends_preserve_section_contract(contract_pdf: Path):
    """Semantic invariants must hold across backends (never byte-equality)."""
    pytest.importorskip("fitz")

    for backend_name in ("pdfminer", "pymupdf"):
        backend = get_pdf_backend(backend_name)
        text = "\n".join(line.text for line in backend.lines(contract_pdf)).lower()

        assert "introduction" in text, backend_name
        assert "methods" in text, backend_name
        assert "conclusions" in text, backend_name
        assert len(text) > 500, backend_name


# ---------------------------------------------------------------------------
# End-to-end through the extractors
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.parametrize("backend_name", _available_backends())
def test_extract_text_pages_mode(contract_pdf: Path, backend_name: str):
    from zsum.extractor import extract_text
    from zsum.models import TextQuality

    config = Config(extraction=ExtractionConfig(backend=backend_name))
    item = _make_item(contract_pdf)
    result = extract_text(item, config)

    assert result.quality == TextQuality.GOOD
    assert result.page_count == 3
    assert "phase field" in result.text.lower()


@pytest.mark.integration
@pytest.mark.parametrize("backend_name", _available_backends())
def test_extract_sections_mode(contract_pdf: Path, backend_name: str):
    from zsum.models import TextQuality
    from zsum.section_extractor import extract_sections

    config = Config(extraction=ExtractionConfig(backend=backend_name, mode="sections"))
    item = _make_item(contract_pdf)
    result = extract_sections(item, config)

    assert result.quality == TextQuality.GOOD
    assert result.extraction_method == "sections"
    assert "introduction" in result.text.lower()
    assert "conclusions" in result.text.lower()


# ---------------------------------------------------------------------------
# Licensing guards
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_default_import_never_touches_pymupdf():
    """Importing zsum with the default backend must not import fitz/pymupdf.

    This is the AGPL guard: the base installation must work — and stay
    MIT-clean — without PyMuPDF ever being imported.
    """
    code = (
        "import sys\n"
        "import zsum.cli, zsum.extractor, zsum.section_extractor, zsum.pdf_backends\n"
        "from zsum.pdf_backends import get_pdf_backend\n"
        "get_pdf_backend('pdfminer')\n"
        "bad = [m for m in sys.modules if m == 'fitz' or m.startswith('pymupdf')]\n"
        "sys.exit(1 if bad else 0)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"PyMuPDF was imported by default path: {proc.stderr}"


@pytest.mark.unit
def test_extraction_signature_changes_with_backend():
    base = Config()
    other = Config(extraction=ExtractionConfig(backend="pymupdf"))
    assert extraction_signature(base) != extraction_signature(other)


@pytest.mark.unit
def test_extraction_signature_stable_for_equal_config():
    assert extraction_signature(Config()) == extraction_signature(Config())
