"""CLI entry point for zotero-summarizer."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import click

from .config import LLMStage, load_config, validate_config
from .setup_model import setup_model as _setup_model_cmd


def _fmt_elapsed(seconds: float) -> str:
    """Format elapsed seconds as mm:ss or hh:mm:ss."""
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _setup_logging(verbose):
    """Configure root logger level (DEBUG if verbose, else INFO) and timestamped format."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _exit_with_config_errors(errors: list[str]) -> None:
    """Emit config validation errors and exit."""
    for error in errors:
        click.echo(f"Config error: {error}", err=True)
    sys.exit(1)


# Set by the top-level CLI group when --pdf-backend is passed; applied on top of
# the loaded config by _load_cfg. The YAML remains the persistent choice.
_PDF_BACKEND_OVERRIDE: str | None = None


def _load_cfg(
    config_path,
    *,
    require_llm: bool = False,
    llm_stages: tuple[LLMStage, ...] | None = None,
):
    """Load and validate config from path, exiting with an error message if not found or invalid."""
    path = Path(config_path)
    if not path.exists():
        click.echo(f"Config not found: {path}", err=True)
        sys.exit(1)
    cfg = load_config(path)
    if _PDF_BACKEND_OVERRIDE is not None:
        cfg.extraction.backend = _PDF_BACKEND_OVERRIDE
    errors = validate_config(cfg, require_llm=require_llm, llm_stages=llm_stages)
    if errors:
        _exit_with_config_errors(errors)
    return cfg


def _load_cfg_for_notebooklm(config_path, *, require_redigest: bool = False):
    """Load config for NotebookLM-aware commands with dynamic local-LLM validation."""
    cfg = _load_cfg(config_path, require_llm=False)
    llm_stages: list[LLMStage] = []
    if cfg.notebooklm.parse_locally:
        llm_stages.append("cards")
    if require_redigest:
        llm_stages.append("redigest")
    if llm_stages:
        errors = validate_config(cfg, require_llm=True, llm_stages=tuple(llm_stages))
        if errors:
            _exit_with_config_errors(errors)
    return cfg


def _matching_collections(idx, collection):
    """Return collections matching an exact name, key, or path filter."""
    collections = sorted(idx.collections.values(), key=lambda c: c.path)
    if collection is None:
        return collections

    matching = [col for col in collections if collection in (col.name, col.key, col.path)]
    if not matching:
        click.echo(f"No collection matched '{collection}'.", err=True)
        sys.exit(1)
    return matching


def _filter_index_to_collection_subtree(idx, collection):
    """Return a deep-copied index filtered to the matched collection subtree."""
    if collection is None:
        return idx

    matching = _matching_collections(idx, collection)
    allowed_collections: set[str] = set()
    allowed_items: set[str] = set()
    stack = [col.key for col in matching]

    while stack:
        current = stack.pop()
        if current in allowed_collections:
            continue
        allowed_collections.add(current)
        col = idx.collections.get(current)
        if col is None:
            continue
        allowed_items.update(col.item_citekeys)
        stack.extend(col.child_keys)

    filtered = idx.model_copy(deep=True)
    filtered.collections = {
        key: col for key, col in filtered.collections.items() if key in allowed_collections
    }
    filtered.items = {
        citekey: item for citekey, item in filtered.items.items() if citekey in allowed_items
    }
    for col in filtered.collections.values():
        col.child_keys = [key for key in col.child_keys if key in allowed_collections]
        col.item_citekeys = [citekey for citekey in col.item_citekeys if citekey in allowed_items]
        if col.parent_key not in allowed_collections:
            col.parent_key = None
    return filtered


def _mapping_notebook_id(mapping) -> str | None:
    if isinstance(mapping, dict):
        value = mapping.get("notebook_id")
        return value if isinstance(value, str) and value else None
    value = getattr(mapping, "notebook_id", None)
    return value if isinstance(value, str) and value else None


def _mapping_sources(mapping) -> list:
    if isinstance(mapping, dict):
        value = mapping.get("sources", [])
        return value if isinstance(value, list) else []
    value = getattr(mapping, "sources", [])
    return list(value) if value else []


def _mapping_source_value(source, field_name: str) -> str | None:
    if isinstance(source, dict):
        value = source.get(field_name)
        return value if isinstance(value, str) and value else None
    value = getattr(source, field_name, None)
    return value if isinstance(value, str) and value else None


def _mapping_notebook_ids(mappings: dict[str, list]) -> list[str]:
    notebook_ids: list[str] = []
    for notebook_group in mappings.values():
        for mapping in notebook_group:
            notebook_id = _mapping_notebook_id(mapping)
            if notebook_id:
                notebook_ids.append(notebook_id)
    return notebook_ids


def _replace_nlm_mappings(cache_dir: Path, config, *, collection_keys: set[str], new_mappings):
    """Replace cached NotebookLM mappings for the targeted collections."""
    from .cache import clear_nlm_mappings, load_nlm_mappings, save_nlm_mappings
    from .nlm_pipeline import cleanup_notebooks

    existing = load_nlm_mappings(cache_dir)
    stale = {key: existing[key] for key in collection_keys if key in existing}
    stale_ids = _mapping_notebook_ids(stale)
    if stale_ids:
        cleanup_notebooks(stale_ids, config)

    merged = {key: value for key, value in existing.items() if key not in collection_keys}
    merged.update({key: value for key, value in new_mappings.items() if value})
    if merged:
        save_nlm_mappings(merged, cache_dir)
    else:
        clear_nlm_mappings(cache_dir)
    return merged


