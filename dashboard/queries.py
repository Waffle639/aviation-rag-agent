"""SQL queries and public data shaping for evaluation dashboard views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from dashboard.database import DatabasePool


QUALITY_METRICS = {
    "recall_at_3",
    "precision_at_3",
    "hit_rate_at_3",
    "ndcg_at_3",
    "recall_at_5",
    "precision_at_5",
    "hit_rate_at_5",
    "ndcg_at_5",
    "mrr",
}
EFFICIENCY_METRICS = {
    "unique_parent_ratio",
    "duplicate_ratio",
    "retrieved_items",
    "retrieved_tokens",
}
PUBLIC_METRICS = QUALITY_METRICS | EFFICIENCY_METRICS
MINIMIZE_METRICS = {"duplicate_ratio"}
TRADEOFF_METRICS = {"retrieved_items", "retrieved_tokens"}
DISPLAY_METRICS = ("recall_at_5", "mrr", "ndcg_at_5", "hit_rate_at_5")
CONFIG_ALLOWLIST = {
    "top_k",
    "k_values",
    "retrieval_top_k",
    "prompt_version",
    "corpus_version",
    "model",
    "generator_model",
    "embedding_model",
    "evaluator_version",
}
MODEL_ALLOWLIST = {
    "model",
    "generator_model",
    "embedding_model",
    "retrieval_model",
    "evaluator_model",
}
DIMENSIONS = {
    "category": "c.category",
    "aircraft": "coalesce(c.aircraft, 'Unknown')",
    "variant": "coalesce(c.variant, 'Unknown')",
    "difficulty": "c.difficulty",
    "split": "c.split",
    "answerable": "c.answerable::text",
}


@dataclass(frozen=True)
class MetricDefinition:
    name: str
    label: str
    direction: str
    unit: str = "score"


METRIC_DEFINITIONS = {
    "recall_at_5": MetricDefinition("recall_at_5", "Recall@5", "maximize"),
    "mrr": MetricDefinition("mrr", "MRR", "maximize"),
    "ndcg_at_5": MetricDefinition("ndcg_at_5", "nDCG@5", "maximize"),
    "hit_rate_at_5": MetricDefinition("hit_rate_at_5", "HitRate@5", "maximize"),
    "recall_at_3": MetricDefinition("recall_at_3", "Recall@3", "maximize"),
    "precision_at_3": MetricDefinition("precision_at_3", "Precision@3", "maximize"),
    "precision_at_5": MetricDefinition("precision_at_5", "Precision@5", "maximize"),
    "hit_rate_at_3": MetricDefinition("hit_rate_at_3", "HitRate@3", "maximize"),
    "ndcg_at_3": MetricDefinition("ndcg_at_3", "nDCG@3", "maximize"),
    "unique_parent_ratio": MetricDefinition(
        "unique_parent_ratio", "Unique parent ratio", "maximize"
    ),
    "duplicate_ratio": MetricDefinition("duplicate_ratio", "Duplicate ratio", "minimize"),
    "retrieved_items": MetricDefinition("retrieved_items", "Retrieved items", "tradeoff", "count"),
    "retrieved_tokens": MetricDefinition("retrieved_tokens", "Retrieved tokens", "tradeoff", "tokens"),
}


def is_public_metric(metric_name: str) -> bool:
    return metric_name in PUBLIC_METRICS


def metric_definition(metric_name: str) -> MetricDefinition:
    return METRIC_DEFINITIONS.get(
        metric_name, MetricDefinition(metric_name, metric_name.replace("_", " ").title(), "maximize")
    )


def normalized_delta(metric_name: str, delta: float | None) -> float | None:
    if delta is None:
        return None
    if metric_name in MINIMIZE_METRICS:
        return -delta
    if metric_name in TRADEOFF_METRICS:
        return None
    return delta


def public_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, Mapping):
        return {}
    return {key: config[key] for key in CONFIG_ALLOWLIST if key in config}


def public_model_versions(model_versions: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(model_versions, Mapping):
        return {}
    return {key: model_versions[key] for key in MODEL_ALLOWLIST if key in model_versions}


def _rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


class EvaluationRepository:
    def __init__(self, pool: DatabasePool):
        self._pool = pool

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select
                    d.dataset_id,
                    d.name,
                    d.version,
                    d.status,
                    d.created_at,
                    coalesce(c.case_count, 0) as case_count,
                    coalesce(r.run_count, 0) as run_count,
                    r.latest_run_at
                from evaluation.datasets d
                left join (
                    select dataset_id, count(*) as case_count
                    from evaluation.cases
                    where status <> 'rejected'
                    group by dataset_id
                ) c using (dataset_id)
                left join (
                    select dataset_id, count(*) as run_count, max(started_at) as latest_run_at
                    from evaluation.runs
                    group by dataset_id
                ) r using (dataset_id)
                order by coalesce(r.latest_run_at, d.created_at) desc, d.dataset_id
                """
            )
            rows = _rows(cursor.fetchall())
        for row in rows:
            row["public_model_versions"] = public_model_versions(row.get("model_versions"))
            row.pop("model_versions", None)
        return rows

    def list_dashboard_runs(self) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                with expected as (
                    select dataset_id, count(*) as expected_cases
                    from evaluation.cases
                    where status <> 'rejected'
                    group by dataset_id
                ), case_stats as (
                    select
                        run_id,
                        count(*) as executed_cases,
                        avg(latency_ms) as avg_latency_ms
                    from evaluation.case_runs
                    group by run_id
                )
                select
                    r.run_id,
                    r.dataset_id,
                    d.name as dataset_name,
                    d.version as dataset_version,
                    d.status as dataset_status,
                    r.run_name,
                    r.run_type,
                    r.status,
                    r.started_at,
                    r.ended_at,
                    r.corpus_version,
                    r.prompt_version,
                    e.expected_cases,
                    coalesce(cs.executed_cases, 0) as executed_cases,
                    cs.avg_latency_ms
                from evaluation.runs r
                join evaluation.datasets d using (dataset_id)
                left join expected e using (dataset_id)
                left join case_stats cs using (run_id)
                order by r.started_at desc, r.run_name
                """
            )
            return _rows(cursor.fetchall())

    def list_runs(self, dataset_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                with expected as (
                    select dataset_id, count(*) as expected_cases
                    from evaluation.cases
                    where status <> 'rejected'
                    group by dataset_id
                ), case_stats as (
                    select
                        run_id,
                        count(*) as executed_cases,
                        avg(latency_ms) as avg_latency_ms
                    from evaluation.case_runs
                    group by run_id
                )
                select
                    r.run_id,
                    r.dataset_id,
                    r.run_name,
                    r.run_type,
                    r.status,
                    r.started_at,
                    r.ended_at,
                    r.git_commit,
                    r.corpus_version,
                    r.prompt_version,
                    r.model_versions,
                    e.expected_cases,
                    coalesce(cs.executed_cases, 0) as executed_cases,
                    cs.avg_latency_ms
                from evaluation.runs r
                left join expected e using (dataset_id)
                left join case_stats cs using (run_id)
                where r.dataset_id = %s
                order by r.started_at desc
                """,
                (dataset_id,),
            )
            return _rows(cursor.fetchall())

    def get_run_summary(self, run_id: str) -> dict[str, Any] | None:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                with expected as (
                    select dataset_id, count(*) as expected_cases
                    from evaluation.cases
                    where status <> 'rejected'
                    group by dataset_id
                ), case_stats as (
                    select
                        run_id,
                        count(*) as executed_cases,
                        count(*) filter (where abstained) as abstained_cases,
                        avg(latency_ms) as avg_latency_ms,
                        percentile_cont(0.50) within group (order by latency_ms) as p50_latency_ms,
                        percentile_cont(0.95) within group (order by latency_ms) as p95_latency_ms,
                        sum(latency_ms) as total_latency_ms_cases,
                        sum(input_tokens) as input_tokens,
                        sum(output_tokens) as output_tokens,
                        sum(context_tokens) as context_tokens,
                        sum(estimated_cost) as known_cost,
                        count(estimated_cost) as cost_samples
                    from evaluation.case_runs
                    group by run_id
                )
                select
                    r.run_id,
                    r.dataset_id,
                    r.run_name,
                    r.run_type,
                    r.status,
                    r.started_at,
                    r.ended_at,
                    r.git_commit,
                    r.corpus_version,
                    r.prompt_version,
                    r.config,
                    r.model_versions,
                    e.expected_cases,
                    cs.*
                from evaluation.runs r
                left join expected e using (dataset_id)
                left join case_stats cs using (run_id)
                where r.run_id = %s
                """,
                (run_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["public_config"] = public_config(data.get("config"))
        data["public_model_versions"] = public_model_versions(data.get("model_versions"))
        data.pop("config", None)
        data.pop("model_versions", None)
        return data

    def get_metric_summary(self, run_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select
                    metric_name,
                    evaluator_version,
                    count(*) as sample_count,
                    avg(score) as mean_score,
                    min(score) as min_score,
                    max(score) as max_score
                from evaluation.metrics
                where run_id = %s
                  and metric_name = any(%s)
                  and (
                      metric_name in ('duplicate_ratio', 'unique_parent_ratio', 'retrieved_items', 'retrieved_tokens')
                      or coalesce((details->>'qrels_count')::int, 0) > 0
                  )
                group by metric_name, evaluator_version
                order by metric_name
                """,
                (run_id, list(PUBLIC_METRICS)),
            )
            return _rows(cursor.fetchall())

    def get_metric_history(self, dataset_id: str, metric_name: str) -> list[dict[str, Any]]:
        if not is_public_metric(metric_name):
            raise ValueError("Unsupported public metric")
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select
                    r.run_id,
                    r.run_name,
                    r.run_type,
                    r.status,
                    r.started_at,
                    avg(m.score) as mean_score,
                    count(*) as sample_count
                from evaluation.runs r
                join evaluation.metrics m using (run_id)
                where r.dataset_id = %s
                  and r.status = 'completed'
                  and m.metric_name = %s
                  and (
                      m.metric_name in ('duplicate_ratio', 'unique_parent_ratio', 'retrieved_items', 'retrieved_tokens')
                      or coalesce((m.details->>'qrels_count')::int, 0) > 0
                  )
                group by r.run_id, r.run_name, r.run_type, r.status, r.started_at
                order by r.started_at
                """,
                (dataset_id, metric_name),
            )
            return _rows(cursor.fetchall())

    def get_quality_latency_runs(
        self, dataset_id: str, metric_name: str = "mrr"
    ) -> list[dict[str, Any]]:
        if not is_public_metric(metric_name):
            raise ValueError("Unsupported public metric")
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                with metric_stats as (
                    select
                        run_id,
                        avg(score) as mean_score,
                        count(*) as metric_cases
                    from evaluation.metrics
                    where metric_name = %s
                      and (
                          metric_name in ('duplicate_ratio', 'unique_parent_ratio', 'retrieved_items', 'retrieved_tokens')
                          or coalesce((details->>'qrels_count')::int, 0) > 0
                      )
                    group by run_id
                ), latency_stats as (
                    select
                        run_id,
                        count(*) as executed_cases,
                        avg(latency_ms) as avg_latency_ms,
                        percentile_cont(0.95) within group (order by latency_ms) as p95_latency_ms,
                        sum(input_tokens) as input_tokens,
                        sum(output_tokens) as output_tokens
                    from evaluation.case_runs
                    group by run_id
                )
                select
                    r.run_id,
                    r.run_name,
                    r.run_type,
                    r.status,
                    r.started_at,
                    r.prompt_version,
                    r.corpus_version,
                    ms.mean_score,
                    ms.metric_cases,
                    ls.executed_cases,
                    ls.avg_latency_ms,
                    ls.p95_latency_ms,
                    ls.input_tokens,
                    ls.output_tokens
                from evaluation.runs r
                join metric_stats ms using (run_id)
                left join latency_stats ls using (run_id)
                where r.dataset_id = %s
                order by r.started_at
                """,
                (metric_name, dataset_id),
            )
            return _rows(cursor.fetchall())

    def compare_runs(self, baseline_run_id: str, candidate_run_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                with baseline as (
                    select case_id, metric_name, evaluator_version, score
                    from evaluation.metrics
                    where run_id = %s and metric_name = any(%s)
                ), candidate as (
                    select case_id, metric_name, evaluator_version, score
                    from evaluation.metrics
                    where run_id = %s and metric_name = any(%s)
                ), paired as (
                    select
                        c.case_id,
                        c.metric_name,
                        c.evaluator_version,
                        b.score as baseline_score,
                        c.score as candidate_score,
                        c.score - b.score as delta
                    from candidate c
                    join baseline b using (case_id, metric_name, evaluator_version)
                )
                select
                    metric_name,
                    evaluator_version,
                    count(*) as paired_cases,
                    avg(baseline_score) as baseline_mean,
                    avg(candidate_score) as candidate_mean,
                    avg(delta) as mean_delta,
                    min(delta) as min_delta,
                    max(delta) as max_delta
                from paired
                group by metric_name, evaluator_version
                order by metric_name
                """,
                (baseline_run_id, list(PUBLIC_METRICS), candidate_run_id, list(PUBLIC_METRICS)),
            )
            rows = _rows(cursor.fetchall())
        for row in rows:
            row["normalized_delta"] = normalized_delta(row["metric_name"], row.get("mean_delta"))
        return rows

    def get_breakdown(
        self, run_id: str, dimension: str = "category", metric_name: str = "mrr"
    ) -> list[dict[str, Any]]:
        if dimension not in DIMENSIONS:
            raise ValueError("Unsupported breakdown dimension")
        if not is_public_metric(metric_name):
            raise ValueError("Unsupported public metric")
        dimension_sql = DIMENSIONS[dimension]
        with self._pool.cursor() as cursor:
            cursor.execute(
                f"""
                select
                    {dimension_sql} as dimension_value,
                    count(*) as sample_count,
                    avg(m.score) as mean_score
                from evaluation.metrics m
                join evaluation.cases c using (case_id)
                where m.run_id = %s
                  and m.metric_name = %s
                  and (
                      m.metric_name in ('duplicate_ratio', 'unique_parent_ratio', 'retrieved_items', 'retrieved_tokens')
                      or coalesce((m.details->>'qrels_count')::int, 0) > 0
                  )
                group by dimension_value
                order by mean_score desc nulls last, sample_count desc
                """,
                (run_id, metric_name),
            )
            return _rows(cursor.fetchall())

    def list_case_results(
        self,
        run_id: str,
        baseline_run_id: str | None = None,
        metric_name: str = "mrr",
    ) -> list[dict[str, Any]]:
        if not is_public_metric(metric_name):
            raise ValueError("Unsupported public metric")
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select
                    cr.case_run_id,
                    cr.run_id,
                    cr.case_id,
                    c.question,
                    c.answerable,
                    c.aircraft,
                    c.variant,
                    c.category,
                    c.difficulty,
                    c.split,
                    cr.abstained,
                    cr.retrieved_count,
                    cr.latency_ms,
                    m.score as candidate_score,
                    b.score as baseline_score,
                    case when b.score is null then null else m.score - b.score end as delta
                from evaluation.case_runs cr
                join evaluation.cases c using (case_id)
                left join evaluation.metrics m
                  on m.run_id = cr.run_id
                 and m.case_id = cr.case_id
                 and m.metric_name = %s
                left join evaluation.metrics b
                  on b.run_id = %s
                 and b.case_id = cr.case_id
                 and b.metric_name = %s
                 and b.evaluator_version = m.evaluator_version
                where cr.run_id = %s
                order by
                    case when b.score is null then 1 else 0 end,
                    delta asc nulls last,
                    cr.case_id
                """,
                (metric_name, baseline_run_id, metric_name, run_id),
            )
            rows = _rows(cursor.fetchall())
        for row in rows:
            row["normalized_delta"] = normalized_delta(metric_name, row.get("delta"))
        return rows

    def get_case_detail(self, run_id: str, case_id: str) -> dict[str, Any] | None:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select
                    cr.case_run_id,
                    cr.run_id,
                    cr.case_id,
                    c.question,
                    c.reference_answer,
                    c.answerable,
                    c.expected_abstention,
                    c.aircraft,
                    c.variant,
                    c.category,
                    c.difficulty,
                    c.split,
                    c.expected_facts,
                    c.expected_numbers,
                    c.tags,
                    cr.answer,
                    cr.abstained,
                    cr.retrieved_count,
                    cr.context_tokens,
                    cr.input_tokens,
                    cr.output_tokens,
                    cr.estimated_cost,
                    cr.latency_ms,
                    cr.timings
                from evaluation.case_runs cr
                join evaluation.cases c using (case_id)
                where cr.run_id = %s and cr.case_id = %s
                """,
                (run_id, case_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_case_metrics(self, run_id: str, case_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select metric_name, score, evaluator_version, details
                from evaluation.metrics
                where run_id = %s and case_id = %s and metric_name = any(%s)
                order by metric_name
                """,
                (run_id, case_id, list(PUBLIC_METRICS)),
            )
            return _rows(cursor.fetchall())

    def get_evidence(self, case_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select evidence_id, source_file, document_id, parent_id, chunk_id,
                       line_start, line_end, quote, relevance, evidence_type
                from evaluation.evidence
                where case_id = %s
                order by relevance desc, evidence_id
                """,
                (case_id,),
            )
            return _rows(cursor.fetchall())

    def get_retrieved_items(self, case_run_id: int) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select rank, document_id, parent_id, chunk_id, aircraft, variant,
                       rrf_score, token_count, relevance, is_duplicate
                from evaluation.retrieved_items
                where case_run_id = %s
                order by rank
                """,
                (case_run_id,),
            )
            return _rows(cursor.fetchall())

    def get_context_items(self, case_run_id: int) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                """
                select position, parent_id, source_file, token_count, selected
                from evaluation.context_items
                where case_run_id = %s
                order by position
                """,
                (case_run_id,),
            )
            return _rows(cursor.fetchall())
