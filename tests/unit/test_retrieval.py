from unittest import mock
import hashlib


def test_search_context_executes_hybrid_query(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        patches = modules["__patches__"]
        rows = [{"chunk_id": "parent-1", "similarity": 0.1234}]

        retrieval.embed_text = mock.Mock(return_value=[0.1, 0.2])
        patches.cursor.fetchall.return_value = rows

        result = retrieval.search_context("What is Vso?", aircraft="Cessna", top_k=3)

    assert result == [{"chunk_id": "parent-1", "similarity": 0.1234, "token_count": 0}]
    retrieval.embed_text.assert_called_once_with("What is Vso?")
    sql, params = patches.cursor.execute.call_args.args
    assert "find_similar_parents_hybrid" in sql
    assert params[1:] == ("What is Vso?", "Cessna", 3)


def test_search_context_backfills_document_id_from_manifest_shape(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        patches = modules["__patches__"]
        patches.cursor.fetchall.return_value = [
            {
                "texto": "The 747 first flew on February 9, 1969.",
                "aircraft": "Boeing_747",
                "font": "wiki",
                "chunk_id": "boeing_747_wiki_p000",
                "parent_id": "boeing_747_wiki_p000",
                "document_id": None,
                "source_file": None,
                "token_count": None,
                "similarity": 0.5,
                "rrf_score": 0.5,
            }
        ]
        retrieval.embed_text = mock.Mock(return_value=[0.1, 0.2])

        result = retrieval.search_context("When did the 747 first fly?")

    assert result[0]["document_id"] == "f3d8f5418129b47f"
    assert result[0]["source_file"] == "data/raw/wiki/Boeing_747.txt"
    assert result[0]["token_count"] > 0


def test_manifest_loader_returns_empty_when_manifest_is_missing(import_fresh, tmp_path):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        retrieval.MANIFEST_PATH = tmp_path / "missing.json"
        retrieval._manifest_by_path.cache_clear()

        assert retrieval._manifest_by_path() == {}


def test_fill_missing_metadata_hashes_source_file_without_manifest(import_fresh, tmp_path):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        retrieval.MANIFEST_PATH = tmp_path / "missing.json"
        retrieval._manifest_by_path.cache_clear()

        rows = retrieval._fill_missing_metadata(
            [{"texto": "abcd", "source_file": "data/raw/wiki/Custom.txt"}]
        )

    expected = hashlib.sha256("wiki/Custom.txt".encode("utf-8")).hexdigest()[:16]
    assert rows[0]["document_id"] == expected
    assert rows[0]["source_file"] == "data/raw/wiki/Custom.txt"
    assert rows[0]["token_count"] == 1


def test_fill_missing_metadata_uses_pdf_manifest_candidate(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]
        retrieval._manifest_by_path.cache_clear()

        rows = retrieval._fill_missing_metadata(
            [{"texto": "manual text", "aircraft": "AC_A320_0624", "font": "pdf"}]
        )

    assert rows[0]["document_id"] == "b0132e331549708b"
    assert rows[0]["source_file"] == "data/raw/pdf_to_txt/AC_A320_0624.txt"


def test_fill_missing_metadata_without_aircraft_still_estimates_tokens(import_fresh):
    with import_fresh("rag.retrieval") as modules:
        retrieval = modules["rag.retrieval"]

        rows = retrieval._fill_missing_metadata([{"texto": "abcdefgh"}])

    assert rows == [{"texto": "abcdefgh", "token_count": 2}]