def _persist_nlm_cards(cards, config) -> None:
    """Save NotebookLM-produced cards to the standard cache location."""
    from .cache import save_card

    cards_dir = config.cache_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    for card in cards.values():
        save_card(card, config, cards_dir)


def _generate_nlm_fallback_cards(failed_citekeys, idx, config):
    """Run page-range extraction + local LLM cards for NotebookLM-failed papers.

    Each generated card is tagged ``extraction_method="fallback_pages"`` and persisted to
    the standard cards cache. Returns the dict of cards generated (citekey → PaperCard).
    If the local LLM is unavailable, logs a warning and returns an empty dict.
    """
    from dataclasses import replace

    from .cards import generate_cards_batch
    from .extractor import extract_batch

    logger = logging.getLogger(__name__)
    failed = [ck for ck in failed_citekeys if ck in idx.items]
    if not failed:
        return {}

    errors = validate_config(config, require_llm=True, llm_stages=("cards",))
    if errors:
        logger.warning(
            "Skipping NotebookLM fallback for %d failed papers: local LLM not configured (%s)",
            len(failed),
            "; ".join(errors),
        )
        return {}

    pages_extraction = replace(config.extraction, mode="pages")
    pages_config = replace(config, extraction=pages_extraction)

    items_subset = {ck: idx.items[ck] for ck in failed}
    extractions = extract_batch(items_subset, pages_config)
    for extraction in extractions.values():
        extraction.extraction_method = "fallback_pages"
        extraction.warnings.append("Fell back to page-range extraction (NotebookLM failed)")

    cards = generate_cards_batch(items_subset, extractions, pages_config, config.cache_dir)
    fallback_cards = {ck: card for ck, card in cards.items() if ck in items_subset}
    logger.info("NotebookLM fallback produced %d cards for failed papers", len(fallback_cards))
    return fallback_cards


def _persist_nlm_digests(idx, digests, cards, cache_dir: Path) -> None:
    """Save NotebookLM-produced digests and their card hash sidecars."""
    from .cache import load_nlm_digest_keys, save_digest_hashes, save_nlm_digest_keys

    digests_dir = cache_dir / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    cards_dir = cache_dir / "cards"
    available_cards = set(cards)
    for collection_key, digest in digests.items():
        (digests_dir / f"{collection_key}.md").write_text(digest, encoding="utf-8")
        collection = idx.collections.get(collection_key)
        citekeys = []
        if collection is not None:
            citekeys = [ck for ck in collection.item_citekeys if ck in available_cards]
        save_digest_hashes(collection_key, citekeys, cards_dir, digests_dir)
    existing_keys = load_nlm_digest_keys(cache_dir)
    save_nlm_digest_keys(existing_keys | set(digests.keys()), cache_dir)


def _prepare_nlm_redigests(cache_dir: Path, target_keys: set[str], *, force: bool = False) -> None:
    """Remove redigest artifacts that do not belong to NotebookLM mode for the target keys."""
    from .cache import load_nlm_redigest_keys

    existing_redigest_keys = load_nlm_redigest_keys(cache_dir)
    stale_keys = target_keys if force else target_keys - existing_redigest_keys
    redigests_dir = cache_dir / "redigests"
    if not redigests_dir.exists():
        return
    for collection_key in stale_keys:
        redigest_path = redigests_dir / f"{collection_key}.md"
        metadata_path = redigests_dir / f"{collection_key}.json"
        if redigest_path.exists():
            redigest_path.unlink()
        if metadata_path.exists():
            metadata_path.unlink()


def _update_nlm_redigest_manifest(
    cache_dir: Path, target_keys: set[str], redigest_keys: set[str]
) -> None:
    """Replace the NotebookLM redigest manifest entries for the targeted collections."""
    from .cache import load_nlm_redigest_keys, save_nlm_redigest_keys

    existing_redigest_keys = load_nlm_redigest_keys(cache_dir)
    save_nlm_redigest_keys((existing_redigest_keys - target_keys) | redigest_keys, cache_dir)


def _run_nlm_upload_stage(idx, config, *, collection=None):
    """Create notebooks for direct-member uploads and persist their mappings."""
    from .nlm_pipeline import create_collection_notebooks

    process_idx = _filter_index_to_collection_subtree(idx, collection)
    created: dict[str, list] = {}
    for collection_key in process_idx.collections:
        notebooks = create_collection_notebooks(
            process_idx.collections[collection_key],
            process_idx,
            config,
        )
        if notebooks:
            created[collection_key] = notebooks

    _replace_nlm_mappings(
        config.cache_dir,
        config,
        collection_keys=set(process_idx.collections.keys()),
        new_mappings=created,
    )
    notebook_count = sum(len(notebooks) for notebooks in created.values())
    source_count = sum(
        len(_mapping_sources(notebook)) for notebooks in created.values() for notebook in notebooks
    )
    return notebook_count, source_count


