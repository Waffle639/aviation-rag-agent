from unittest import mock


def test_search_context_executes_hybrid_query(import_fresh):
    with import_fresh("rag.retrival") as modules:
        retrival = modules["rag.retrival"]
        patches = modules["__patches__"]
        rows = [{"chunk_id": "parent-1", "similarity": 0.1234}]

        retrival.embed_text = mock.Mock(return_value=[0.1, 0.2])
        patches.cursor.fetchall.return_value = rows

        result = retrival.search_context("What is Vso?", aircraft="Cessna", top_k=3)

    assert result == [{"chunk_id": "parent-1", "similarity": 0.1234, "token_count": 0}]
    retrival.embed_text.assert_called_once_with("What is Vso?")
    sql, params = patches.cursor.execute.call_args.args
    assert "find_similar_parents_hybrid" in sql
    assert params[1:] == ("What is Vso?", "Cessna", 3)


def test_search_context_backfills_document_id_from_manifest_shape(import_fresh):
    with import_fresh("rag.retrival") as modules:
        retrival = modules["rag.retrival"]
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
        retrival.embed_text = mock.Mock(return_value=[0.1, 0.2])

        result = retrival.search_context("When did the 747 first fly?")

    assert result[0]["document_id"] == "f3d8f5418129b47f"
    assert result[0]["source_file"] == "data/raw/wiki/Boeing_747.txt"
    assert result[0]["token_count"] > 0
