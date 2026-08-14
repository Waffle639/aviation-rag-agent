"""Overview page for the evaluation dashboard."""

from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import charts
from dashboard.components import alert, kpi_card, panel_title
from dashboard.queries import DISPLAY_METRICS, metric_definition


def _metric_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["metric_name"]: row for row in rows}


def _comparison_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["metric_name"]: row for row in rows}


def render(repo, dataset_id: str, run_id: str, baseline_run_id: str | None) -> None:
    summary = repo.get_run_summary(run_id)
    if not summary:
        alert("Selected run was not found.")
        return

    expected = summary.get("expected_cases") or 0
    executed = summary.get("executed_cases") or 0
    if summary.get("status") != "completed":
        alert(
            f"Run status is {summary.get('status')}. Aggregated metrics may still change."
        )
    elif expected and executed < expected:
        alert(f"Only {executed} of {expected} expected cases are available.")

    metrics = _metric_map(repo.get_metric_summary(run_id))
    comparison = _comparison_map(repo.compare_runs(baseline_run_id, run_id)) if baseline_run_id else {}

    cols = st.columns(4)
    for column, metric_name in zip(cols, DISPLAY_METRICS):
        metric = metrics.get(metric_name, {})
        delta = comparison.get(metric_name, {}).get("mean_delta")
        normalized = comparison.get(metric_name, {}).get("normalized_delta")
        definition = metric_definition(metric_name)
        with column:
            kpi_card(
                definition.label,
                metric.get("mean_score"),
                delta=delta,
                unit="percent" if metric_name.startswith(("recall", "hit_rate")) else "score",
                sample_count=metric.get("sample_count"),
                normalized_delta=normalized,
            )

    st.write("")
    left, right = st.columns([1.2, 1])
    with left:
        panel_title("Quality trend")
        history_metric = st.selectbox(
            "Trend metric",
            DISPLAY_METRICS,
            index=1,
            format_func=lambda name: metric_definition(name).label,
            label_visibility="collapsed",
        )
        history = repo.get_metric_history(dataset_id, history_metric)
        if history:
            st.plotly_chart(
                charts.metric_history(history, history_metric, run_id, baseline_run_id),
                use_container_width=True,
            )
        else:
            st.caption("No completed metric history available yet.")

    with right:
        panel_title("Quality / latency map")
        quality_latency = repo.get_quality_latency_runs(dataset_id, history_metric)
        if quality_latency:
            st.plotly_chart(
                charts.quality_latency_scatter(
                    quality_latency, history_metric, run_id, baseline_run_id
                ),
                use_container_width=True,
            )
        else:
            st.caption("No latency comparison available yet.")

    left, right = st.columns([1.1, 1])
    with left:
        panel_title("Performance by category")
        breakdown = repo.get_breakdown(run_id, "category", "mrr")
        if breakdown:
            st.plotly_chart(charts.breakdown_bar(breakdown, "mrr"), use_container_width=True)
        else:
            st.caption("No category breakdown available.")

    with right:
        panel_title("Latency and resources")
        resource_cols = st.columns(2)
        resource_cols[0].metric("p50 latency", _latency(summary.get("p50_latency_ms")))
        resource_cols[1].metric("p95 latency", _latency(summary.get("p95_latency_ms")))
        resource_cols[0].metric("Input tokens", _count(summary.get("input_tokens")))
        resource_cols[1].metric("Output tokens", _count(summary.get("output_tokens")))
        resource_cols[0].metric("Context tokens", _count(summary.get("context_tokens")))
        resource_cols[1].metric("Known cost", _cost(summary.get("known_cost")))

    panel_title("Largest regressions")
    if baseline_run_id:
        cases = repo.list_case_results(run_id, baseline_run_id, "mrr")[:8]
        st.dataframe(
            [
                {
                    "case_id": row["case_id"],
                    "category": row["category"],
                    "difficulty": row["difficulty"],
                    "baseline": row.get("baseline_score"),
                    "candidate": row.get("candidate_score"),
                    "delta": row.get("delta"),
                    "question": row.get("question"),
                }
                for row in cases
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("Select a baseline run to show regressions.")


def _latency(value: Any) -> str:
    if value is None:
        return "N/A"
    value = float(value)
    return f"{value / 1000:.2f} s" if value >= 1000 else f"{value:.0f} ms"


def _count(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):,.0f}"


def _cost(value: Any) -> str:
    return "N/A" if value is None else f"${float(value):.4f}"