def _run_nlm_cards_stage(idx, config, *, collection=None, force: bool = False):
    """Generate cards from NotebookLM notebook mappings, creating mappings if needed."""
    from .cache import (
        load_cached_cards,
        load_nlm_mappings,
        load_version_matched_citekeys,
        save_nlm_mappings,
    )
    from .digests import _bottom_up_order
    from .nlm_pipeline import create_collection_notebooks, query_paper_card

    process_idx = _filter_index_to_collection_subtree(idx, collection)
    target_keys = set(process_idx.collections.keys())

    existing = {} if force else load_nlm_mappings(config.cache_dir)
    if force:
        _replace_nlm_mappings(
            config.cache_dir,
            config,
            collection_keys=target_keys,
            new_mappings={},
        )

    new_mappings: dict[str, list] = {}
    notebooks_by_collection: dict[str, list] = {}
    for collection_key in _bottom_up_order(process_idx):
        notebooks: list = existing.get(collection_key) or []
        if not notebooks:
            notebooks = create_collection_notebooks(
                process_idx.collections[collection_key],
                process_idx,
                config,
            )
            if notebooks:
                new_mappings[collection_key] = notebooks
        notebooks_by_collection[collection_key] = notebooks or []

    if new_mappings:
        merged = {key: value for key, value in existing.items() if key not in new_mappings}
        merged.update(new_mappings)
        save_nlm_mappings(merged, config.cache_dir)

    cached_cards = {} if force else load_cached_cards(config.cache_dir)
    version_matched = (
        set() if force else load_version_matched_citekeys(config.cache_dir, config.prompt_version)
    )
    cards = {
        citekey: card
        for citekey, card in cached_cards.items()
        if citekey in process_idx.items
        and citekey in version_matched
        and card.extraction_method == "notebooklm"
    }
    skip = set(cards)
    generated_cards = {}

    for collection_key in _bottom_up_order(process_idx):
        for notebook in notebooks_by_collection.get(collection_key, []):
            notebook_id = _mapping_notebook_id(notebook)
            if not notebook_id:
                continue
            for source in _mapping_sources(notebook):
                if _mapping_source_value(source, "kind") != "paper":
                    continue
                citekey = _mapping_source_value(source, "citekey")
                source_id = _mapping_source_value(source, "source_id")
                if not citekey or not source_id or citekey in skip or citekey in generated_cards:
                    continue
                item = process_idx.items.get(citekey)
                if item is None:
                    continue
                generated_cards[citekey] = query_paper_card(notebook_id, source_id, item, config)

    if generated_cards:
        _persist_nlm_cards(generated_cards, config)
    cards.update(generated_cards)
    return cards


def _run_nlm_digests_stage(idx, config, *, collection=None, force: bool = False):
    """Generate collection digests with NotebookLM and persist fresh notebook mappings."""
    from .cache import load_cached_cards
    from .digests import _bottom_up_order
    from .nlm_pipeline import create_collection_notebooks, query_collection_digest

    process_idx = _filter_index_to_collection_subtree(idx, collection)
    target_keys = set(process_idx.collections.keys())
    digests_dir = config.cache_dir / "digests"
    digests_dir.mkdir(parents=True, exist_ok=True)
    if force:
        for collection_key in target_keys:
            digest_path = digests_dir / f"{collection_key}.md"
            hash_path = digests_dir / f"{collection_key}_hashes.json"
            if digest_path.exists():
                digest_path.unlink()
            if hash_path.exists():
                hash_path.unlink()

    cards = {
        citekey: card
        for citekey, card in load_cached_cards(config.cache_dir).items()
        if card.extraction_method == "notebooklm"
    }

    digests = {}
    child_digests: dict[str, str] = {}
    new_mappings: dict[str, list] = {}

    for collection_key in _bottom_up_order(process_idx):
        collection_obj = process_idx.collections[collection_key]
        notebooks = create_collection_notebooks(
            collection_obj,
            process_idx,
            config,
            child_digests=child_digests,
        )
        if not notebooks:
            continue

        digest = query_collection_digest(notebooks, collection_obj, config)
        digests[collection_key] = digest
        child_digests[collection_key] = digest
        new_mappings[collection_key] = notebooks

    if digests:
        _persist_nlm_digests(process_idx, digests, cards, config.cache_dir)
    _replace_nlm_mappings(
        config.cache_dir,
        config,
        collection_keys=target_keys,
        new_mappings=new_mappings,
    )
    from .cache import load_nlm_digest_keys, save_nlm_digest_keys

    existing_digest_keys = load_nlm_digest_keys(config.cache_dir)
    save_nlm_digest_keys(
        (existing_digest_keys - target_keys) | set(digests.keys()), config.cache_dir
    )
    return digests


def _run_nlm_all_stage(idx, config, *, collection=None):
    """Run the full NotebookLM card+digest stage and persist its cache outputs."""
    from .nlm_pipeline import run_nlm_pipeline

    process_idx = _filter_index_to_collection_subtree(idx, collection)
    result = run_nlm_pipeline(process_idx, config, config.cache_dir)
    if result.cards:
        _persist_nlm_cards(result.cards, config)
    if result.failed_papers:
        fallback_cards = _generate_nlm_fallback_cards(result.failed_papers, process_idx, config)
        if fallback_cards:
            result.cards.update(fallback_cards)
    if result.digests:
        _persist_nlm_digests(process_idx, result.digests, result.cards, config.cache_dir)

    target_keys = set(process_idx.collections.keys())
    persisted_mappings = {} if config.notebooklm.cleanup else result.mappings
    _replace_nlm_mappings(
        config.cache_dir,
        config,
        collection_keys=target_keys,
        new_mappings=persisted_mappings,
    )
    from .cache import load_nlm_digest_keys, save_nlm_digest_keys

    existing_digest_keys = load_nlm_digest_keys(config.cache_dir)
    save_nlm_digest_keys(
        (existing_digest_keys - target_keys) | set(result.digests.keys()), config.cache_dir
    )
    return result


