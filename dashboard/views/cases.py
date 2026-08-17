"""Case explorer page."""

from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from dashboard.components import alert, panel_title
from dashboard.queries import display_metrics_for_run, metric_definition


def render(repo, run_id: str, baseline_run_id: str | None) -> None:
    summary = repo.get_run_summary(run_id)
    display_metrics = display_metrics_for_run(summary)
    metric_name = st.selectbox(
        "Ranking metric",
        display_metrics,
        index=1,
        format_func=lambda name: metric_definition(name).label,
    )
    rows = repo.list_case_results(run_id, baseline_run_id, metric_name)
    if not rows:
        alert("No cases are available for the selected run.")
        return

    categories = ["All"] + sorted({str(row.get("category")) for row in rows if row.get("category")})
    aircraft = ["All"] + sorted({str(row.get("aircraft")) for row in rows if row.get("aircraft")})
    col1, col2, col3 = st.columns([1.2, 1, 1])
    search = col1.text_input("Search", placeholder="Case id or question")
    category_filter = col2.selectbox("Category", categories)
    aircraft_filter = col3.selectbox("Aircraft", aircraft)

    filtered = _filter_rows(rows, search, category_filter, aircraft_filter)
    if not filtered:
        alert("No cases match the current filters.")
        return

    left, right = st.columns([0.9, 1.6])
    with left:
        panel_title(f"Cases ({len(filtered)})")
        options = [row["case_id"] for row in filtered]
        selected_case_id = st.radio(
            "Case",
            options,
            format_func=lambda case_id: _case_label(next(row for row in filtered if row["case_id"] == case_id)),
            label_visibility="collapsed",
        )

    with right:
        _render_case_detail(repo, run_id, selected_case_id, baseline_run_id)


def _filter_rows(
    rows: list[dict[str, Any]], search: str, category: str, aircraft: str
) -> list[dict[str, Any]]:
    needle = search.strip().lower()
    filtered = []
    for row in rows:
        if category != "All" and row.get("category") != category:
            continue
        if aircraft != "All" and row.get("aircraft") != aircraft:
            continue
        if needle and needle not in row["case_id"].lower() and needle not in (row.get("question") or "").lower():
            continue
        filtered.append(row)
    return filtered


def _case_label(row: dict[str, Any]) -> str:
    delta = row.get("delta")
    marker = "DOWN" if delta is not None and delta < 0 else "UP" if delta is not None and delta > 0 else "STABLE"
    score = row.get("candidate_score")
    score_text = "N/A" if score is None else f"{float(score):.2f}"
    return f"{marker} {row['case_id']} | {row.get('category')} | {score_text}"


def _render_case_detail(repo, run_id: str, case_id: str, baseline_run_id: str | None) -> None:
    detail = repo.get_case_detail(run_id, case_id)
    if not detail:
        alert("The selected case could not be loaded.")
        return

    panel_title(f"Case {case_id}")
    st.caption(
        f"{detail.get('category')} | {detail.get('difficulty')} | "
        f"{'Answerable' if detail.get('answerable') else 'Expected abstention'}"
    )
    st.markdown(
        f"<div class='case-question'><strong>Question</strong><br>{escape(detail.get('question') or '')}</div>",
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(
        f"<div class='case-answer'><strong>Reference answer</strong><br>{escape(detail.get('reference_answer') or 'N/A')}</div>",
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(
        f"<div class='case-answer'><strong>Generated answer</strong><br>{escape(detail.get('answer') or 'N/A')}</div>",
        unsafe_allow_html=True,
    )

    metrics = repo.get_case_metrics(run_id, case_id)
    if metrics:
        metric_cols = st.columns(min(4, len(metrics)))
        for column, metric in zip(metric_cols, metrics[:4]):
            column.metric(metric_definition(metric["metric_name"]).label, _score(metric.get("score")))

    tabs = st.tabs(["Golden evidence", "Retrieved ranking", "Context used", "Run details"])
    with tabs[0]:
        evidence = repo.get_evidence(case_id)
        if evidence:
            st.dataframe(evidence, use_container_width=True, hide_index=True)
        else:
            st.caption("No golden evidence available.")

    with tabs[1]:
        retrieved = repo.get_retrieved_items(detail["case_run_id"])
        if retrieved:
            st.dataframe(retrieved, use_container_width=True, hide_index=True)
        else:
            st.caption("No retrieved ranking persisted for this case.")

    with tabs[2]:
        context = repo.get_context_items(detail["case_run_id"])
        if context:
            st.dataframe(context, use_container_width=True, hide_index=True)
        else:
            st.caption("No context items persisted for this case.")

    with tabs[3]:
        st.json(
            {
                "latency_ms": detail.get("latency_ms"),
                "context_tokens": detail.get("context_tokens"),
                "input_tokens": detail.get("input_tokens"),
                "output_tokens": detail.get("output_tokens"),
                "estimated_cost": detail.get("estimated_cost"),
                "abstained": detail.get("abstained"),
                "timings": detail.get("timings") or {},
            },
            expanded=False,
        )


def _score(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.3f}"
