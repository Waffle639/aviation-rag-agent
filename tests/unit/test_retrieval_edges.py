import json
from unittest import mock


def test_source_file_helpers_reject_external_paths_and_generate_candidates(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]

        assert retrieval._document_id_from_source_file("outside/file.txt") is None
        assert list(retrieval._candidate_source_files({})) == []
        assert list(
            retrieval._candidate_source_files(
                {"aircraft": "Airbus A320", "font": "Wikipedia"}
            )
        ) == ["data/raw/wiki/Airbus A320.txt", "data/raw/wiki/Airbus_A320.txt"]
        assert list(
            retrieval._candidate_source_files(
                {"aircraft": "A320", "font": "pdf_text"}
            )
        ) == ["data/raw/pdf_to_txt/A320.txt"]


def test_manifest_metadata_wins_over_fallback_hash(import_fresh, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "path": "data/raw/wiki/A320.txt",
                        "document_id": "manifest-id",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        retrieval.MANIFEST_PATH = manifest_path
        retrieval._manifest_by_path.cache_clear()

        rows = retrieval._fill_missing_metadata(
            [{"aircraft": "A320", "font": "wiki", "texto": "fact"}]
        )

    assert rows == [
        {
            "aircraft": "A320",
            "font": "wiki",
            "texto": "fact",
            "document_id": "manifest-id",
            "source_file": "data/raw/wiki/A320.txt",
            "token_count": 1,
        }
    ]


def test_existing_metadata_and_token_count_are_not_overwritten(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        rows = retrieval._fill_missing_metadata(
            [
                {
                    "document_id": "known",
                    "source_file": "custom/source.txt",
                    "token_count": 99,
                    "texto": "short",
                }
            ]
        )

    assert rows == [
        {
            "document_id": "known",
            "source_file": "custom/source.txt",
            "token_count": 99,
            "texto": "short",
        }
    ]


def test_search_context_returns_empty_rows_without_losing_query_contract(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        patches = modules["__patches__"]
        retrieval.embed_text = mock.Mock(return_value=[0.1])
        patches.cursor.fetchall.return_value = []

        assert retrieval.search_context("unknown", aircraft=None, top_k=0) == []

    sql, params = patches.cursor.execute.call_args.args
    assert "find_similar_parents_hybrid" in sql
    assert params[1:] == ("unknown", None, 0)
