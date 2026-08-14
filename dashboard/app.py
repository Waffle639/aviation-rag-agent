"""Streamlit entrypoint for Aviation RAG Evaluations."""

from __future__ import annotations

from html import escape

import streamlit as st

from dashboard.components import alert, header
from dashboard.config import APP_TITLE, load_config
from dashboard.database import create_pool
from dashboard.queries import EvaluationRepository
from dashboard.styles import apply_styles
from dashboard.views import cases, comparison, overview


st.set_page_config(page_title=APP_TITLE, layout="wide", page_icon="A")
apply_styles()


@st.cache_resource(show_spinner=False)
def _repository() -> EvaluationRepository:
    config = load_config()
    return EvaluationRepository(create_pool(config))


@st.cache_data(ttl=60, show_spinner=False)
def _all_runs(_repo: EvaluationRepository) -> list[dict]:
    return _repo.list_dashboard_runs()


def _run_label(run: dict) -> str:
    status = run.get("status") or "unknown"
    cases = _case_progress(run)
    return f"{run.get('run_name')} | {run.get('run_type')} | {status} | {cases} cases"


def _case_progress(run: dict) -> str:
    expected = run.get("expected_cases")
    executed = run.get("executed_cases")
    if expected:
        return f"{executed or 0}/{expected}"
    return str(executed or 0)


def _initial_candidate_run_id(runs: list[dict]) -> str:
    for run in runs:
        if run.get("run_type") != "baseline" and run.get("status") == "completed":
            return run["run_id"]
    for run in runs:
        if run.get("status") == "completed":
            return run["run_id"]
    return runs[0]["run_id"]


def _compatible_runs(runs: list[dict], candidate: dict) -> list[dict]:
    return [
        run
        for run in runs
        if run.get("dataset_id") == candidate.get("dataset_id")
        and run.get("run_id") != candidate.get("run_id")
    ]


def _recommended_baseline(runs: list[dict], candidate: dict) -> str | None:
    compatible = _compatible_runs(runs, candidate)
    for run in compatible:
        if run.get("run_type") == "baseline" and run.get("status") == "completed":
            return run["run_id"]
    for run in compatible:
        if run.get("status") == "completed":
            return run["run_id"]
    return compatible[0]["run_id"] if compatible else None


def _run_by_id(runs: list[dict], run_id: str | None) -> dict | None:
    return next((run for run in runs if run.get("run_id") == run_id), None)


