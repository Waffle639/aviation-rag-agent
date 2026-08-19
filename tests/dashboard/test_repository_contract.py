from contextlib import contextmanager

import pytest

from dashboard.queries import EvaluationRepository


class FakeCursor:
    def __init__(self, rows=None, one=None, rowcount=0):
        self.rows = rows or []
        self.one = one
        self.rowcount = rowcount
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.one


class FakePool:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.readonly_values = []

    @contextmanager
    def cursor(self, readonly=True):
        self.readonly_values.append(readonly)
        yield self.cursor_instance


def test_case_metrics_interpolates_public_metric_filter_and_returns_rows():
    cursor = FakeCursor(rows=[{"metric_name": "mrr", "score": 1.0}])
    repository = EvaluationRepository(FakePool(cursor))

    rows = repository.get_case_metrics("run-1", "av_0001")

    assert rows == [{"metric_name": "mrr", "score": 1.0}]
    sql, params = cursor.calls[0]
    assert "{public_metric_sql_filter()}" not in sql
    assert "metric_name = any(%s)" in sql
    assert params[0:2] == ("run-1", "av_0001")


def test_run_summary_exposes_only_public_configuration_fields():
    cursor = FakeCursor(
        one={
            "run_id": "run-1",
            "config": {"top_k": 5, "database_url": "secret"},
            "model_versions": {"generator_model": "test", "api_key": "secret"},
        }
    )
    repository = EvaluationRepository(FakePool(cursor))

    result = repository.get_run_summary("run-1")

    assert result["public_config"] == {"top_k": 5}
    assert result["public_model_versions"] == {"generator_model": "test"}
    assert "config" not in result
    assert "model_versions" not in result


@pytest.mark.parametrize(
    "method,args",
    [
        ("get_metric_history", ("dataset", "private_metric")),
        ("get_quality_latency_runs", ("dataset", "private_metric")),
        ("get_breakdown", ("run", "not-a-dimension", "mrr")),
        ("get_breakdown", ("run", "category", "private_metric")),
        ("list_case_results", ("run", None, "private_metric")),
    ],
)
def test_repository_rejects_private_metrics_or_dimensions(method, args):
    repository = EvaluationRepository(FakePool(FakeCursor()))

    with pytest.raises(ValueError):
        getattr(repository, method)(*args)


def test_delete_run_is_safe_for_missing_and_running_runs():
    missing_cursor = FakeCursor(one=None)
    missing_pool = FakePool(missing_cursor)
    assert EvaluationRepository(missing_pool).delete_run("missing") is False
    assert missing_pool.readonly_values == [False]

    running_cursor = FakeCursor(one={"status": "running"})
    with pytest.raises(ValueError, match="running"):
        EvaluationRepository(FakePool(running_cursor)).delete_run("running")


def test_delete_run_removes_feedback_and_run_when_completed():
    cursor = FakeCursor(one={"status": "completed"}, rowcount=1)
    pool = FakePool(cursor)

    assert EvaluationRepository(pool).delete_run("run-1") is True
    assert len(cursor.calls) == 3
    assert cursor.calls[1][0].startswith("delete from evaluation.feedback")
    assert cursor.calls[2][0].startswith("delete from evaluation.runs")
