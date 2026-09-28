"""Shared test helpers for zsum tests."""

from __future__ import annotations

from zsum.models import Item


def make_test_item(**overrides) -> Item:
    """Create a test Item with sensible defaults. Accepts keyword overrides."""
    defaults = dict(
        citekey="smith2017",
        zotero_key="AAA",
        item_id=1,
        title="Phase Field Modeling",
        authors=["Smith, John"],
        year=2017,
        venue="JMPS",
        doi="10.1000/test",
        abstract="A phase field model.",
    )
    defaults.update(overrides)
    return Item(**defaults)