@click.group()
@click.option("--config", "config_path", default="config.yaml")
@click.option(
    "--pdf-backend",
    type=click.Choice(["pdfminer", "pymupdf"]),
    default=None,
    help="Override extraction.backend from config.yaml for this invocation.",
)
@click.option("-v", "--verbose", is_flag=True)
@click.pass_context
def main(ctx, config_path, pdf_backend, verbose):
    """zsum - Zotero Collection Summarizer."""
    global _PDF_BACKEND_OVERRIDE
    _setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    if pdf_backend is not None:
        _PDF_BACKEND_OVERRIDE = pdf_backend


main.add_command(_setup_model_cmd)


@main.group()
@click.pass_context
def nlm(ctx):
    """NotebookLM-specific upload/query/status helpers."""
    ctx.ensure_object(dict)


@nlm.command(name="upload")
@click.option("--collection", default=None, help="Filter to a single collection subtree.")
@click.pass_context
def nlm_upload(ctx, collection):
    """Create NotebookLM notebooks and upload sources for the selected collections."""
    cfg = _load_cfg_for_notebooklm(ctx.obj["config_path"])
    from .cache import save_membership, save_plugin_index
    from .indexer import build_index

    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    notebook_count, source_count = _run_nlm_upload_stage(idx, cfg, collection=collection)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(
        f"Uploaded {source_count} sources into {notebook_count} NotebookLM notebook"
        f"{'s' if notebook_count != 1 else ''}."
    )


@nlm.command(name="cards")
@click.option("--collection", default=None, help="Filter to a single collection subtree.")
@click.option("--force", is_flag=True)
@click.pass_context
def nlm_cards(ctx, collection, force):
    """Generate paper cards from NotebookLM notebooks."""
    cfg = _load_cfg_for_notebooklm(ctx.obj["config_path"])
    from .cache import save_membership, save_plugin_index
    from .indexer import build_index

    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    cards = _run_nlm_cards_stage(idx, cfg, collection=collection, force=force)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"Total cards: {len(cards)}")


@nlm.command(name="digests")
@click.option("--collection", default=None, help="Filter to a single collection subtree.")
@click.option("--force", is_flag=True)
@click.pass_context
def nlm_digests(ctx, collection, force):
    """Generate collection digests through NotebookLM."""
    cfg = _load_cfg_for_notebooklm(ctx.obj["config_path"])
    from .cache import save_membership, save_plugin_index
    from .indexer import build_index

    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    digests = _run_nlm_digests_stage(idx, cfg, collection=collection, force=force)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"Total digests: {len(digests)}")


@nlm.command(name="all")
@click.option("--collection", default=None, help="Filter to a single collection subtree.")
@click.pass_context
def nlm_all(ctx, collection):
    """Run the full NotebookLM card+digest stage and persist its outputs."""
    cfg = _load_cfg_for_notebooklm(ctx.obj["config_path"])
    from .cache import save_membership, save_plugin_index
    from .indexer import build_index

    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    result = _run_nlm_all_stage(idx, cfg, collection=collection)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(
        f"NotebookLM complete: {len(result.cards)} cards, {len(result.digests)} digests, "
        f"{len(dict.fromkeys(result.notebooks_created))} notebook"
        f"{'s' if len(dict.fromkeys(result.notebooks_created)) != 1 else ''}."
    )


@nlm.command(name="status")
@click.pass_context
def nlm_status(ctx):
    """Show cached NotebookLM notebook/source/card/digest counts."""
    cfg = _load_cfg_for_notebooklm(ctx.obj["config_path"])
    from .cache import load_cached_cards, load_nlm_digest_keys, load_nlm_mappings

    mappings = load_nlm_mappings(cfg.cache_dir)
    notebook_ids = list(dict.fromkeys(_mapping_notebook_ids(mappings)))
    source_count = sum(
        len(_mapping_sources(notebook)) for notebooks in mappings.values() for notebook in notebooks
    )
    notebooklm_card_count = sum(
        1
        for card in load_cached_cards(cfg.cache_dir).values()
        if card.extraction_method == "notebooklm"
    )
    notebooklm_digest_count = len(load_nlm_digest_keys(cfg.cache_dir))
    click.echo(f"NotebookLM collections: {len(mappings)}")
    click.echo(f"NotebookLM notebooks: {len(notebook_ids)}")
    click.echo(f"NotebookLM sources: {source_count}")
    click.echo(f"NotebookLM cards: {notebooklm_card_count}")
    click.echo(f"NotebookLM digests: {notebooklm_digest_count}")


