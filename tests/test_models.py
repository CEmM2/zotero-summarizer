"""Tests for the models module."""

from __future__ import annotations

from tests.helpers import make_test_item
from zsum.models import Item, TextQuality


class TestTextQuality:
    def test_values(self):
        assert TextQuality.GOOD == "good"
        assert TextQuality.DEGRADED == "degraded"
        assert TextQuality.NO_PDF == "no_pdf"

    def test_is_str(self):
        assert isinstance(TextQuality.GOOD, str)

    def test_comparison_with_string(self):
        assert TextQuality.GOOD == "good"


class TestItem:
    def test_library_id_defaults_to_none(self):
        item = Item(
            citekey="smith2017",
            zotero_key="AAA",
            item_id=1,
            title="Phase Field Modeling",
        )

        assert item.library_id is None

    def test_make_test_item_accepts_library_id_override(self):
        item = make_test_item(library_id=7)

        assert item.library_id == 7
