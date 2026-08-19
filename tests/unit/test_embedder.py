import json
from types import SimpleNamespace
from unittest import mock

import pytest


def _chunk(chunk_id="c1", parent_id="p1", text="aviation fact"):
    return {
        "texto": text,
        "metadata": {
            "chunk_id": chunk_id,
            "parent_id": parent_id,
            "aeronave": "TestPlane",
            "fuente": "wiki",
            "document_id": "doc1",
            "source_file": "data/raw/wiki/TestPlane.txt",
            "token_count": 3,
        },
    }


def _parent(parent_id="p1", text="aviation parent"):
    return {
        "texto": text,
        "metadata": {
            "parent_id": parent_id,
            "aeronave": "TestPlane",
            "fuente": "wiki",
            "document_id": "doc1",
            "source_file": "data/raw/wiki/TestPlane.txt",
            "token_count": 4,
        },
    }


def test_load_json_files_is_sorted_and_ignores_non_json_entries(import_fresh, tmp_path):
    route = tmp_path / "chunks"
    (route / "PlaneB").mkdir(parents=True)
    (route / "PlaneA").mkdir()
    (route / "ignored.txt").write_text("not a directory", encoding="utf-8")
    (route / "PlaneB" / "02.json").write_text('{"id": 2}', encoding="utf-8")
    (route / "PlaneB" / "01.json").write_text('{"id": 1}', encoding="utf-8")
    (route / "PlaneB" / "skip.csv").write_text("skip", encoding="utf-8")
    (route / "PlaneA" / "01.json").write_text('{"id": 0}', encoding="utf-8")

    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        assert embedder._load_json_files(str(route)) == [
            {"id": 0},
            {"id": 1},
            {"id": 2},
        ]


def test_load_chunks_and_parents_forward_custom_routes(import_fresh, tmp_path):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder._load_json_files = mock.Mock(return_value=[{"id": 1}])

        assert embedder.load_chunks(str(tmp_path / "chunks")) == [{"id": 1}]
        assert embedder.load_parents(str(tmp_path / "parents")) == [{"id": 1}]
        assert embedder._load_json_files.call_args_list == [
            mock.call(str(tmp_path / "chunks")),
            mock.call(str(tmp_path / "parents")),
        ]


def test_existing_ids_are_read_from_the_database(import_fresh):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        cursor = modules["__patches__"].cursor
        cursor.fetchall.side_effect = [[("c1",), ("c2",)], [("p1",)]]

        assert embedder.get_existing_chunk_ids() == {"c1", "c2"}
        assert embedder.get_existing_parent_ids() == {"p1"}
        assert cursor.execute.call_args_list == [
            mock.call("select chunk_id from documents"),
            mock.call("select parent_id from parent_chunks"),
        ]


def test_embed_batch_retries_rate_limit_and_returns_embeddings(import_fresh, monkeypatch):
    from openai import RateLimitError

    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
        embedder.openai_client.embeddings.create.side_effect = [
            RateLimitError("limited", response=mock.Mock(), body=None),
            response,
        ]
        sleep = mock.Mock()
        monkeypatch.setattr(embedder.time, "sleep", sleep)

        assert embedder.embed_batch(["text"]) == [[0.1, 0.2]]
        assert embedder.openai_client.embeddings.create.call_count == 2
        sleep.assert_called_once_with(2)


def test_embed_batch_raises_after_last_api_error(import_fresh, monkeypatch):
    from openai import APIError

    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        error = APIError("failed", request=mock.Mock(), body=None)
        embedder.openai_client.embeddings.create.side_effect = error
        monkeypatch.setattr(embedder.time, "sleep", mock.Mock())

        with pytest.raises(APIError):
            embedder.embed_batch(["text"])
        assert embedder.openai_client.embeddings.create.call_count == embedder.MAX_RETRIES


def test_upsert_retries_after_rollback(import_fresh, monkeypatch):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        execute_values = mock.Mock(side_effect=[RuntimeError("temporary"), None])
        monkeypatch.setattr(embedder, "execute_values", execute_values)
        sleep = mock.Mock()
        monkeypatch.setattr(embedder.time, "sleep", sleep)

        embedder._upsert_with_retry("insert sql", [("row",)], "Child")

        assert execute_values.call_count == 2
        assert embedder.db_connection.rollback.call_count == 1
        assert embedder.db_connection.commit.call_count == 1
        sleep.assert_called_once_with(2)