@nlm.command(name="cleanup")
@click.pass_context
def nlm_cleanup(ctx):
    """Delete cached NotebookLM notebooks and clear saved mapping state."""
    cfg = _load_cfg_for_notebooklm(ctx.obj["config_path"])
    from .cache import clear_nlm_mappings, load_nlm_mappings
    from .nlm_pipeline import cleanup_notebooks

    mappings = load_nlm_mappings(cfg.cache_dir)
    notebook_ids = list(dict.fromkeys(_mapping_notebook_ids(mappings)))
    if not notebook_ids:
        click.echo("No cached NotebookLM notebooks.")
        return

    cleanup_notebooks(notebook_ids, cfg)
    clear_nlm_mappings(cfg.cache_dir)
    click.echo(
        f"Deleted {len(notebook_ids)} NotebookLM notebook{'s' if len(notebook_ids) != 1 else ''}."
    )


@main.command()
@click.pass_context
def index(ctx):
    """Build index and print stats."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .cache import save_membership
    from .indexer import build_index

    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    s = idx.stats
    click.echo(f"Items: {s['total_items']} ({s['with_pdf']} with PDF)")
    click.echo(f"Collections: {s['total_collections']}")
    for col in sorted(idx.collections.values(), key=lambda c: c.path):
        click.echo(f"  {col.path} ({len(col.item_citekeys)} papers)")


@main.command()
@click.pass_context
def extract(ctx):
    """Dry run: show extraction quality."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .extractor import extract_batch, extraction_report
    from .indexer import build_index

    idx = build_index(cfg)
    click.echo(extraction_report(extract_batch(idx.items, cfg)))


@main.command()
@click.option("--force", is_flag=True)
@click.pass_context
def cards(ctx, force):
    """Generate paper cards using LLM."""
    cfg = _load_cfg(ctx.obj["config_path"], require_llm=False)
    if cfg.extraction.mode == "notebooklm":
        if cfg.notebooklm.parse_locally:
            errors = validate_config(cfg, require_llm=True, llm_stages=("cards",))
            if errors:
                _exit_with_config_errors(errors)
        from .cache import save_membership, save_plugin_index
        from .indexer import build_index

        idx = build_index(cfg)
        save_membership(idx, cfg.cache_dir)
        result = _run_nlm_cards_stage(idx, cfg, force=force)
        save_plugin_index(idx, cfg.cache_dir, cfg)
        click.echo(f"Total cards: {len(result)}")
        return

    errors = validate_config(cfg, require_llm=True, llm_stages=("cards",))
    if errors:
        _exit_with_config_errors(errors)
    from .cache import extraction_signature, load_version_matched_citekeys, save_plugin_index
    from .cards import generate_cards_batch
    from .extractor import extract_batch
    from .indexer import build_index

    idx = build_index(cfg)
    skip = (
        set()
        if force
        else load_version_matched_citekeys(
            cfg.cache_dir, cfg.prompt_version, extraction_signature(cfg)
        )
    )
    exts = extract_batch(idx.items, cfg, skip_citekeys=skip)
    result = generate_cards_batch(idx.items, exts, cfg, cfg.cache_dir)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"Total cards: {len(result)}")


@main.command()
@click.option("--force", is_flag=True)
@click.pass_context
def digests(ctx, force):
    """Generate collection digests using LLM."""
    cfg = _load_cfg(ctx.obj["config_path"], require_llm=False)
    if cfg.extraction.mode == "notebooklm":
        from .cache import save_membership, save_plugin_index
        from .indexer import build_index

        idx = build_index(cfg)
        save_membership(idx, cfg.cache_dir)
        result = _run_nlm_digests_stage(idx, cfg, force=force)
        save_plugin_index(idx, cfg.cache_dir, cfg)
        click.echo(f"Total digests: {len(result)}")
        return

    errors = validate_config(cfg, require_llm=True, llm_stages=("digests",))
    if errors:
        _exit_with_config_errors(errors)
    from .cache import load_cached_cards, save_plugin_index
    from .digests import generate_digests_batch
    from .indexer import build_index

    idx = build_index(cfg)
    if force:
        d = cfg.cache_dir / "digests"
        if d.exists():
            for f in d.glob("*.md"):
                f.unlink()
    result = generate_digests_batch(idx, load_cached_cards(cfg.cache_dir), cfg, cfg.cache_dir)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"Total digests: {len(result)}")


@main.command()
@click.option("--collection", default=None, help="Filter to a single collection (by name or key).")
@click.option("--force", is_flag=True)
@click.pass_context
def redigest(ctx, collection, force):
    """Refine cached first-pass digests into final publish-ready digests."""
    cfg = _load_cfg(ctx.obj["config_path"], require_llm=True, llm_stages=("redigest",))
    from .cache import load_cached_cards, load_cached_digests, save_plugin_index
    from .digests import generate_redigests_batch
    from .indexer import build_index

    idx = build_index(cfg)
    matching = _matching_collections(idx, collection)
    if cfg.extraction.mode == "notebooklm":
        _prepare_nlm_redigests(cfg.cache_dir, {col.key for col in matching}, force=force)
    result = generate_redigests_batch(
        idx,
        load_cached_digests(cfg.cache_dir),
        cfg,
        cfg.cache_dir,
        cards=load_cached_cards(cfg.cache_dir),
        collections=matching,
        force=force,
    )
    for col_name in result.missing_first_pass:
        click.echo(
            "Warning: no first-pass digest for "
            f"'{col_name}'. Run `zsum digests` first or "
            f'`zsum digests --collection "{col_name}"`.',
            err=True,
        )
    if cfg.extraction.mode == "notebooklm":
        _update_nlm_redigest_manifest(
            cfg.cache_dir,
            {col.key for col in matching},
            set(result.redigests.keys()),
        )
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(
        f"Total redigests: {len(result.redigests)} "
        f"({result.generated} generated, {result.cached} cached, "
        f"{len(result.missing_first_pass)} skipped missing first-pass digests, "
        f"{result.failed} failed)"
    )