def main() -> None:
    header()
    try:
        repo = _repository()
        runs = _all_runs(repo)
    except Exception:
        alert("Evaluation data is temporarily unavailable. Check dashboard database access.")
        st.stop()

    if not runs:
        alert("No evaluation runs found.")
        st.stop()

    if "candidate_run_id" not in st.session_state or not _run_by_id(runs, st.session_state.candidate_run_id):
        st.session_state.candidate_run_id = _initial_candidate_run_id(runs)

    selected_run = _run_by_id(runs, st.session_state.candidate_run_id)
    if not selected_run:
        alert("Selected evaluation run was not found.")
        st.stop()

    _render_evaluation_picker(runs, selected_run)

    selected_run = _run_by_id(runs, st.session_state.candidate_run_id)
    if not selected_run:
        alert("Selected evaluation run was not found.")
        st.stop()

    run_id = selected_run["run_id"]
    dataset_id = selected_run["dataset_id"]
    recommended_baseline_id = _recommended_baseline(runs, selected_run)
    if (
        "baseline_run_id" not in st.session_state
        or not _run_by_id(_compatible_runs(runs, selected_run), st.session_state.baseline_run_id)
    ):
        st.session_state.baseline_run_id = recommended_baseline_id
    baseline_run_id = st.session_state.baseline_run_id

    baseline_run = _run_by_id(runs, baseline_run_id)
    _render_selection_summary(runs, selected_run, baseline_run)

    header_status = selected_run.get("status") if selected_run else None
    if header_status and header_status != "completed":
        alert(f"Selected run status: {header_status}. Metrics may be incomplete.")

    page = st.radio(
        "Navigation",
        ["Overview", "Run Comparison", "Case Explorer"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if page == "Overview":
        overview.render(repo, dataset_id, run_id, baseline_run_id)
    elif page == "Run Comparison":
        comparison.render(repo, run_id, baseline_run_id)
    else:
        cases.render(repo, run_id, baseline_run_id)


def _render_evaluation_picker(runs: list[dict], selected_run: dict) -> None:
    top_left, top_right = st.columns([2.6, 0.7])
    with top_left:
        st.markdown("### Current evaluation")
        st.markdown(
            f"""
            <div class="evaluation-card">
              <strong>{escape(str(selected_run.get('run_name') or 'Untitled evaluation'))}</strong>
              <div class="evaluation-meta">
                Dataset {escape(str(selected_run.get('dataset_name') or 'Unknown'))} v{escape(str(selected_run.get('dataset_version') or 'Unknown'))} | 
                {escape(str(selected_run.get('run_type') or 'unknown'))} | {escape(str(selected_run.get('status') or 'unknown'))} | {_case_progress(selected_run)} cases
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with top_right:
        st.write("")
        st.write("")
        if st.button("Refresh data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    with st.expander("Change evaluation", expanded=False):
        st.caption("Pick the evaluation run you want to inspect. The dataset is inferred automatically.")
        table_rows = [_run_table_row(run) for run in runs]
        event = st.dataframe(
            table_rows,
            use_container_width=True,
            hide_index=True,
            column_order=["evaluation", "type", "status", "dataset", "cases", "started_at"],
            column_config={
                "evaluation": "Evaluation",
                "type": "Type",
                "status": "Status",
                "dataset": "Dataset",
                "cases": "Cases",
                "started_at": "Started",
            },
            on_select="rerun",
            selection_mode="single-row",
            key="evaluation_run_table",
        )
        selected_rows = event.selection.rows if hasattr(event, "selection") else []
        if selected_rows:
            selected_index = selected_rows[0]
            selected_id = table_rows[selected_index]["run_id"]
            if selected_id != st.session_state.candidate_run_id:
                st.session_state.candidate_run_id = selected_id
                st.session_state.pop("baseline_run_id", None)
                st.rerun()


def _render_selection_summary(runs: list[dict], candidate: dict, baseline: dict | None) -> None:
    left, right = st.columns([1.4, 1])
    with left:
        st.caption(
            f"Dataset is inferred from the selected evaluation: "
            f"{candidate.get('dataset_name')} v{candidate.get('dataset_version')} "
            f"({candidate.get('dataset_status')})."
        )
    with right:
        if baseline:
            st.markdown(
                f"""
                <div class="baseline-card">
                  <strong>Baseline comparison</strong><br>
                  {escape(str(baseline.get('run_name') or 'Untitled baseline'))} | {_case_progress(baseline)} cases
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            alert("No compatible baseline was found for this evaluation.")

    compatible = _compatible_runs(runs, candidate)
    if compatible:
        with st.expander("Advanced baseline override", expanded=False):
            baseline_options = [run["run_id"] for run in compatible]
            current = st.session_state.get("baseline_run_id")
            index = baseline_options.index(current) if current in baseline_options else 0
            st.radio(
                "Baseline run",
                baseline_options,
                index=index,
                format_func=lambda run_id: _run_label(next(run for run in compatible if run["run_id"] == run_id)),
                key="baseline_run_id",
            )


def _run_table_row(run: dict) -> dict:
    return {
        "run_id": run["run_id"],
        "evaluation": run.get("run_name"),
        "type": run.get("run_type"),
        "status": run.get("status"),
        "dataset": f"{run.get('dataset_name')} v{run.get('dataset_version')}",
        "cases": _case_progress(run),
        "started_at": run.get("started_at"),
    }


if __name__ == "__main__":
    main()
