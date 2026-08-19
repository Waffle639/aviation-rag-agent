"""SQL queries and public data shaping for evaluation dashboard views."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from dashboard.database import DatabasePool


_DYNAMIC_METRIC_RE = re.compile(r"^(recall|precision|hit_rate|ndcg)_at_([1-9][0-9]*)$")
QUALITY_METRICS = {"mrr"}
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
    "max_context_chars",
    "max_output_tokens",
    "rag_security",
    "relevance_threshold",
    "retrieval_evaluator_version",
    "corpus_manifest_sha256",
    "evaluator_version",
}
MODEL_ALLOWLIST = {
    "model",
    "generator_model",
    "embedding_model",
    "prompt_guard_model",
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
    description: str = ""


METRIC_DEFINITIONS = {
    "mrr": MetricDefinition(
        "mrr",
        "MRR",
        "maximize",
        description="Shows how high the first correct result appears. Rank 1 scores 1, rank 2 scores 0.5, and no hit scores 0.",
    ),
    "unique_parent_ratio": MetricDefinition(
        "unique_parent_ratio", "Unique parent ratio", "maximize",
        description="Share of results coming from different parent chunks. It is parent chunks divided by retrieved results."
    ),
    "duplicate_ratio": MetricDefinition("duplicate_ratio", "Duplicate ratio", "minimize", description="Share of repeated parent chunks. It is 1 minus unique parent ratio; lower is better."),
    "retrieved_items": MetricDefinition("retrieved_items", "Retrieved items", "tradeoff", "count", description="Number of results retrieved per question. It checks the actual top_k budget, but it is not a quality score."),
    "retrieved_tokens": MetricDefinition("retrieved_tokens", "Retrieved tokens", "tradeoff", "tokens", description="Estimated tokens in retrieved results. Fewer tokens reduce cost, but may remove needed evidence."),
}


def is_public_metric(metric_name: str) -> bool:
    return metric_name in PUBLIC_METRICS or bool(_DYNAMIC_METRIC_RE.fullmatch(metric_name))


def public_metric_sql_filter(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        f"({prefix}metric_name = any(%s) or "
        f"{prefix}metric_name ~ '^(recall|precision|hit_rate|ndcg)_at_[1-9][0-9]*$')"
    )


def run_top_k(run: Mapping[str, Any] | None) -> int | None:
    if not isinstance(run, Mapping):
        return None
    for source in (run.get("config"), run.get("public_config"), run):
        if isinstance(source, Mapping):
            value = source.get("top_k") or source.get("retrieval_top_k")
            if value is not None:
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    return None
                return number if number > 0 else None
    value = run.get("raw_top_k")
    try:
        number = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    return number if number and number > 0 else None


def display_metrics_for_run(run: Mapping[str, Any] | None) -> tuple[str, ...]:
    top_k = run_top_k(run) or 5
    return (f"recall_at_{top_k}", "mrr", f"ndcg_at_{top_k}", f"hit_rate_at_{top_k}")


def concept_metric(metric_concept: str, run: Mapping[str, Any] | None) -> str:
    top_k = run_top_k(run) or 5
    if metric_concept in {"recall", "precision", "hit_rate", "ndcg"}:
        return f"{metric_concept}_at_{top_k}"
    return metric_concept


def metric_definition(metric_name: str) -> MetricDefinition:
    match = _DYNAMIC_METRIC_RE.fullmatch(metric_name)
    if match:
        metric_type, k = match.groups()
        labels = {
            "recall": "Recall",
            "precision": "Precision",
            "hit_rate": "HitRate",
            "ndcg": "nDCG",
        }
        descriptions = {
            "recall": f"Share of expected relevant information found in the first {k} results. It is found relevant documents divided by expected relevant documents.",
            "precision": f"Share of correct results among the first {k}. It increases when less irrelevant context is retrieved.",
            "hit_rate": f"Checks whether at least one correct result appears in the first {k}. Each question scores 1 for a hit and 0 for no hit.",
            "ndcg": f"Checks whether the most relevant results appear first within {k}. It compares your ranking with the ideal ranking.",
        }
        return MetricDefinition(
            metric_name,
            f"{labels[metric_type]}@{k}",
            "maximize",
            description=descriptions[metric_type],
        )
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
                f"""
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
                f"""
                with expected as (
                    select dataset_id, count(*) as expected_cases
                    from evaluation.cases
                    where status <> 'rejected'
                    group by dataset_id
                ), case_stats as (
                    select
                        run_id,
                        count(*) as executed_cases,
                        avg(latency_ms) as avg_latency_ms,
                        case
                            when min((raw_output->'metadata'->>'top_k')::int) = max((raw_output->'metadata'->>'top_k')::int)
                            then min((raw_output->'metadata'->>'top_k')::int)
                            else null
                        end as raw_top_k
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
                    r.config,
                    e.expected_cases,
                    coalesce(cs.executed_cases, 0) as executed_cases,
                    cs.avg_latency_ms,
                    cs.raw_top_k
                from evaluation.runs r
                join evaluation.datasets d using (dataset_id)
                left join expected e using (dataset_id)
                left join case_stats cs using (run_id)
                order by r.started_at desc, r.run_name
                """
            )
            rows = _rows(cursor.fetchall())
        for row in rows:
            row["public_config"] = public_config(row.get("config"))
            row["top_k"] = run_top_k(row)
            row.pop("config", None)
        return rows

    def list_runs(self, dataset_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                f"""
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
                f"""
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
                        count(estimated_cost) as cost_samples,
                        case
                            when min((raw_output->'metadata'->>'top_k')::int) = max((raw_output->'metadata'->>'top_k')::int)
                            then min((raw_output->'metadata'->>'top_k')::int)
                            else null
                        end as raw_top_k
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
        data["top_k"] = run_top_k(data)
        data.pop("config", None)
        data.pop("model_versions", None)
        return data

    def get_metric_summary(self, run_id: str) -> list[dict[str, Any]]:
        with self._pool.cursor() as cursor:
            cursor.execute(
                f"""
                select
                    metric_name,
                    evaluator_version,
                    count(*) as sample_count,
                    avg(score) as mean_score,
                    min(score) as min_score,
                    max(score) as max_score
                from evaluation.metrics
                where run_id = %s
                  and {public_metric_sql_filter()}
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
                f"""
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
                f"""
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
                f"""
                with baseline as (
                    select case_id, metric_name, evaluator_version, score
                    from evaluation.metrics
                    where run_id = %s and {public_metric_sql_filter()}
                ), candidate as (
                    select case_id, metric_name, evaluator_version, score
                    from evaluation.metrics
                    where run_id = %s and {public_metric_sql_filter()}
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
                f"""
                select metric_name, score, evaluator_version, details
                from evaluation.metrics
                where run_id = %s and case_id = %s and {public_metric_sql_filter()}
                order by metric_name
                """,
                (run_id, case_id, list(PUBLIC_METRICS)),
            )
            return _rows(cursor.fetchall())

    def delete_run(self, run_id: str) -> bool:
        with self._pool.cursor(readonly=False) as cursor:
            cursor.execute(
                "select status from evaluation.runs where run_id = %s for update",
                (run_id,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            if row.get("status") == "running":
                raise ValueError("Cannot delete a running evaluation.")
            cursor.execute("delete from evaluation.feedback where run_id = %s", (run_id,))
            cursor.execute("delete from evaluation.runs where run_id = %s", (run_id,))
            return cursor.rowcount == 1

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