@main.command()
@click.pass_context
def publish(ctx):
    """Write Obsidian vault from cached cards and digests."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .cache import (
        load_cached_cards,
        load_citations,
        load_effective_digests,
        load_nlm_digest_keys,
        load_nlm_redigest_keys,
        save_plugin_index,
    )
    from .indexer import build_index
    from .publisher import publish_vault

    idx = build_index(cfg)
    cards = load_cached_cards(cfg.cache_dir)
    if cfg.extraction.mode == "notebooklm":
        notebooklm_collection_keys = load_nlm_digest_keys(cfg.cache_dir)
        notebooklm_citekeys = {
            citekey
            for collection_key in notebooklm_collection_keys
            for citekey in idx.collections.get(collection_key, ()).item_citekeys
        }
        cards = {
            citekey: card
            for citekey, card in cards.items()
            if card.extraction_method in {"notebooklm", "fallback_pages"}
            and citekey in notebooklm_citekeys
        }
        digests = load_effective_digests(
            cfg.cache_dir,
            notebooklm_collection_keys,
            load_nlm_redigest_keys(cfg.cache_dir),
        )
    else:
        digests = load_effective_digests(cfg.cache_dir)
    citations = load_citations(cfg.cache_dir)
    publish_vault(idx, cfg, cards=cards, digests=digests, citations=citations)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"Vault written to {cfg.vault_output}")


@main.command()
@click.pass_context
def skeleton(ctx):
    """Phase A: vault skeleton, no LLM."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .cache import save_membership, save_plugin_index
    from .extractor import extract_batch, extraction_report
    from .indexer import build_index
    from .publisher import publish_vault

    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    click.echo(extraction_report(extract_batch(idx.items, cfg)))
    publish_vault(idx, cfg)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"Skeleton vault written to {cfg.vault_output}")


