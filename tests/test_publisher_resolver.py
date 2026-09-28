"""Tests for the public wikilink/filename resolver."""

from __future__ import annotations

import pytest

from zsum.publisher.resolver import (
    FilenameTracker,
    resolve_collection_wikilink,
    resolve_paper_wikilink,
    safe_filename,
)


class TestSafeFilename:
    def test_replaces_unsafe_chars(self) -> None:
        assert (
            safe_filename("Materials: Composites/Mechanics?") == "Materials_ Composites_Mechanics_"
        )

    def test_strips_leading_trailing_whitespace(self) -> None:
        assert safe_filename("  hello  ") == "hello"

    def test_strips_leading_trailing_dots(self) -> None:
        assert safe_filename("..foo..") == "foo"

    def test_passthrough_simple(self) -> None:
        assert safe_filename("Plain Note") == "Plain Note"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            safe_filename("...")

    def test_each_unsafe_char(self) -> None:
        for ch in '<>:"\\/|?*':
            assert safe_filename(f"a{ch}b") == "a_b"


class TestFilenameTracker:
    def test_first_call_returns_safe_name(self) -> None:
        t = FilenameTracker()
        assert t.resolve("Foo") == "Foo"

    def test_idempotent_for_same_input(self) -> None:
        t = FilenameTracker()
        assert t.resolve("Foo") == "Foo"
        assert t.resolve("Foo") == "Foo"

    def test_real_collision(self) -> None:
        t = FilenameTracker()
        assert t.resolve("a/b") == "a_b"
        assert t.resolve("a:b") == "a_b_2"
        assert t.resolve("a*b") == "a_b_3"

    def test_get_safe_name_after_resolve(self) -> None:
        t = FilenameTracker()
        t.resolve("Foo")
        assert t.get_safe_name("Foo") == "Foo"

    def test_get_safe_name_unknown_raises(self) -> None:
        t = FilenameTracker()
        with pytest.raises(KeyError):
            t.get_safe_name("never-registered")


class TestPaperAndCollectionResolvers:
    def test_paper_wikilink(self) -> None:
        assert resolve_paper_wikilink("smith2020") == "@smith2020"

    def test_paper_wikilink_with_unsafe_char(self) -> None:
        assert resolve_paper_wikilink("smith/2020") == "@smith_2020"

    def test_collection_wikilink(self) -> None:
        assert resolve_collection_wikilink("My Collection") == "My Collection"

    def test_collection_wikilink_with_slash(self) -> None:
        assert resolve_collection_wikilink("Folder/Sub") == "Folder_Sub"


class TestBackwardCompatAliases:
    def test_private_aliases_in_publisher(self) -> None:
        from zsum.publisher import _FilenameTracker, _safe_filename

        assert _safe_filename("a:b") == "a_b"
        t = _FilenameTracker()
        assert t.resolve("Foo") == "Foo"
