"""Run comparison page."""

from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from dashboard import charts
from dashboard.components import alert, format_delta, format_score, panel_title
from dashboard.queries import (
    concept_metric,
    display_metrics_for_run,
    metric_definition,
    normalized_delta,
    run_top_k,
)


QUALITY_CONCEPTS = ("recall", "mrr", "ndcg", "hit_rate")
METRIC_CONCEPTS = QUALITY_CONCEPTS + ("retrieved_tokens",)


def render(repo, run_id: str, baseline_run_id: str | None) -> None:
    if not baseline_run_id:
        alert("Select Evaluation B to compare.")
        return
    if baseline_run_id == run_id:
        alert("Both selections point to the same evaluation. Select two different runs.")
        return

    baseline = repo.get_run_summary(baseline_run_id)
    candidate = repo.get_run_summary(run_id)
    if not baseline or not candidate:
        alert("One of the selected runs could not be loaded.")
        return

    baseline_metrics = _metric_map(repo.get_metric_summary(baseline_run_id))
    candidate_metrics = _metric_map(repo.get_metric_summary(run_id))
    concept_rows = _concept_rows(baseline, candidate, baseline_metrics, candidate_metrics)

    _compatibility_panel(baseline, candidate)
    _render_column_headers(candidate, baseline)

    panel_title("Model quality")
    _render_comparison_rows(concept_rows[: len(QUALITY_CONCEPTS)])

    panel_title("Latency, retrieval and cost")
    _render_comparison_rows(
        _resource_rows(baseline, candidate, baseline_metrics, candidate_metrics),
        resource=True,
    )

    panel_title("Metric chart")
    if concept_rows:
        st.plotly_chart(charts.comparison_bar(concept_rows), use_container_width=True)
    else:
        st.caption("No comparable public metrics available.")

    selected_metric = st.selectbox(
        "Case delta metric",
        display_metrics_for_run(candidate),
        index=1,
        format_func=lambda name: metric_definition(name).label,
    )
    cases = repo.list_case_results(run_id, baseline_run_id, selected_metric)
    left, right = st.columns([1, 1])
    with left:
        panel_title("Case scatter")
        st.plotly_chart(charts.baseline_candidate_scatter(cases, selected_metric), use_container_width=True)
    with right:
        panel_title("Largest case movements")
        st.plotly_chart(charts.case_delta_bar(cases, selected_metric), use_container_width=True)

    left, right = st.columns([1, 1])
    with left:
        panel_title("Case delta distribution")
        st.plotly_chart(charts.delta_distribution(cases), use_container_width=True)
    with right:
        panel_title("Case change table")
        st.dataframe(
            [
                {
                    "case_id": row["case_id"],
                    "category": row["category"],
                    "evaluation_a": row.get("candidate_score"),
                    "evaluation_b": row.get("baseline_score"),
                    "delta": row.get("delta"),
                    "question": row.get("question"),
                }
                for row in cases[:20]
            ],
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Run details", expanded=False):
        st.dataframe(_field_rows(baseline, candidate), use_container_width=True, hide_index=True)


def _metric_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["metric_name"]: row for row in rows}


def _render_column_headers(candidate: dict[str, Any], baseline: dict[str, Any]) -> None:
    left, middle, right = st.columns([1, 0.72, 1])
    with left:
        _model_header("Evaluation A", candidate)
    with middle:
        st.markdown("<div class='comparison-column-header comparison-column-difference'>Difference</div>", unsafe_allow_html=True)
    with right:
        _model_header("Evaluation B", baseline)


