"""Tests for the NotebookLM orchestration pipeline."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from tests.helpers import make_test_item
from zsum.config import Config, LLMConfig, LLMProviderConfig, NotebookLMConfig
from zsum.llm import LLMResponse
from zsum.models import Collection, LibraryIndex, PaperCard
from zsum.nlm_pipeline import (
    NotebookLMAuthError,
    _nlm_add_source,
    _nlm_create_notebook,
    _nlm_query,
    cleanup_notebooks,
    compute_direct_members,
    create_collection_notebooks,
    query_paper_card,
    run_nlm_pipeline,
)


def _make_index_for_direct_members() -> LibraryIndex:
    return LibraryIndex(
        collections={
            "ROOT": Collection(
                key="ROOT",
                name="Root",
                item_citekeys=["root-paper", "child-paper", "grand-paper"],
                child_keys=["CHILD"],
            ),
            "CHILD": Collection(
                key="CHILD",
                name="Child",
                parent_key="ROOT",
                item_citekeys=["child-paper", "grand-paper"],
                child_keys=["GRAND"],
            ),
            "GRAND": Collection(
                key="GRAND",
                name="Grand",
                parent_key="CHILD",
                item_citekeys=["grand-paper"],
            ),
        }
    )


def _make_card(item_citekey: str, title: str) -> PaperCard:
    return PaperCard(citekey=item_citekey, title=title, problem=f"Problem for {item_citekey}")


class TestComputeDirectMembers:
    def test_excludes_descendant_members_recursively(self):
        index = _make_index_for_direct_members()

        direct = compute_direct_members(index.collections["ROOT"], index)

        assert direct == ["root-paper"]

    def test_leaf_collection_returns_all_members(self):
        index = _make_index_for_direct_members()

        direct = compute_direct_members(index.collections["GRAND"], index)

        assert direct == ["grand-paper"]

    def test_empty_collection_returns_empty(self):
        index = LibraryIndex(
            collections={
                "EMPTY": Collection(key="EMPTY", name="Empty", item_citekeys=[]),
            }
        )

        direct = compute_direct_members(index.collections["EMPTY"], index)

        assert direct == []


class TestCleanupNotebooks:
    def test_deduplicates_notebook_ids(self):
        config = Config()
        with patch("zsum.nlm_pipeline._nlm_delete_notebook") as mock_delete:
            cleanup_notebooks(["nb-1", "nb-2", "nb-1", "nb-2", "nb-3"], config)

        assert mock_delete.call_count == 3
        deleted_ids = [call.args[0] for call in mock_delete.call_args_list]
        assert deleted_ids == ["nb-1", "nb-2", "nb-3"]

    def test_swallows_deletion_errors(self):
        config = Config()
        with patch(
            "zsum.nlm_pipeline._nlm_delete_notebook",
            side_effect=[None, RuntimeError("API error"), None],
        ) as mock_delete:
            cleanup_notebooks(["nb-1", "nb-2", "nb-3"], config)

        assert mock_delete.call_count == 3


class TestCreateCollectionNotebooks:
    def test_batches_sources_across_multiple_notebooks(self, tmp_path):
        pdf_a = tmp_path / "a.pdf"
        pdf_b = tmp_path / "b.pdf"
        pdf_c = tmp_path / "c.pdf"
        pdf_a.write_text("a")
        pdf_b.write_text("b")
        pdf_c.write_text("c")

        index = LibraryIndex(
            items={
                "a": make_test_item(citekey="a", zotero_key="A", pdf_path=pdf_a, title="Paper A"),
                "b": make_test_item(citekey="b", zotero_key="B", pdf_path=pdf_b, title="Paper B"),
                "c": make_test_item(citekey="c", zotero_key="C", pdf_path=pdf_c, title="Paper C"),
            },
            collections={
                "COL": Collection(
                    key="COL",
                    name="Large Collection",
                    item_citekeys=["a", "b", "c"],
                )
            },
        )
        config = Config(notebooklm=NotebookLMConfig(max_sources_per_notebook=2))

        with (
            patch("zsum.nlm_pipeline._nlm_create_notebook", side_effect=["nb-1", "nb-2"]),
            patch(
                "zsum.nlm_pipeline._nlm_add_source",
                side_effect=["src-1", "src-2", "src-3"],
            ),
        ):
            notebooks = create_collection_notebooks(index.collections["COL"], index, config)

        assert [notebook.notebook_id for notebook in notebooks] == ["nb-1", "nb-2"]
        assert [len(notebook.sources) for notebook in notebooks] == [2, 1]
        assert notebooks[0].title.endswith("(1/2)")
        assert notebooks[1].title.endswith("(2/2)")


class TestNlmCliRetries:
    def test_create_notebook_retries_timeout_then_succeeds(self):
        config = Config(notebooklm=NotebookLMConfig(query_timeout=7.5))
        success = subprocess.CompletedProcess(
            args=["nlm"],
            returncode=0,
            stdout="Notebook created: 123e4567-e89b-42d3-a456-426614174000",
            stderr="",
        )

        with (
            patch(
                "zsum.nlm_pipeline.subprocess.run",
                side_effect=[subprocess.TimeoutExpired(["nlm"], 7.5), success],
            ) as mock_run,
            patch("zsum.nlm_pipeline.time.sleep") as mock_sleep,
        ):
            notebook_id = _nlm_create_notebook("Retry Notebook", config)

        assert notebook_id == "123e4567-e89b-42d3-a456-426614174000"
        assert mock_run.call_count == 2
        mock_sleep.assert_called_once()

    def test_create_notebook_uses_real_cli_subcommand_shape(self):
        config = Config(notebooklm=NotebookLMConfig(profile="work"))
        success = subprocess.CompletedProcess(
            args=["nlm"],
            returncode=0,
            stdout="Notebook created: 123e4567-e89b-42d3-a456-426614174000",
            stderr="",
        )

        with patch("zsum.nlm_pipeline.subprocess.run", return_value=success) as mock_run:
            notebook_id = _nlm_create_notebook("Retry Notebook", config)

        command = mock_run.call_args.args[0]
        assert command[:4] == ["nlm", "notebook", "create", "Retry Notebook"]
        assert command[-2:] == ["--profile", "work"]
        assert notebook_id == "123e4567-e89b-42d3-a456-426614174000"

    def test_add_source_uses_file_upload_cli_shape(self, tmp_path):
        pdf_path = tmp_path / "paper.pdf"
        pdf_path.write_text("pdf")
        config = Config(notebooklm=NotebookLMConfig(upload_timeout=321.0, profile="work"))
        success = subprocess.CompletedProcess(
            args=["nlm"],
            returncode=0,
            stdout="Source id: src-12345",
            stderr="",
        )

        with patch("zsum.nlm_pipeline.subprocess.run", return_value=success) as mock_run:
            source_id = _nlm_add_source(
                "nb-1",
                config,
                file_path=pdf_path,
                title="Paper A",
            )

        command = mock_run.call_args.args[0]
        assert command[:4] == ["nlm", "source", "add", "nb-1"]
        assert "--file" in command and str(pdf_path) in command
        assert "--wait" in command
        assert "--wait-timeout" in command and "321.0" in command
        assert command[-2:] == ["--profile", "work"]
        assert source_id == "src-12345"

    def test_query_raises_auth_error_without_retry(self):
        config = Config()
        auth_failure = subprocess.CompletedProcess(
            args=["nlm"],
            returncode=1,
            stdout="",
            stderr="HTTP 401 Unauthorized - please log in",
        )

        with (
            patch("zsum.nlm_pipeline.subprocess.run", return_value=auth_failure) as mock_run,
            patch("zsum.nlm_pipeline.time.sleep") as mock_sleep,
            pytest.raises(NotebookLMAuthError),
        ):
            _nlm_query("nb-1", "prompt", config)

        command = mock_run.call_args.args[0]
        assert command[:4] == ["nlm", "notebook", "query", "nb-1"]
        assert command[4] == "prompt"
        mock_run.assert_called_once()
        mock_sleep.assert_not_called()


class TestQueryPaperCard:
    def test_can_route_nlm_text_through_local_parser(self):
        item = make_test_item(citekey="local-parse", zotero_key="LP1", title="Local Parse Paper")
        config = Config(
            notebooklm=NotebookLMConfig(parse_locally=True),
            llm=LLMConfig(
                provider="anthropic",
                anthropic=LLMProviderConfig(model="claude-test"),
            ),
        )
        local_json = json.dumps(
            {
                "problem": "NotebookLM summary converted locally.",
                "methods": ["Method A"],
                "key_findings": ["Finding A"],
                "limitations": ["Limitation A"],
                "keywords": ["keyword-a"],
                "paper_type": "research",
            }
        )

        with (
            patch(
                "zsum.nlm_pipeline._nlm_query", return_value="A natural-language NotebookLM answer."
            ),
            patch(
                "zsum.nlm_pipeline.complete_with_retry",
                return_value=LLMResponse(
                    text=local_json,
                    model="claude-test",
                    input_tokens=11,
                    output_tokens=22,
                ),
            ) as mock_complete,
        ):
            card = query_paper_card("nb-1", "src-1", item, config)

        assert card.problem == "NotebookLM summary converted locally."
        assert mock_complete.called


class TestRunNlmPipeline:
    def test_parent_collections_use_child_digests_not_child_papers(self, tmp_path):
        root_pdf = tmp_path / "root.pdf"
        child_pdf = tmp_path / "child.pdf"
        root_pdf.write_text("root")
        child_pdf.write_text("child")

        index = LibraryIndex(
            items={
                "root-paper": make_test_item(
                    citekey="root-paper",
                    zotero_key="ROOT1",
                    title="Root Paper",
                    pdf_path=root_pdf,
                ),
                "child-paper": make_test_item(
                    citekey="child-paper",
                    zotero_key="CHILD1",
                    title="Child Paper",
                    pdf_path=child_pdf,
                ),
            },
            collections={
                "ROOT": Collection(
                    key="ROOT",
                    name="Root Collection",
                    item_citekeys=["root-paper", "child-paper"],
                    child_keys=["CHILD"],
                ),
                "CHILD": Collection(
                    key="CHILD",
                    name="Child Collection",
                    parent_key="ROOT",
                    item_citekeys=["child-paper"],
                ),
            },
        )
        config = Config(notebooklm=NotebookLMConfig(max_sources_per_notebook=3))

        digest_calls: list[dict[str, object]] = []
        notebook_ids: list[str] = []

        def fake_create_notebook(title: str, config: Config) -> str:
            notebook_id = f"nb-{len(notebook_ids) + 1}"
            notebook_ids.append(notebook_id)
            return notebook_id

        def fake_add_source(*args, **kwargs) -> str:
            return f"src-{len(digest_calls) + 1}"

        def fake_query_digest(notebooks, collection, config):
            digest_calls.append(
                {
                    "collection": collection.key,
                    "sources": [
                        (source.kind, source.citekey, source.collection_key, source.title)
                        for notebook in notebooks
                        for source in notebook.sources
                    ],
                }
            )
            return f"Digest for {collection.key}", []

        def fake_query_card(notebook_id: str, source_id: str, item, config):
            return _make_card(item.citekey, item.title)

        with (
            patch("zsum.nlm_pipeline._nlm_create_notebook", side_effect=fake_create_notebook),
            patch("zsum.nlm_pipeline._nlm_add_source", side_effect=fake_add_source),
            patch(
                "zsum.nlm_pipeline._query_collection_digest_with_aggregates",
                side_effect=fake_query_digest,
            ),
            patch("zsum.nlm_pipeline.query_paper_card", side_effect=fake_query_card),
        ):
            result = run_nlm_pipeline(index, config, tmp_path)

        assert [call["collection"] for call in digest_calls] == ["CHILD", "ROOT"]

        root_sources = digest_calls[1]["sources"]
        assert ("paper", "root-paper", None, "root-paper: Root Paper") in root_sources
        assert any(
            kind == "child_digest" and collection_key == "CHILD"
            for kind, _, collection_key, _ in root_sources
        )
        assert not any(
            kind == "paper" and citekey == "child-paper" for kind, citekey, _, _ in root_sources
        )
        assert set(result.cards) == {"root-paper", "child-paper"}
        assert result.digests == {"CHILD": "Digest for CHILD", "ROOT": "Digest for ROOT"}
