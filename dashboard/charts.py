"""Plotly chart factories for the evaluation dashboard."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import plotly.graph_objects as go

from dashboard.queries import metric_definition, normalized_delta


PLOTLY_TEMPLATE = "plotly_white"
CYAN = "#22C7D6"
AMBER = "#F5A524"
GREEN = "#23BFA5"
RED = "#EF6474"
NAVY = "#102536"
MUTED = "#66798B"


def _float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _base_layout(fig: go.Figure, height: int = 320) -> go.Figure:
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        height=height,
        margin=dict(l=12, r=12, t=34, b=18),
        font=dict(color=NAVY),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(244,247,249,0.55)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="#DDE7ED", zeroline=False)
    return fig


def _score_text(value: Any) -> str:
    number = _float(value)
    return "N/A" if number is None else f"{number:.3f}"


def metric_history(
    rows: list[dict[str, Any]],
    metric_name: str,
    selected_run_id: str | None = None,
    baseline_run_id: str | None = None,
) -> go.Figure:
    label = metric_definition(metric_name).label
    fig = go.Figure()
    colors = []
    sizes = []
    symbols = []
    for row in rows:
        if row.get("run_id") == selected_run_id:
            colors.append(GREEN)
            sizes.append(13)
            symbols.append("diamond")
        elif row.get("run_id") == baseline_run_id:
            colors.append(AMBER)
            sizes.append(12)
            symbols.append("square")
        else:
            colors.append(CYAN)
            sizes.append(8)
            symbols.append("circle")
    fig.add_trace(
        go.Scatter(
            x=[row.get("started_at") for row in rows],
            y=[_float(row.get("mean_score")) for row in rows],
            mode="lines+markers",
            line=dict(color=CYAN, width=2.5),
            marker=dict(size=sizes, color=colors, symbol=symbols, line=dict(color="white", width=1.5)),
            text=[row.get("run_name") for row in rows],
            customdata=[[row.get("run_type"), row.get("sample_count")] for row in rows],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Type: %{customdata[0]}<br>"
                f"{label}: %{{y:.3f}}<br>"
                "Cases: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_yaxes(title=label, range=[0, 1] if rows and all((_float(row.get("mean_score")) or 0) <= 1 for row in rows) else None)
    fig.update_xaxes(title="Run date")
    return _base_layout(fig)


def breakdown_bar(rows: list[dict[str, Any]], metric_name: str = "mrr") -> go.Figure:
    labels = [str(row.get("dimension_value") or "Unknown") for row in rows]
    values = [_float(row.get("mean_score")) for row in rows]
    samples = [int(row.get("sample_count") or 0) for row in rows]
    colors = [GREEN if (value or 0) >= 0.8 else AMBER if (value or 0) >= 0.5 else RED for value in values]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=colors),
            text=[
                f"{value:.2f} | n={sample}" if value is not None else f"N/A | n={sample}"
                for value, sample in zip(values, samples)
            ],
            textposition="outside",
            customdata=samples,
            hovertemplate=(
                "<b>%{y}</b><br>"
                f"{metric_definition(metric_name).label}: %{{x:.3f}}<br>"
                "Cases: %{customdata}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title=metric_definition(metric_name).label, range=[0, 1.08])
    fig.update_yaxes(autorange="reversed")
    return _base_layout(fig, height=max(280, 42 * len(rows) + 80))


def comparison_bar(rows: list[dict[str, Any]]) -> go.Figure:
    labels = [metric_definition(row["metric_name"]).label for row in rows]
    baseline = [_float(row.get("baseline_mean")) for row in rows]
    candidate = [_float(row.get("candidate_mean")) for row in rows]
    deltas = [_float(row.get("mean_delta")) for row in rows]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Baseline", y=labels, x=baseline, orientation="h", marker_color=MUTED))
    fig.add_trace(go.Bar(name="Candidate", y=labels, x=candidate, orientation="h", marker_color=CYAN))
    fig.add_trace(
        go.Scatter(
            name="Delta",
            y=labels,
            x=candidate,
            mode="text",
            text=["" if delta is None else f"{delta:+.3f}" for delta in deltas],
            textposition="middle right",
            textfont=dict(color=NAVY, size=12),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Mean score", range=[0, 1.12])
    return _base_layout(fig, height=360)


def delta_distribution(rows: list[dict[str, Any]]) -> go.Figure:
    values = [_float(row.get("delta")) for row in rows if row.get("delta") is not None]
    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=values,
            marker_color=CYAN,
            opacity=0.85,
            nbinsx=18,
            hovertemplate="Delta %{x:.3f}<br>Cases %{y}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_color=AMBER, line_width=2)
    fig.update_xaxes(title="Candidate - baseline")
    fig.update_yaxes(title="Cases")
    return _base_layout(fig, height=300)


def quality_latency_scatter(
    rows: list[dict[str, Any]],
    metric_name: str,
    selected_run_id: str | None = None,
    baseline_run_id: str | None = None,
) -> go.Figure:
    label = metric_definition(metric_name).label
    fig = go.Figure()
    colors = []
    sizes = []
    symbols = []
    for row in rows:
        if row.get("run_id") == selected_run_id:
            colors.append(GREEN)
            sizes.append(18)
            symbols.append("diamond")
        elif row.get("run_id") == baseline_run_id:
            colors.append(AMBER)
            sizes.append(16)
            symbols.append("square")
        elif row.get("run_type") == "baseline":
            colors.append(MUTED)
            sizes.append(12)
            symbols.append("square")
        else:
            colors.append(CYAN)
            sizes.append(12)
            symbols.append("circle")

    fig.add_trace(
        go.Scatter(
            x=[_float(row.get("p95_latency_ms")) for row in rows],
            y=[_float(row.get("mean_score")) for row in rows],
            mode="markers+text",
            text=[row.get("run_name") for row in rows],
            textposition="top center",
            marker=dict(size=sizes, color=colors, symbol=symbols, line=dict(color="white", width=1.5)),
            customdata=[
                [row.get("run_type"), row.get("metric_cases"), row.get("avg_latency_ms"), row.get("prompt_version")]
                for row in rows
            ],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Type: %{customdata[0]}<br>"
                f"{label}: %{{y:.3f}}<br>"
                "p95 latency: %{x:.0f} ms<br>"
                "avg latency: %{customdata[2]:.0f} ms<br>"
                "Cases: %{customdata[1]}<br>"
                "Prompt: %{customdata[3]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title="p95 latency (ms)")
    fig.update_yaxes(title=label, range=[0, 1.05])
    return _base_layout(fig, height=360)


def baseline_candidate_scatter(rows: list[dict[str, Any]], metric_name: str) -> go.Figure:
    label = metric_definition(metric_name).label
    fig = go.Figure()
    points = [row for row in rows if row.get("baseline_score") is not None and row.get("candidate_score") is not None]
    colors = []
    for row in points:
        ndelta = normalized_delta(metric_name, _float(row.get("delta")))
        colors.append(GREEN if ndelta and ndelta > 0 else RED if ndelta and ndelta < 0 else MUTED)
    fig.add_trace(
        go.Scatter(
            x=[_float(row.get("baseline_score")) for row in points],
            y=[_float(row.get("candidate_score")) for row in points],
            mode="markers",
            marker=dict(size=12, color=colors, opacity=0.85, line=dict(color="white", width=1.2)),
            text=[row.get("case_id") for row in points],
            customdata=[[row.get("category"), row.get("delta"), row.get("question")] for row in points],
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Category: %{customdata[0]}<br>"
                "Baseline: %{x:.3f}<br>"
                "Candidate: %{y:.3f}<br>"
                "Delta: %{customdata[1]:+.3f}<br>"
                "%{customdata[2]}<extra></extra>"
            ),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(color=AMBER, dash="dash", width=2),
            hoverinfo="skip",
            showlegend=False,
        )
    )
    fig.update_xaxes(title=f"Baseline {label}", range=[-0.03, 1.03])
    fig.update_yaxes(title=f"Candidate {label}", range=[-0.03, 1.03])
    return _base_layout(fig, height=360)


def case_delta_bar(rows: list[dict[str, Any]], metric_name: str, limit: int = 12) -> go.Figure:
    movable = [row for row in rows if row.get("delta") is not None]
    movable.sort(key=lambda row: abs(float(row.get("delta") or 0)), reverse=True)
    top = movable[:limit]
    labels = [str(row.get("case_id")) for row in top]
    deltas = [_float(row.get("delta")) for row in top]
    colors = []
    for delta in deltas:
        ndelta = normalized_delta(metric_name, delta)
        colors.append(GREEN if ndelta and ndelta > 0 else RED if ndelta and ndelta < 0 else MUTED)
    fig = go.Figure(
        go.Bar(
            x=deltas,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=["" if delta is None else f"{delta:+.3f}" for delta in deltas],
            textposition="outside",
            customdata=[[row.get("category"), row.get("question")] for row in top],
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Category: %{customdata[0]}<br>"
                "Delta: %{x:+.3f}<br>"
                "%{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_color=AMBER, line_width=2)
    fig.update_xaxes(title="Candidate - baseline")
    fig.update_yaxes(autorange="reversed", title="Case")
    return _base_layout(fig, height=max(320, 28 * len(top) + 100))