@main.command(name="all")
@click.pass_context
def run_all(ctx):
    """Full pipeline: index, cards, digests, publish."""
    cfg = _load_cfg(ctx.obj["config_path"], require_llm=False)
    if cfg.extraction.mode == "notebooklm":
        llm_stages: list[LLMStage] = ["redigest"]
        if cfg.notebooklm.parse_locally:
            llm_stages.insert(0, "cards")
        errors = validate_config(cfg, require_llm=True, llm_stages=tuple(llm_stages))
        if errors:
            _exit_with_config_errors(errors)

        from .cache import (
            load_citations,
            load_effective_digests,
            save_membership,
            save_plugin_index,
        )
        from .digests import generate_redigests_batch
        from .indexer import build_index
        from .publisher import publish_vault

        t0 = time.monotonic()

        click.echo("1/4 Index...")
        idx = build_index(cfg)
        save_membership(idx, cfg.cache_dir)
        s = idx.stats
        click.echo(
            f"  ✓ {s['total_items']} items ({s['with_pdf']} PDF), "
            f"{s['total_collections']} collections [{_fmt_elapsed(time.monotonic() - t0)}]"
        )

        t1 = time.monotonic()
        click.echo("2/4 NotebookLM...")
        nlm_result = _run_nlm_all_stage(idx, cfg)
        click.echo(
            f"  ✓ {len(nlm_result.cards)}/{s['total_items']} cards, "
            f"{len(nlm_result.digests)}/{s['total_collections']} digests "
            f"[{_fmt_elapsed(time.monotonic() - t1)}]"
        )

        t2 = time.monotonic()
        click.echo("3/4 Redigest...")
        _prepare_nlm_redigests(cfg.cache_dir, set(nlm_result.digests.keys()))
        redigest_result = generate_redigests_batch(
            idx,
            nlm_result.digests,
            cfg,
            cfg.cache_dir,
            cards=nlm_result.cards,
        )
        _update_nlm_redigest_manifest(
            cfg.cache_dir,
            set(nlm_result.digests.keys()),
            set(redigest_result.redigests.keys()),
        )
        click.echo(
            f"  ✓ {len(redigest_result.redigests)}/{s['total_collections']} redigests "
            f"({redigest_result.generated} generated, {redigest_result.cached} cached, "
            f"{len(redigest_result.missing_first_pass)} skipped) "
            f"[{_fmt_elapsed(time.monotonic() - t2)}]"
        )

        t3 = time.monotonic()
        click.echo("4/4 Publish...")
        citations = load_citations(cfg.cache_dir)
        effective_digests = dict(nlm_result.digests)
        effective_digests.update(redigest_result.redigests)
        publish_vault(
            idx,
            cfg,
            cards=nlm_result.cards,
            digests=effective_digests,
            citations=citations,
        )
        save_plugin_index(idx, cfg.cache_dir, cfg)
        click.echo(f"  ✓ Published to {cfg.vault_output} [{_fmt_elapsed(time.monotonic() - t3)}]")

        click.echo(
            f"Done! {len(nlm_result.cards)} cards, {len(nlm_result.digests)} digests, "
            f"{len(redigest_result.redigests)} redigests "
            f"in {_fmt_elapsed(time.monotonic() - t0)}"
        )
        return

    errors = validate_config(
        cfg,
        require_llm=True,
        llm_stages=("cards", "digests", "redigest"),
    )
    if errors:
        _exit_with_config_errors(errors)
    from .cache import (
        extraction_signature,
        load_citations,
        load_effective_digests,
        load_version_matched_citekeys,
        save_membership,
        save_plugin_index,
    )
    from .cards import generate_cards_batch
    from .digests import generate_digests_batch, generate_redigests_batch
    from .extractor import extract_batch
    from .indexer import build_index
    from .publisher import publish_vault

    t0 = time.monotonic()

    click.echo("1/6 Index...")
    idx = build_index(cfg)
    save_membership(idx, cfg.cache_dir)
    s = idx.stats
    click.echo(
        f"  ✓ {s['total_items']} items ({s['with_pdf']} PDF), "
        f"{s['total_collections']} collections [{_fmt_elapsed(time.monotonic() - t0)}]"
    )

    t1 = time.monotonic()
    click.echo("2/6 Extract...")
    skip = load_version_matched_citekeys(
        cfg.cache_dir, cfg.prompt_version, extraction_signature(cfg)
    )
    exts = extract_batch(idx.items, cfg, skip_citekeys=skip)
    good = sum(1 for r in exts.values() if r.quality == "good")
    click.echo(
        f"  ✓ {len(exts)} extracted ({good} good, {len(skip)} cached)"
        f" [{_fmt_elapsed(time.monotonic() - t1)}]"
    )

    t2 = time.monotonic()
    click.echo("3/6 Cards...")
    all_cards = generate_cards_batch(idx.items, exts, cfg, cfg.cache_dir)
    click.echo(
        f"  ✓ {len(all_cards)}/{s['total_items']} cards [{_fmt_elapsed(time.monotonic() - t2)}]"
    )

    t3 = time.monotonic()
    click.echo("4/6 Digests...")
    all_digests = generate_digests_batch(idx, all_cards, cfg, cfg.cache_dir)
    click.echo(
        f"  ✓ {len(all_digests)}/{s['total_collections']} digests"
        f" [{_fmt_elapsed(time.monotonic() - t3)}]"
    )

    t4 = time.monotonic()
    click.echo("5/6 Redigest...")
    redigest_result = generate_redigests_batch(
        idx,
        all_digests,
        cfg,
        cfg.cache_dir,
        cards=all_cards,
    )
    click.echo(
        f"  ✓ {len(redigest_result.redigests)}/{s['total_collections']} redigests "
        f"({redigest_result.generated} generated, {redigest_result.cached} cached, "
        f"{len(redigest_result.missing_first_pass)} skipped) "
        f"[{_fmt_elapsed(time.monotonic() - t4)}]"
    )

    t5 = time.monotonic()
    click.echo("6/6 Publish...")
    citations = load_citations(cfg.cache_dir)
    effective_digests = load_effective_digests(cfg.cache_dir)
    publish_vault(idx, cfg, cards=all_cards, digests=effective_digests, citations=citations)
    save_plugin_index(idx, cfg.cache_dir, cfg)
    click.echo(f"  ✓ Published to {cfg.vault_output} [{_fmt_elapsed(time.monotonic() - t5)}]")

    click.echo(
        f"Done! {len(all_cards)} cards, {len(all_digests)} digests, "
        f"{len(redigest_result.redigests)} redigests "
        f"in {_fmt_elapsed(time.monotonic() - t0)}"
    )


@main.command()
@click.pass_context
def stats(ctx):
    """Show counts."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .cache import load_cached_cards, load_cached_digests
    from .indexer import build_index

    idx = build_index(cfg)
    cc, cd = load_cached_cards(cfg.cache_dir), load_cached_digests(cfg.cache_dir)
    s = idx.stats
    click.echo(f"Items: {s['total_items']} ({s['with_pdf']} PDF)")
    click.echo(f"Collections: {s['total_collections']}")
    click.echo(f"Cards: {len(cc)} cached, {s['total_items'] - len(cc)} pending")
    click.echo(f"Digests: {len(cd)} cached")


@main.command()
@click.option("--collection", default=None, help="Filter to a single collection (by name or key).")
@click.option("--top", "top_n", default=None, type=int, help="Show only top-N most cited.")
@click.option("--refresh", is_flag=True, help="Force re-fetch even if cached entries are fresh.")
@click.pass_context
def citations(ctx, collection, top_n, refresh):
    """Fetch or display citation counts from OpenAlex / Semantic Scholar."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .cache import save_plugin_index
    from .citations import fetch_citations_batch, top_n_by_citations
    from .indexer import build_index

    idx = build_index(cfg)

    if not cfg.citations.enabled:
        click.echo("Citations are disabled in config (citations.enabled = false).")
        return

    filtered_items = idx.items
    if collection:
        matching = [c for c in idx.collections.values() if collection in (c.name, c.key, c.path)]
        if not matching:
            click.echo(f"No collection matched '{collection}'.", err=True)
            sys.exit(1)
        allowed = {ck for c in matching for ck in c.item_citekeys}
        filtered_items = {ck: it for ck, it in idx.items.items() if ck in allowed}

    records = fetch_citations_batch(filtered_items, cfg, cfg.cache_dir, refresh=refresh)
    save_plugin_index(idx, cfg.cache_dir, cfg)

    requested = top_n if top_n is not None else cfg.citations.top_n
    top = top_n_by_citations(records, list(filtered_items), requested)
    if not top:
        click.echo("No citation counts available.")
        return

    click.echo(f"Top {len(top)} most-cited papers:")
    for citekey, count in top:
        item = idx.items[citekey]
        year = item.year or "n.d."
        click.echo(f"  {count:>6}  @{citekey} ({year}) {item.title}")


