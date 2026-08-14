"""Run comparison page."""

from __future__ import annotations

from typing import Any

import streamlit as st

from dashboard import charts
from dashboard.components import alert, kpi_card, panel_title, safe_json
from dashboard.queries import DISPLAY_METRICS, metric_definition


def render(repo, run_id: str, baseline_run_id: str | None) -> None:
    if not baseline_run_id:
        alert("Select a baseline run to compare against the candidate.")
        return
    if baseline_run_id == run_id:
        alert("Baseline and candidate are the same run. Select two different runs.")
        return

    baseline = repo.get_run_summary(baseline_run_id)
    candidate = repo.get_run_summary(run_id)
    if not baseline or not candidate:
        alert("One of the selected runs could not be loaded.")
        return

    _compatibility_panel(baseline, candidate)

    comparison = repo.compare_runs(baseline_run_id, run_id)
    comparison_by_metric = {row["metric_name"]: row for row in comparison}
    cols = st.columns(4)
    for column, metric_name in zip(cols, DISPLAY_METRICS):
        row = comparison_by_metric.get(metric_name, {})
        definition = metric_definition(metric_name)
        with column:
            kpi_card(
                definition.label,
                row.get("candidate_mean"),
                row.get("mean_delta"),
                unit="percent" if metric_name.startswith(("recall", "hit_rate")) else "score",
                sample_count=row.get("paired_cases"),
                normalized_delta=row.get("normalized_delta"),
            )

    left, right = st.columns([1.25, 1])
    with left:
        panel_title("Metric comparison")
        metric_rows = [row for row in comparison if row["metric_name"] in DISPLAY_METRICS]
        if metric_rows:
            st.plotly_chart(charts.comparison_bar(metric_rows), use_container_width=True)
        else:
            st.caption("No paired public metrics available.")

    with right:
        panel_title("Configuration differences")
        st.caption("Only public allow-listed configuration values are shown.")
        safe_json(
            {
                "baseline": baseline.get("public_config") or {},
                "candidate": candidate.get("public_config") or {},
                "baseline_prompt_version": baseline.get("prompt_version"),
                "candidate_prompt_version": candidate.get("prompt_version"),
                "baseline_corpus_version": baseline.get("corpus_version"),
                "candidate_corpus_version": candidate.get("corpus_version"),
            }
        )

    selected_metric = st.selectbox(
        "Case delta metric",
        DISPLAY_METRICS,
        index=1,
        format_func=lambda name: metric_definition(name).label,
    )
    cases = repo.list_case_results(run_id, baseline_run_id, selected_metric)
    left, right = st.columns([1, 1])
    with left:
        panel_title("Baseline vs candidate by case")
        st.plotly_chart(
            charts.baseline_candidate_scatter(cases, selected_metric),
            use_container_width=True,
        )
    with right:
        panel_title("Largest case movements")
        st.plotly_chart(
            charts.case_delta_bar(cases, selected_metric),
            use_container_width=True,
        )

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
                    "baseline": row.get("baseline_score"),
                    "candidate": row.get("candidate_score"),
                    "delta": row.get("delta"),
                    "question": row.get("question"),
                }
                for row in cases[:20]
            ],
            use_container_width=True,
            hide_index=True,
        )


def _compatibility_panel(baseline: dict[str, Any], candidate: dict[str, Any]) -> None:
    checks = []
    checks.append(("Same dataset", baseline.get("dataset_id") == candidate.get("dataset_id")))
    checks.append(("Same corpus", baseline.get("corpus_version") == candidate.get("corpus_version")))
    checks.append(("Same prompt", baseline.get("prompt_version") == candidate.get("prompt_version")))
    ok_text = "   ".join(("OK" if ok else "WARN") + f" {label}" for label, ok in checks)
    st.caption(ok_text)
    if not checks[0][1]:
        alert("The selected runs belong to different datasets. Treat this comparison as exploratory.")
