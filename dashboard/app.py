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
    top_k = f" | top_k={run.get('top_k')}" if run.get("top_k") else ""
    return f"{run.get('run_name')} | {run.get('run_type')} | {status}{top_k} | {cases} cases"


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

    run_id = selected_run["run_id"]
    dataset_id = selected_run["dataset_id"]
    header_status = selected_run.get("status") if selected_run else None
    if header_status and header_status != "completed":
        alert(f"Selected run status: {header_status}. Metrics may be incomplete.")

    page = st.segmented_control(
        "Navigation",
        ["Overview", "Run Comparison", "Case Explorer", "Delete Evaluation"],
        default="Overview",
        key="dashboard_page",
        label_visibility="collapsed",
    )
    page = page or "Overview"

    recommended_baseline_id = _recommended_baseline(runs, selected_run)
    if (
        "baseline_run_id" not in st.session_state
        or not _run_by_id([run for run in runs if run.get("run_id") != run_id], st.session_state.baseline_run_id)
    ):
        st.session_state.baseline_run_id = recommended_baseline_id
    baseline_run_id = st.session_state.baseline_run_id
    baseline_run = _run_by_id(runs, baseline_run_id)

    if page == "Overview":
        _render_primary_selector(runs, selected_run)
        overview.render(repo, dataset_id, run_id)
    elif page == "Run Comparison":
        _render_comparison_selectors(runs, selected_run, baseline_run)
        comparison.render(repo, run_id, baseline_run_id)
    elif page == "Case Explorer":
        _render_primary_selector(runs, selected_run)
        cases.render(repo, run_id, baseline_run_id)
    else:
        _render_delete_evaluation(repo, runs, selected_run)


def _render_primary_selector(runs: list[dict], evaluation_a: dict, *, show_card: bool = True) -> None:
    with st.container(border=True):
        left, right = st.columns([2.4, 0.35], vertical_alignment="bottom")
        run_ids = [run["run_id"] for run in runs]
        with left:
            selected_a = st.selectbox(
                "Evaluation",
                run_ids,
                index=run_ids.index(evaluation_a["run_id"]),
                format_func=lambda run_id: _run_label(_run_by_id(runs, run_id) or {}),
                help="Type to search by run name, type, or status.",
            )
            if selected_a != st.session_state.candidate_run_id:
                st.session_state.candidate_run_id = selected_a
                st.session_state.pop("baseline_run_id", None)
                st.rerun()
        with right:
            if st.button("Refresh", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
    if show_card:
        _evaluation_card("Evaluation", evaluation_a)


def _render_comparison_selectors(runs: list[dict], evaluation_a: dict, evaluation_b: dict | None) -> None:
    run_ids = [run["run_id"] for run in runs]
    _, refresh = st.columns([1, 0.2], vertical_alignment="bottom")
    with refresh:
        if st.button("Refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    left, right = st.columns(2)

    with left:
        with st.popover(_comparison_picker_label("Evaluation A", evaluation_a), use_container_width=True):
            if st.session_state.get("comparison_a_selector") not in run_ids:
                st.session_state.comparison_a_selector = evaluation_a["run_id"]
            selected_a = st.selectbox(
                "Search evaluations",
                run_ids,
                format_func=lambda run_id: _run_label(_run_by_id(runs, run_id) or {}),
                key="comparison_a_selector",
            )
            if selected_a != st.session_state.candidate_run_id:
                st.session_state.candidate_run_id = selected_a
                st.session_state.pop("baseline_run_id", None)
                st.session_state.pop("comparison_b_selector", None)
                st.rerun()

    with right:
        options_b = [None] + [run_id for run_id in run_ids if run_id != evaluation_a["run_id"]]
        current_b = evaluation_b["run_id"] if evaluation_b else None
        with st.popover(_comparison_picker_label("Evaluation B", evaluation_b), use_container_width=True):
            if st.session_state.get("comparison_b_selector") not in options_b:
                st.session_state.comparison_b_selector = current_b
            selected_b = st.selectbox(
                "Search evaluations",
                options_b,
                format_func=lambda run_id: "No comparison" if run_id is None else _run_label(_run_by_id(runs, run_id) or {}),
                key="comparison_b_selector",
            )
            if selected_b != st.session_state.get("baseline_run_id"):
                st.session_state.baseline_run_id = selected_b
                st.rerun()

def _comparison_picker_label(title: str, run: dict | None) -> str:
    if not run:
        return f"{title}  |  Select evaluation"
    return f"{title}  |  {run.get('run_name') or 'Untitled evaluation'}  |  {run.get('status') or 'unknown'}"


def _evaluation_card(title: str, run: dict) -> None:
    st.markdown(
        f"""
        <div class="evaluation-card">
          <strong>{escape(title)}: {escape(str(run.get('run_name') or 'Untitled evaluation'))}</strong>
          <div class="evaluation-meta">
            Dataset {escape(str(run.get('dataset_name') or run.get('dataset_id') or 'Unknown'))} |
            {escape(str(run.get('run_type') or 'unknown'))} | {escape(str(run.get('status') or 'unknown'))} | {_case_progress(run)} cases | top_k {escape(str(run.get('top_k') or 'Unknown'))}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_delete_evaluation(repo: EvaluationRepository, runs: list[dict], selected_run: dict) -> None:
    st.markdown("### Delete Evaluation")
    alert("This permanently deletes the selected evaluation and its results.")
    _render_primary_selector(runs, selected_run, show_card=False)
    st.markdown(
        f"""
        <div class="delete-summary">
          <strong>{escape(str(selected_run.get('run_name') or 'Untitled evaluation'))}</strong>
          <span>{escape(str(selected_run.get('dataset_name') or selected_run.get('dataset_id') or 'Unknown dataset'))} | {escape(str(selected_run.get('status') or 'unknown'))}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Copy this run_id into the confirmation field.")
    st.code(selected_run["run_id"], language=None)
    confirm = st.text_input("Type the exact run_id to confirm", key="delete_run_confirm_page")
    can_delete = confirm == selected_run["run_id"] and selected_run.get("status") != "running"
    if selected_run.get("status") == "running":
        alert("A running evaluation cannot be deleted.")
    if st.button("Delete evaluation", disabled=not can_delete, type="primary", use_container_width=True):
        try:
            deleted = repo.delete_run(selected_run["run_id"])
        except Exception as exc:
            alert(f"Could not delete the evaluation: {exc}")
        else:
            if deleted:
                st.cache_data.clear()
                st.session_state.pop("candidate_run_id", None)
                st.session_state.pop("baseline_run_id", None)
                st.success("Evaluation deleted.")
                st.rerun()
            else:
                alert("The evaluation no longer exists.")


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
