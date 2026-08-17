"""Run the RAG against an evaluation dataset and persist execution traces."""

from __future__ import annotations

import argparse
import os
import uuid
from typing import Any, Callable

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json

from evaluation.metrics.retrieval import RetrievedItem, evaluate_retrieval
from rag.result import RAGResult


RETRIEVAL_EVALUATOR_VERSION = "deterministic-retrieval-v1"
RELEVANCE_THRESHOLD = 2


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if number <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _metric_k_values(config: dict[str, Any]) -> tuple[int, ...]:
    if "k_values" in config:
        values = config["k_values"]
        if isinstance(values, (str, bytes)) or not isinstance(values, list | tuple):
            raise ValueError("k_values must be a list of positive integers")
        return tuple(_positive_int(value, "k_values") for value in values)
    if "top_k" in config:
        return (_positive_int(config["top_k"], "top_k"),)
    return (3, 5, 10)


def _run_id(run_name: str) -> str:
    return f"{run_name}-{uuid.uuid4().hex[:12]}"


def _langsmith_extra(
    trace_id: str,
    db_run_id: str,
    case_id: str,
    dataset_id: str,
    run_name: str,
    run_type: str,
    corpus_version: str | None,
    prompt_version: str | None,
    model_versions: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": f"evaluation.{run_name}.{case_id}",
        "run_id": trace_id,
        "tags": ["evaluation", run_type, dataset_id, run_name],
        "metadata": {
            "trace_id": trace_id,
            "db_run_id": db_run_id,
            "case_id": case_id,
            "dataset_id": dataset_id,
            "run_name": run_name,
            "run_type": run_type,
            "corpus_version": corpus_version,
            "prompt_version": prompt_version,
            "model_versions": model_versions,
        },
    }


