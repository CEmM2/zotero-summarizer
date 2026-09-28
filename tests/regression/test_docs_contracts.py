"""Regression tests for doc-critical contracts."""

from __future__ import annotations


def test_cli_subcommands_complete():
    """All expected CLI subcommands are registered on the Click group."""
    from zsum.cli import main

    expected = {
        "index",
        "extract",
        "cards",
        "digests",
        "redigest",
        "publish",
        "skeleton",
        "all",
        "stats",
        "clear-cache",
        "reviews",
        "citations",
        "restructure",
        "setup-model",
        "nlm",
    }
    actual = set(main.commands.keys())
    assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"


def test_config_has_expected_fields():
    """Config dataclass has all documented fields."""
    from dataclasses import fields

    from zsum.config import Config

    expected = {
        "bbt_json",
        "zotero_sqlite",
        "zotero_pdf_base",
        "vault_output",
        "cache_dir",
        "collections",
        "max_first_pages",
        "max_last_pages",
        "max_text_chars",
        "min_text_chars",
        "max_pdf_pages",
        "llm",
        "generate_paper_notes",
        "prompt_version",
        "citations",
        "restructure",
        "extraction",
        "notebooklm",
    }
    actual = {f.name for f in fields(Config)}
    assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"


def test_digest_prompt_has_wikilink_citation_syntax():
    """Digest prompt template must contain [[@citekey]] wikilink citation syntax."""
    from zsum.prompts import load_prompt

    content = load_prompt("collection_digest.txt")
    assert "[[@" in content, "Digest prompt must contain [[@citekey]] wikilink citation syntax"


def test_card_parser_expected_fields():
    """_EXPECTED_LLM_FIELDS locks the strict validation contract."""
    from zsum.cards import _EXPECTED_LLM_FIELDS

    expected = {"problem", "methods", "key_findings", "limitations", "keywords", "paper_type"}
    assert expected == _EXPECTED_LLM_FIELDS


def test_text_quality_enum_values():
    """TextQuality enum has exactly good, degraded, no_pdf."""
    from zsum.models import TextQuality

    expected = {"good", "degraded", "no_pdf", "fallback"}
    actual = {member.value for member in TextQuality}
    assert expected == actual, f"Missing: {expected - actual}, Extra: {actual - expected}"
