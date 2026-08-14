from unittest import mock


def test_search_context_executes_hybrid_query(import_fresh):
    with import_fresh("rag.retrival") as modules:
        retrival = modules["rag.retrival"]
        patches = modules["__patches__"]
        rows = [{"chunk_id": "parent-1", "similarity": 0.1234}]

        retrival.embed_text = mock.Mock(return_value=[0.1, 0.2])
        patches.cursor.fetchall.return_value = rows

        result = retrival.search_context("What is Vso?", aircraft="Cessna", top_k=3)

    assert result == rows
    retrival.embed_text.assert_called_once_with("What is Vso?")
    sql, params = patches.cursor.execute.call_args.args
    assert "find_similar_parents_hybrid" in sql
    assert params[1:] == ("What is Vso?", "Cessna", 3)