def _insert_run(
    cursor,
    run_id: str,
    dataset_id: str,
    run_name: str,
    run_type: str,
    git_commit: str | None,
    corpus_version: str | None,
    prompt_version: str | None,
    config: dict[str, Any],
    model_versions: dict[str, Any],
) -> None:
    cursor.execute(
        """
        insert into evaluation.runs (
            run_id, dataset_id, run_name, run_type, git_commit,
            corpus_version, prompt_version, config, model_versions
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            dataset_id,
            run_name,
            run_type,
            git_commit,
            corpus_version,
            prompt_version,
            Json(config),
            Json(model_versions),
        ),
    )


def _insert_case_result(cursor, run_id: str, case_id: str, result: RAGResult) -> int:
    cursor.execute(
        """
        insert into evaluation.case_runs (
            run_id, case_id, answer, abstained, trace_id, retrieved_count,
            context_tokens, input_tokens, output_tokens, estimated_cost,
            latency_ms, timings, raw_output
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning case_run_id
        """,
        (
            run_id,
            case_id,
            result.answer,
            result.abstained,
            result.metadata.get("trace_id"),
            len(result.retrieved_items),
            result.token_usage.get("context_estimated"),
            result.token_usage.get("input_tokens"),
            result.token_usage.get("output_tokens"),
            result.metadata.get("estimated_cost"),
            result.timings_ms.get("total"),
            Json(result.timings_ms),
            Json(result.to_dict()),
        ),
    )
    return cursor.fetchone()[0]


def _insert_items(cursor, case_run_id: int, result: RAGResult) -> None:
    for rank, item in enumerate(result.retrieved_items, start=1):
        cursor.execute(
            """
            insert into evaluation.retrieved_items (
                case_run_id, rank, document_id, parent_id, chunk_id,
                aircraft, variant, vector_rank, keyword_rank,
                vector_score, keyword_score, rrf_score, token_count
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                case_run_id,
                rank,
                item.get("document_id"),
                item.get("parent_id") or item.get("chunk_id"),
                item.get("chunk_id"),
                item.get("aircraft"),
                item.get("variant"),
                item.get("vector_rank"),
                item.get("keyword_rank"),
                item.get("vector_score"),
                item.get("keyword_score"),
                item.get("rrf_score") or item.get("similarity"),
                item.get("token_count"),
            ),
        )

    for position, item in enumerate(result.context_items, start=1):
        cursor.execute(
            """
            insert into evaluation.context_items (
                case_run_id, position, parent_id, source_file, token_count
            )
            values (%s, %s, %s, %s, %s)
            """,
            (
                case_run_id,
                position,
                item.get("parent_id") or item.get("chunk_id"),
                item.get("source_file") or item.get("font"),
                item.get("token_count"),
            ),
        )


def _load_qrels(cursor, case_id: str) -> dict[str, int]:
    cursor.execute(
        """
        select document_id, parent_id, chunk_id, relevance
        from evaluation.evidence
        where case_id = %s
        """,
        (case_id,),
    )
    qrels: dict[str, int] = {}
    for document_id, parent_id, chunk_id, relevance in cursor.fetchall():
        item_id = document_id or parent_id or chunk_id
        if not item_id:
            continue
        qrels[item_id] = max(qrels.get(item_id, 0), int(relevance))
    return qrels


def _retrieved_items_for_metrics(result: RAGResult) -> list[RetrievedItem]:
    items = []
    for item in result.retrieved_items:
        item_id = item.get("document_id") or item.get("parent_id") or item.get("chunk_id")
        if not item_id:
            continue
        items.append(
            RetrievedItem(
                item_id=str(item_id),
                parent_id=item.get("parent_id") or item.get("chunk_id"),
                document_id=item.get("document_id"),
                token_count=int(item.get("token_count") or 0),
            )
        )
    return items


def _insert_metrics(
    cursor,
    run_id: str,
    case_run_id: int,
    case_id: str,
    metrics: dict[str, float | int],
    details: dict[str, Any],
) -> None:
    for metric_name, score in metrics.items():
        cursor.execute(
            """
            insert into evaluation.metrics (
                case_run_id, run_id, case_id, metric_name,
                score, details, evaluator_version
            )
            values (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                case_run_id,
                run_id,
                case_id,
                metric_name,
                float(score),
                Json(details),
                RETRIEVAL_EVALUATOR_VERSION,
            ),
        )

def run_evaluation(
    connection,
    dataset_id: str,
    run_name: str,
    target: Callable[..., RAGResult],
    run_type: str = "evaluation",
    git_commit: str | None = None,
    corpus_version: str | None = None,
    prompt_version: str | None = None,
    config: dict[str, Any] | None = None,
    model_versions: dict[str, Any] | None = None,
) -> str:
    """Run all active cases and persist their structured RAG results."""
    run_id = _run_id(run_name)
    config = config or {}
    model_versions = model_versions or {}
    k_values = _metric_k_values(config)
    expected_top_k = _positive_int(config["top_k"], "top_k") if "top_k" in config else None

    with connection.cursor() as cursor:
        _insert_run(
            cursor,
            run_id,
            dataset_id,
            run_name,
            run_type,
            git_commit,
            corpus_version,
            prompt_version,
            config,
            model_versions,
        )
    connection.commit()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select case_id, question
                from evaluation.cases
                where dataset_id = %s and status <> 'rejected'
                order by case_id
                """,
                (dataset_id,),
            )
            cases = cursor.fetchall()

            for case_id, question in cases:
                qrels = _load_qrels(cursor, case_id)
                trace_id = str(uuid.uuid4())
                langsmith_extra = _langsmith_extra(
                    trace_id,
                    run_id,
                    case_id,
                    dataset_id,
                    run_name,
                    run_type,
                    corpus_version,
                    prompt_version,
                    model_versions,
                )
                result = target(question, langsmith_extra=langsmith_extra)
                actual_top_k = result.metadata.get("top_k")
                if expected_top_k is not None and actual_top_k != expected_top_k:
                    raise ValueError(
                        "Configured top_k does not match the executed RAG result "
                        f"for case {case_id}: expected {expected_top_k}, got {actual_top_k}."
                    )
                if qrels and result.retrieved_items and any(
                    not item.get("document_id") for item in result.retrieved_items
                ):
                    raise ValueError(
                        "Retriever results must include document_id to calculate "
                        f"document-level metrics for case {case_id}."
                    )
                result.metadata["trace_id"] = trace_id
                result.metadata["langsmith_name"] = langsmith_extra["name"]
                case_run_id = _insert_case_result(cursor, run_id, case_id, result)
                _insert_items(cursor, case_run_id, result)
                metrics = evaluate_retrieval(
                    _retrieved_items_for_metrics(result),
                    qrels,
                    k_values=k_values,
                    relevance_threshold=RELEVANCE_THRESHOLD,
                )
                _insert_metrics(
                    cursor,
                    run_id,
                    case_run_id,
                    case_id,
                    metrics,
                    {
                        "qrels_count": len(qrels),
                        "relevance_threshold": RELEVANCE_THRESHOLD,
                        "top_k": expected_top_k,
                        "k_values": list(k_values),
                    },
                )

            cursor.execute(
                """
                update evaluation.runs
                set status = 'completed', ended_at = now(),
                    total_cost = (
                        select coalesce(sum(estimated_cost), 0)
                        from evaluation.case_runs where run_id = %s
                    ),
                    total_latency_ms = (
                        select coalesce(sum(latency_ms), 0)
                        from evaluation.case_runs where run_id = %s
                    )
                where run_id = %s
                """,
                (run_id, run_id, run_id),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update evaluation.runs
                set status = 'failed', ended_at = now()
                where run_id = %s
                """,
                (run_id,),
            )
        connection.commit()
        raise

    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="aviation_golden_v1")
    parser.add_argument("--run-name", default="baseline-v1")
    parser.add_argument(
        "--run-type",
        choices=("baseline", "evaluation", "ablation", "online_sample"),
        default="baseline",
    )
    args = parser.parse_args()

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url or "YOUR-PASSWORD" in database_url:
        raise SystemExit("DATABASE_URL is missing or still contains the placeholder.")

    from evaluation.manifest import DEFAULT_OUTPUT
    from ingestion.embedder import EMBEDDING_MODEL
    from rag.generator import K_TOP, MODEL_NAME, generate_result
    from rag.guardrails import (
        MAX_CONTEXT_CHARS,
        MAX_OUTPUT_TOKENS,
        PROMPT_GUARD_MODEL,
        RAG_SECURITY,
    )

    config = {
        "top_k": K_TOP,
        "k_values": [K_TOP],
        "max_context_chars": MAX_CONTEXT_CHARS,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "rag_security": RAG_SECURITY,
        "relevance_threshold": RELEVANCE_THRESHOLD,
        "retrieval_evaluator_version": RETRIEVAL_EVALUATOR_VERSION,
    }
    if DEFAULT_OUTPUT.exists():
        import json

        manifest = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
        config["corpus_manifest_sha256"] = manifest.get("manifest_sha256")

    model_versions = {
        "generator_model": MODEL_NAME,
        "embedding_model": EMBEDDING_MODEL,
        "prompt_guard_model": PROMPT_GUARD_MODEL,
    }

    connection = psycopg2.connect(database_url)
    try:
        run_id = run_evaluation(
            connection,
            dataset_id=args.dataset,
            run_name=args.run_name,
            run_type=args.run_type,
            target=generate_result,
            config=config,
            corpus_version=config.get("corpus_manifest_sha256"),
            model_versions=model_versions,
        )
    finally:
        connection.close()
    print(f"Completed evaluation run: {run_id}")


if __name__ == "__main__":
    main()