def test_upsert_child_and_parent_wrappers_use_expected_labels(import_fresh, monkeypatch):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder._upsert_with_retry = mock.Mock()

        embedder.upsert_child_batch([("child",)])
        embedder.upsert_parent_batch([("parent",)])

        assert embedder._upsert_with_retry.call_args_list == [
            mock.call(embedder.UPSERT_CHILD_SQL, [("child",)], "Child"),
            mock.call(embedder.UPSERT_PARENT_SQL, [("parent",)], "Parent"),
        ]


def test_embed_text_delegates_to_one_item_batch(import_fresh):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder.embed_batch = mock.Mock(return_value=[[1.0, 2.0]])

        assert embedder.embed_text("question") == [1.0, 2.0]
        embedder.embed_batch.assert_called_once_with(["question"])


def test_run_embeds_only_pending_children_and_upserts_parents(import_fresh, monkeypatch):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        child_pending = _chunk("new")
        child_existing = _chunk("old")
        parent_pending = _parent("new-parent")
        parent_existing = _parent("old-parent")
        embedder.load_chunks = mock.Mock(return_value=[child_pending, child_existing])
        embedder.load_parents = mock.Mock(return_value=[parent_pending, parent_existing])
        embedder.get_existing_chunk_ids = mock.Mock(return_value={"old"})
        embedder.get_existing_parent_ids = mock.Mock(return_value={"old-parent"})
        embedder._scan_ingestion_chunks = mock.Mock(return_value=([], []))
        embedder.embed_batch = mock.Mock(return_value=[[0.1, 0.2]])
        embedder.upsert_child_batch = mock.Mock()
        embedder.upsert_parent_batch = mock.Mock()
        monkeypatch.setattr(embedder, "Vector", lambda value: tuple(value))

        embedder._run()

        embedder.embed_batch.assert_called_once_with(["aviation fact"])
        child_rows = embedder.upsert_child_batch.call_args.args[0]
        assert child_rows[0][2] == "new"
        assert child_rows[0][5] == "p1"
        parent_rows = embedder.upsert_parent_batch.call_args.args[0]
        assert parent_rows[0][2] == "new-parent"
        embedder.db_connection.close.assert_called_once()


def test_run_closes_connection_and_reports_failed_child_batch(import_fresh, monkeypatch):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder.load_chunks = mock.Mock(return_value=[_chunk("new")])
        embedder.load_parents = mock.Mock(return_value=[])
        embedder.get_existing_chunk_ids = mock.Mock(return_value=set())
        embedder.get_existing_parent_ids = mock.Mock(return_value=set())
        embedder._scan_ingestion_chunks = mock.Mock(return_value=([], []))
        embedder.embed_batch = mock.Mock(side_effect=RuntimeError("embedding failed"))
        monkeypatch.setattr(embedder, "Vector", lambda value: tuple(value))

        with pytest.raises(SystemExit) as exc_info:
            embedder._run()

        assert exc_info.value.code == 1
        embedder.db_connection.close.assert_called_once()


def test_run_closes_connection_when_scan_raises(import_fresh):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder.load_chunks = mock.Mock(return_value=[])
        embedder.load_parents = mock.Mock(return_value=[])
        embedder.get_existing_chunk_ids = mock.Mock(return_value=set())
        embedder.get_existing_parent_ids = mock.Mock(return_value=set())
        embedder._scan_ingestion_chunks = mock.Mock(side_effect=RuntimeError("scan failed"))

        with pytest.raises(RuntimeError, match="scan failed"):
            embedder._run()

        embedder.db_connection.close.assert_called_once()


def test_run_logs_parent_batch_failure_but_closes_cleanly(import_fresh, caplog):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder.load_chunks = mock.Mock(return_value=[])
        embedder.load_parents = mock.Mock(return_value=[_parent("new-parent")])
        embedder.get_existing_chunk_ids = mock.Mock(return_value=set())
        embedder.get_existing_parent_ids = mock.Mock(return_value=set())
        embedder._scan_ingestion_chunks = mock.Mock(return_value=([], []))
        embedder.upsert_parent_batch = mock.Mock(side_effect=RuntimeError("db failed"))

        with caplog.at_level("ERROR", logger=embedder.__name__):
            embedder._run()

        assert any("Parent batch" in record.message for record in caplog.records)
        embedder.db_connection.close.assert_called_once()


def test_run_wrapper_disables_tracing_for_operational_ingestion(import_fresh):
    with import_fresh("ingestion.embedder") as modules:
        embedder = modules["ingestion.embedder"]
        embedder._run = mock.Mock()

        embedder.run("chunks", "parents")

        embedder._run.assert_called_once_with("chunks", "parents")
