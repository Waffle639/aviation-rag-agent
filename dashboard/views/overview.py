"""Overview page for the evaluation dashboard."""

from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import charts
from dashboard.components import alert, kpi_card, panel_title
from dashboard.queries import display_metrics_for_run, metric_definition


def _metric_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["metric_name"]: row for row in rows}


def render(repo, dataset_id: str, run_id: str) -> None:
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
    display_metrics = display_metrics_for_run(summary)

    cols = st.columns(4)
    for column, metric_name in zip(cols, display_metrics):
        metric = metrics.get(metric_name, {})
        definition = metric_definition(metric_name)
        with column:
            kpi_card(
                definition.label,
                metric.get("mean_score"),
                unit="percent" if metric_name.startswith(("recall", "hit_rate")) else "score",
                sample_count=metric.get("sample_count"),
                description=definition.description,
            )

    st.write("")
    left, right = st.columns([1.2, 1])
    with left:
        panel_title("Quality trend")
        history_metric = st.selectbox(
            "Trend metric",
            display_metrics,
            index=1,
            format_func=lambda name: metric_definition(name).label,
            label_visibility="collapsed",
        )
        history = repo.get_metric_history(dataset_id, history_metric)
        if history:
            st.plotly_chart(
                    charts.metric_history(history, history_metric, run_id),
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
                    quality_latency, history_metric, run_id
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

def _latency(value: Any) -> str:
    if value is None:
        return "N/A"
    value = float(value)
    return f"{value / 1000:.2f} s" if value >= 1000 else f"{value:.0f} ms"


def _count(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):,.0f}"


def _cost(value: Any) -> str:
    return "N/A" if value is None else f"${float(value):.4f}"