def _model_header(role: str, run: dict[str, Any]) -> None:
    versions = run.get("public_model_versions") or {}
    model = versions.get("generator_model") or versions.get("model") or "Model not recorded"
    st.markdown(
        f"""
        <div class="comparison-column-header">
          <span>{escape(role)}</span>
          <strong>{escape(str(run.get('run_name') or 'Untitled evaluation'))}</strong>
          <small>{escape(str(model))}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_comparison_rows(rows: list[dict[str, Any]], *, resource: bool = False) -> None:
    if not rows:
        st.caption("No comparable values available.")
        return
    for row in rows:
        candidate_value = row.get("candidate") if resource else row.get("candidate_mean")
        baseline_value = row.get("baseline") if resource else row.get("baseline_mean")
        candidate_metric = row.get("candidate_metric_name") or row.get("key") or ""
        baseline_metric = row.get("baseline_metric_name") or candidate_metric
        unit = row.get("unit") or _unit(candidate_metric)
        left, middle, right = st.columns([1, 0.72, 1])
        with left:
            _comparison_value_card(
                "Evaluation A",
                metric_definition(candidate_metric).label if not resource else row["label"],
                candidate_value,
                unit,
                row.get("description") or metric_definition(candidate_metric).description,
            )
        with middle:
            _comparison_delta_card(
                row["label"],
                row.get("delta"),
                candidate_metric,
                unit,
                row.get("normalized_delta"),
            )
        with right:
            _comparison_value_card(
                "Evaluation B",
                metric_definition(baseline_metric).label if not resource else row["label"],
                baseline_value,
                unit if resource or baseline_metric == candidate_metric else _unit(baseline_metric),
                metric_definition(baseline_metric).description if not resource else row.get("description", ""),
            )


def _comparison_value_card(
    role: str,
    label: str,
    value: Any,
    unit: str,
    description: str,
) -> None:
    label_html = escape(label)
    if description:
        label_html += f" <span class='info-icon' data-tooltip='{escape(description, quote=True)}'>i</span>"
    st.markdown(
        f"""
        <div class="comparison-value-card {'comparison-a-card' if role == 'Evaluation A' else 'comparison-b-card'}">
          <div class="comparison-label">{label_html}</div>
          <div class="comparison-value">{escape(format_score(value, unit))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _comparison_delta_card(
    label: str,
    delta: Any,
    metric_name: str,
    unit: str,
    normalized_delta_value: Any,
) -> None:
    direction = _winner(normalized_delta_value)
    delta_class = {
        "A wins": "comparison-a-wins",
        "B wins": "comparison-b-wins",
        "Tie": "comparison-tie",
        "Trade-off": "comparison-tie",
        "No data": "comparison-tie",
    }[direction]
    st.markdown(
        f"""
        <div class="comparison-delta-card {delta_class}">
          <div class="comparison-role">Difference</div>
          <div class="comparison-label">{escape(label)}</div>
          <div class="comparison-delta">{escape(_format_comparison_delta(delta, metric_name, unit))}</div>
          <div class="comparison-winner">{escape(direction)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _winner(normalized_delta_value: Any) -> str:
    if normalized_delta_value is None:
        return "Trade-off"
    value = float(normalized_delta_value)
    if abs(value) < 0.0005:
        return "Tie"
    return "A wins" if value > 0 else "B wins"


def _format_comparison_delta(value: Any, metric_name: str, unit: str) -> str:
    if value is None:
        return "No baseline"
    if unit in {"milliseconds", "currency", "tokens", "count"}:
        return _format_delta_unit(value, unit)
    return format_delta(value, _unit(metric_name))


def _concept_rows(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
    candidate_metrics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for concept in METRIC_CONCEPTS:
        baseline_metric_name = concept_metric(concept, baseline)
        candidate_metric_name = concept_metric(concept, candidate)
        baseline_row = baseline_metrics.get(baseline_metric_name, {})
        candidate_row = candidate_metrics.get(candidate_metric_name, {})
        baseline_mean = baseline_row.get("mean_score")
        candidate_mean = candidate_row.get("mean_score")
        delta = None if baseline_mean is None or candidate_mean is None else float(candidate_mean) - float(baseline_mean)
        label = metric_definition(candidate_metric_name).label
        if baseline_metric_name != candidate_metric_name:
            label = f"{label} vs {metric_definition(baseline_metric_name).label}"
        rows.append(
            {
                "metric_name": candidate_metric_name,
                "label": label,
                "baseline_metric_name": baseline_metric_name,
                "candidate_metric_name": candidate_metric_name,
                "baseline_mean": baseline_mean,
                "candidate_mean": candidate_mean,
                "mean_delta": delta,
                "delta": delta,
                "normalized_delta": normalized_delta(candidate_metric_name, delta),
                "baseline_samples": baseline_row.get("sample_count"),
                "candidate_samples": candidate_row.get("sample_count"),
            }
        )
    return rows


def _compatibility_panel(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    top_a = run_top_k(candidate) or "Unknown"
    top_b = run_top_k(baseline) or "Unknown"
    checks = [
        ("Same dataset", baseline.get("dataset_id") == candidate.get("dataset_id")),
        ("Same corpus", baseline.get("corpus_version") == candidate.get("corpus_version")),
        ("Same prompt", baseline.get("prompt_version") == candidate.get("prompt_version")),
        ("Same top_k", top_a == top_b),
    ]
    if not checks[0][1]:
        alert("The selected runs belong to different datasets. Treat this comparison as exploratory.")
    if top_a != top_b:
        alert(f"Different retrieval budgets: top_k {top_a} vs {top_b}. The delta compares full systems with different context budgets.")


def _field_rows(baseline: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [
        ("Run name", candidate.get("run_name"), baseline.get("run_name")),
        ("Run type", candidate.get("run_type"), baseline.get("run_type")),
        ("Status", candidate.get("status"), baseline.get("status")),
        ("Dataset", candidate.get("dataset_id"), baseline.get("dataset_id")),
        ("top_k", run_top_k(candidate), run_top_k(baseline)),
        ("Executed cases", candidate.get("executed_cases"), baseline.get("executed_cases")),
        ("Abstained cases", candidate.get("abstained_cases"), baseline.get("abstained_cases")),
        ("Corpus", candidate.get("corpus_version"), baseline.get("corpus_version")),
        ("Prompt", candidate.get("prompt_version"), baseline.get("prompt_version")),
        ("Generator model", (candidate.get("public_model_versions") or {}).get("generator_model"), (baseline.get("public_model_versions") or {}).get("generator_model")),
        ("Embedding model", (candidate.get("public_model_versions") or {}).get("embedding_model"), (baseline.get("public_model_versions") or {}).get("embedding_model")),
    ]
    return [
        {
            "field": name,
            "evaluation_a": _plain(a),
            "evaluation_b": _plain(b),
            "same": "yes" if a == b else "no",
        }
        for name, a, b in fields
    ]


def _resource_rows(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
    candidate_metrics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    specs = [
        ("p50 latency", "p50_latency_ms", "milliseconds", "Typical latency: 50% of cases finish below this value. Lower is better."),
        ("p95 latency", "p95_latency_ms", "milliseconds", "Tail latency: 95% of cases finish below this value. It highlights slow outliers."),
        ("Average latency", "avg_latency_ms", "milliseconds", "Average time per case. It can be pulled up by a small number of slow cases."),
        ("Retrieved tokens", "retrieved_tokens", "tokens", "Average estimated tokens in retrieved results."),
        ("Context tokens", "context_tokens", "tokens", "Tokens sent to the model as retrieved context. They increase with more chunks or longer chunks."),
        ("Input tokens", "input_tokens", "tokens", "Total tokens sent to the model, including instructions, context, and the question."),
        ("Output tokens", "output_tokens", "tokens", "Tokens generated in the answer. They may stay stable even when top_k changes."),
        ("Known cost", "known_cost", "currency", "Recorded total cost when the run stored per-case cost values."),
    ]
    rows = []
    metric_keys = {"retrieved_tokens"}
    for label, key, unit, description in specs:
        if key in metric_keys:
            candidate_value = candidate_metrics.get(key, {}).get("mean_score")
            baseline_value = baseline_metrics.get(key, {}).get("mean_score")
        else:
            candidate_value = candidate.get(key)
            baseline_value = baseline.get(key)
        delta = None if candidate_value is None or baseline_value is None else float(candidate_value) - float(baseline_value)
        normalized = -delta if delta is not None and key not in metric_keys else None
        rows.append(
            {
                "label": label,
                "key": key,
                "candidate": candidate_value,
                "baseline": baseline_value,
                "delta": delta,
                "unit": unit,
                "normalized_delta": normalized,
                "description": description,
            }
        )
    return rows


def _unit(metric_name: str) -> str:
    if metric_name.startswith(("recall", "hit_rate")):
        return "percent"
    if metric_name == "retrieved_items":
        return "count"
    if metric_name == "retrieved_tokens":
        return "tokens"
    return "score"


def _plain(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def _format_delta_unit(value: Any, unit: str) -> str:
    if value is None:
        return "N/A"
    number = float(value)
    sign = "+" if number > 0 else ""
    if unit == "milliseconds":
        return f"{sign}{number:.0f} ms"
    if unit == "currency":
        return f"{sign}${number:.4f}"
    if unit in {"tokens", "count"}:
        return f"{sign}{number:,.0f}"
    return f"{sign}{number:.3f}"
