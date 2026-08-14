"""Reusable Streamlit components for the dashboard."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

import streamlit as st

from dashboard.config import APP_SUBTITLE, APP_TITLE


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_score(value: Any, unit: str = "score") -> str:
    number = _to_float(value)
    if number is None:
        return "N/A"
    if unit == "percent":
        return f"{number * 100:.1f}%"
    if unit == "milliseconds":
        if number >= 1000:
            return f"{number / 1000:.2f} s"
        return f"{number:.0f} ms"
    if unit == "currency":
        return f"${number:.4f}"
    if unit in {"count", "tokens"}:
        return f"{number:,.0f}"
    return f"{number:.3f}" if abs(number) < 10 else f"{number:,.1f}"


def format_delta(value: Any, unit: str = "score") -> str:
    number = _to_float(value)
    if number is None:
        return "No baseline"
    sign = "+" if number > 0 else ""
    if unit == "percent":
        return f"{sign}{number * 100:.1f} pp"
    if unit == "milliseconds":
        return f"{sign}{number:.0f} ms"
    if unit in {"count", "tokens"}:
        return f"{sign}{number:,.0f}"
    return f"{sign}{number:.3f}"


def header(status: str | None = None) -> None:
    status_class = "completed" if status == "completed" else "warning"
    status_text = escape(status.upper()) if status else "ONLINE"
    st.markdown(
        f"""
        <div class="dashboard-header">
          <div class="header-content" style="display:flex; justify-content:space-between; gap:1rem; align-items:flex-start; flex-wrap:wrap;">
            <div class="header-copy">
              <div class="title-kicker">Retrieval Quality Console</div>
              <h1><span class="brand-title">Aviation RAG</span> <span class="brand-accent">Evaluations</span></h1>
              <p>{escape(APP_SUBTITLE)} / baseline comparison / case diagnostics</p>
            </div>
            <span class="status-pill {status_class}">STATUS {status_text}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(
    label: str,
    value: Any,
    delta: Any = None,
    unit: str = "percent",
    sample_count: Any = None,
    normalized_delta: Any = None,
) -> None:
    direction = _to_float(normalized_delta if normalized_delta is not None else delta)
    if direction is None or direction == 0:
        delta_class = "delta-neutral"
    elif direction > 0:
        delta_class = "delta-good"
    else:
        delta_class = "delta-bad"

    sample = "" if sample_count is None else f"<div class='small-muted'>n = {escape(str(sample_count))}</div>"
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-label">{escape(label)}</div>
          <div class="kpi-value">{escape(format_score(value, unit))}</div>
          <div class="kpi-delta {delta_class}">{escape(format_delta(delta, unit))}</div>
          {sample}
        </div>
        """,
        unsafe_allow_html=True,
    )


def panel_title(title: str) -> None:
    st.markdown(f"<div class='panel-title'>{escape(title)}</div>", unsafe_allow_html=True)


def alert(message: str) -> None:
    st.markdown(
        f"<div class='alert-card'>{escape(message)}</div>", unsafe_allow_html=True
    )


def safe_json(data: Any) -> None:
    if not data:
        st.caption("No public configuration values available.")
        return
    st.json(data, expanded=False)