@main.command()
@click.option("--collection", default=None, help="Filter to a single collection (by name or key).")
@click.pass_context
def reviews(ctx, collection):
    """List review/survey/meta-analysis papers detected by the classifier."""
    cfg = _load_cfg(ctx.obj["config_path"])
    from .cache import load_cached_cards
    from .indexer import build_index

    idx = build_index(cfg)
    cards = load_cached_cards(cfg.cache_dir)

    # Build citekey -> effective paper_type (card overrides item).
    effective_type: dict[str, str] = {}
    for ck, item in idx.items.items():
        card = cards.get(ck)
        effective_type[ck] = card.paper_type if card else item.paper_type

    review_set = {"review", "survey", "meta-analysis"}
    review_keys = {ck for ck, pt in effective_type.items() if pt in review_set}

    if not review_keys:
        click.echo("No review papers detected.")
        return

    # Group by collection path; optionally filter.
    cols = sorted(idx.collections.values(), key=lambda c: c.path)
    total_shown = 0
    for col in cols:
        if collection and collection not in (col.name, col.key, col.path):
            continue
        col_reviews = [ck for ck in sorted(col.item_citekeys) if ck in review_keys]
        if not col_reviews:
            continue
        click.echo(
            f"\n{col.path} ({len(col_reviews)} review{'s' if len(col_reviews) != 1 else ''})"
        )
        for ck in col_reviews:
            item = idx.items[ck]
            pt = effective_type[ck]
            year = item.year or "n.d."
            venue = f" — {item.venue}" if item.venue else ""
            click.echo(f"  [{pt}] @{ck} ({year}) {item.title}{venue}")
            total_shown += 1

    if total_shown == 0 and collection:
        click.echo(f"No review papers in collection '{collection}'.")
    else:
        click.echo(f"\nTotal: {total_shown} review paper{'s' if total_shown != 1 else ''}.")


@main.command()
@click.option("--collection", default=None, help="Restrict advice to a single collection subtree.")
@click.option(
    "--output", "output_path", default=None, type=click.Path(), help="Write report to file."
)
@click.pass_context
def restructure(ctx, collection, output_path):
    """Generate an advisory report on the collection hierarchy (no write-back)."""
    cfg = _load_cfg(ctx.obj["config_path"], require_llm=True, llm_stages=("digests",))
    from .cache import load_cached_cards, load_cached_digests
    from .indexer import build_index
    from .restructure import advise_structure, render_advice_report, save_advice

    idx = build_index(cfg)
    if collection:
        matching = [c for c in idx.collections.values() if collection in (c.name, c.key, c.path)]
        if not matching:
            click.echo(f"No collection matched '{collection}'.", err=True)
            sys.exit(1)
        allowed = {c.key for c in matching}
        for m in matching:
            stack = [m.key]
            while stack:
                k = stack.pop()
                allowed.add(k)
                stack.extend(idx.collections[k].child_keys)
        idx.collections = {k: v for k, v in idx.collections.items() if k in allowed}

    digests = load_cached_digests(cfg.cache_dir)
    cards = load_cached_cards(cfg.cache_dir)
    if not digests:
        click.echo(
            "Warning: no cached digests found. The advisor works best after `zsum digests`;"
            " falling back to paper titles and keywords.",
            err=True,
        )

    advice = advise_structure(idx, digests, cards, cfg)
    report = render_advice_report(advice, idx)
    save_advice(advice, report, cfg.cache_dir)

    if output_path:
        Path(output_path).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output_path}")
    else:
        click.echo(report)


@main.command(name="clear-cache")
@click.option("--cards", "cc", is_flag=True)
@click.option("--digests", "cd", is_flag=True)
@click.option("--all", "ca", is_flag=True)
@click.pass_context
def clear_cache(ctx, cc, cd, ca):
    """Clear cached data."""
    import shutil

    cfg = _load_cfg(ctx.obj["config_path"])
    if ca:
        from .cache import clear_nlm_digest_keys, clear_nlm_mappings, clear_nlm_redigest_keys

        clear_nlm_mappings(cfg.cache_dir)
        clear_nlm_digest_keys(cfg.cache_dir)
        clear_nlm_redigest_keys(cfg.cache_dir)
    if ca or cc:
        d = cfg.cache_dir / "cards"
        if d.exists():
            n = len(list(d.glob("*.json")))
            shutil.rmtree(d)
            d.mkdir()
            click.echo(f"Cleared {n} cards")
    if ca or cd:
        d = cfg.cache_dir / "digests"
        if d.exists():
            n_digests = len(list(d.glob("*.md")))
            n_hashes = len(list(d.glob("*.json")))
            shutil.rmtree(d)
            d.mkdir()
            click.echo(f"Cleared {n_digests} digests, {n_hashes} hash files")
    if not (ca or cc or cd):
        click.echo("Specify --cards, --digests, or --all")
