from rag.result import RAGResult

from evaluation.runner import run_evaluation


class FakeCursor:
    def __init__(self, cases, qrels):
        self.cases = cases
        self.qrels = qrels
        self.calls = []
        self._next_case_run_id = 100
        self._fetchone = None
        self._fetchall = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, params))
        if normalized.startswith("select case_id, question"):
            self._fetchall = self.cases
            return
        if normalized.startswith("select document_id, parent_id, chunk_id, relevance"):
            self._fetchall = self.qrels.get(params[0], [])
            return
        if "returning case_run_id" in normalized:
            self._fetchone = (self._next_case_run_id,)
            self._next_case_run_id += 1

    def fetchall(self):
        return self._fetchall

    def fetchone(self):
        return self._fetchone


class FakeConnection:
    def __init__(self, cases, qrels=None):
        self.cursor_instance = FakeCursor(cases, qrels or {})
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1



def _sample_result(question):
    return RAGResult(
        question=question,
        answer="According to wiki, the answer is 250 feet.",
        retrieved_items=[
            {
                "document_id": "boeing_747_wiki",
                "parent_id": "boeing_747_wiki_p001",
                "chunk_id": "boeing_747_wiki_c004",
                "aircraft": "Boeing 747",
                "font": "wiki",
                "rrf_score": 0.05,
                "token_count": 42,
            }
        ],
        context_items=[
            {
                "parent_id": "boeing_747_wiki_p001",
                "source_file": "Boeing_747.txt",
                "token_count": 42,
            }
        ],
        timings_ms={"total": 123.4},
        token_usage={"context_estimated": 42, "input_tokens": 100, "output_tokens": 12},
    )


def test_run_evaluation_persists_run_cases_and_trace_items():
    connection = FakeConnection(
        [("av_0001", "Question one?"), ("av_0002", "Question two?")],
        qrels={
            "av_0001": [("boeing_747_wiki", "boeing_747_wiki_p001", None, 3)],
            "av_0002": [("boeing_747_wiki", "boeing_747_wiki_p001", None, 3)],
        },
    )
    seen_questions = []

    def target(question):
        seen_questions.append(question)
        return _sample_result(question)

    run_id = run_evaluation(
        connection,
        dataset_id="aviation_golden_v1",
        run_name="baseline-v1",
        run_type="baseline",
        target=target,
        model_versions={"generation": "test-model"},
    )

    calls = connection.cursor_instance.calls
    sql = [call[0] for call in calls]
    assert run_id.startswith("baseline-v1-")
    assert seen_questions == ["Question one?", "Question two?"]
    assert connection.commits == 2
    assert connection.rollbacks == 0
    assert any(statement.startswith("insert into evaluation.runs") for statement in sql)
    assert sum(statement.startswith("insert into evaluation.case_runs") for statement in sql) == 2
    assert sum(statement.startswith("insert into evaluation.retrieved_items") for statement in sql) == 2
    assert sum(statement.startswith("insert into evaluation.context_items") for statement in sql) == 2
    assert sum(statement.startswith("insert into evaluation.metrics") for statement in sql) == 34
    assert any("set status = 'completed'" in statement for statement in sql)


def test_run_evaluation_marks_run_failed_after_case_error():
    connection = FakeConnection([("av_0001", "Question one?")])

    def target(_question):
        raise RuntimeError("boom")

    try:
        run_evaluation(
            connection,
            dataset_id="aviation_golden_v1",
            run_name="baseline-v1",
            target=target,
        )
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected RuntimeError")

    sql = [call[0] for call in connection.cursor_instance.calls]
    assert connection.commits == 2
    assert connection.rollbacks == 1
    assert any(statement.startswith("insert into evaluation.runs") for statement in sql)
    assert any("set status = 'failed'" in statement for statement in sql)
