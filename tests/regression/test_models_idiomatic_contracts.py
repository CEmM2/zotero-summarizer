"""Tests for Idiomatic checks: frozenset, Field(ge=0), type hint.

This task applies idiomatic improvements:
- Use frozenset for _TRANSIENT_STATUS_CODES and _FATAL_STATUS_CODES in llm.py
- Add Field(ge=0) on Item.item_id in models.py to reject negative IDs
- Fix _is_transient type hint from BaseException to Exception
- Replace len(value)==0 with not value in cards.py (idiomatic pattern)

Covers:
- AC-1: Status code sets are frozenset (immutable)
- AC-2: _is_transient accepts Exception, not BaseException (type hint fix — lint-covered)
- AC-3: No len(x)==0 patterns in cards.py (lint-covered, ruff check only)
- AC-4: Item(item_id=-1) raises ValidationError with Field(ge=0) constraint
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zsum.llm import _FATAL_STATUS_CODES, _TRANSIENT_STATUS_CODES
from zsum.models import Item


class TestModelsIdiomaticContracts:
    """
    Tests for Idiomatic checks: frozenset, Field(ge=0), type hint
    Covers: AC-1 (frozenset), AC-4 (Item ge=0)
    (AC-2 type hint + AC-3 idiomatic emptiness are ruff-covered — no runtime test.)
    """

    @pytest.mark.unit
    def test_transient_status_codes_is_frozenset(self):
        """
        Verifies: _TRANSIENT_STATUS_CODES is a frozenset, not a mutable set.
        Covers: AC-1 (Status code sets are frozenset)
        Passes when: type(_TRANSIENT_STATUS_CODES) is frozenset
        """
        assert type(_TRANSIENT_STATUS_CODES) is frozenset

    @pytest.mark.unit
    def test_fatal_status_codes_is_frozenset(self):
        """
        Verifies: _FATAL_STATUS_CODES is a frozenset, not a mutable set.
        Covers: AC-1 (Status code sets are frozenset)
        Passes when: type(_FATAL_STATUS_CODES) is frozenset
        """
        assert type(_FATAL_STATUS_CODES) is frozenset

    @pytest.mark.unit
    def test_transient_status_codes_immutable(self):
        """
        Verifies: _TRANSIENT_STATUS_CODES cannot be modified (frozenset immutability).
        Covers: AC-1 (frozenset immutability)
        Passes when: Attempting to add() or discard() raises AttributeError
        """
        with pytest.raises(AttributeError):
            _TRANSIENT_STATUS_CODES.add(999)  # type: ignore[attr-defined]

    @pytest.mark.unit
    def test_item_negative_item_id_raises_validation_error(self):
        """
        Verifies: Item(item_id=-1) raises ValidationError due to Field(ge=0) constraint.
        Covers: AC-4 (Item(item_id=-1) raises ValidationError)
        Passes when: Item(item_id=-1, ...) raises ValidationError mentioning constraint
        """
        with pytest.raises(ValidationError):
            Item(citekey="test2024", zotero_key="ABCD1234", title="Test Paper", item_id=-1)

    @pytest.mark.unit
    def test_item_item_id_zero_allowed(self):
        """
        Verifies: Item(item_id=0) is allowed by Field(ge=0) constraint.
        Covers: AC-4 (Field(ge=0) allows 0)
        Passes when: Item(..., item_id=0) constructs successfully
        """
        item = Item(citekey="test2024", zotero_key="ABCD1234", title="Test Paper", item_id=0)
        assert item.item_id == 0

    @pytest.mark.unit
    def test_item_positive_item_id_allowed(self):
        """
        Verifies: Item(item_id=123) is allowed by Field(ge=0) constraint.
        Covers: AC-4 (Field(ge=0) allows positive IDs)
        Passes when: Item(..., item_id=123) constructs successfully
        """
        item = Item(citekey="test2024", zotero_key="ABCD1234", title="Test Paper", item_id=123)
        assert item.item_id == 123
