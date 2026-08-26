"""Reusable Streamlit components for the chat app."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from typing import Any

import streamlit as st

from agent.memory import ConversationMessage, ConversationSession


def format_tokens(value: int | None) -> str:
    tokens = int(value or 0)
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k"
    return str(tokens)


def format_ms(value: float | None) -> str:
    ms = float(value or 0)
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def session_label(session: ConversationSession) -> str:
    title = (session.title or "Untitled chat").strip()
    if len(title) > 38:
        title = title[:35].rstrip() + "..."
    return title


def render_sidebar_brand(app_title: str, tagline: str) -> None:
    st.markdown(
        f"""
        <div class="sidebar-brand">
          <h2>{escape(app_title)}</h2>
          <p>{escape(tagline)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_topbar(title: str, *, model_name: str, total_tokens: int, message_count: int) -> None:
    st.markdown(
        f"""
        <div class="chat-topbar">
          <div>
            <h1 class="chat-title">{escape(title)}</h1>
          </div>
          <div class="topbar-meta">
            {escape(model_name)} &middot; {escape(format_tokens(total_tokens))} tokens &middot; {message_count} messages
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_landing(app_title: str, tagline: str) -> None:
    examples = [
        "Compare Cessna 172 stall recovery guidance with related NTSB stall accidents.",
        "What evidence exists for loss-of-control accidents involving Piper aircraft?",
        "Summarize the operational limitations supported by the retrieved manual evidence.",
        "Find accident records where weather or visibility was a relevant factor.",
    ]
    cards = "".join(f'<div class="example-card">{escape(example)}</div>' for example in examples)
    st.markdown(
        f"""
        <div class="landing-card">
          <h1>{escape(app_title)}</h1>
          <p>{escape(tagline)}. Ask about technical documents, NTSB records, or both in one turn.</p>
          <div class="example-grid">{cards}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_message(message: ConversationMessage, *, model_name: str) -> None:
    with st.chat_message(message.role):
        st.markdown(message.content)
        if message.role == "assistant":
            render_answer_metadata(message.metadata, model_name=model_name)
            render_sources(message.metadata)


def render_answer_metadata(metadata: dict[str, Any], *, model_name: str) -> None:
    usage = metadata.get("token_usage") or {}
    timings = metadata.get("timings_ms") or {}
    route = metadata.get("route") or {}
    total_tokens = int(usage.get("total_tokens") or 0)
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    estimated = " estimated" if usage.get("estimated") else ""
    route_name = str(route.get("route") or "unknown").replace("_", " ").title()
    evidence_count = len(metadata.get("evidence_ids") or [])
    st.markdown(
        f"""
        <div class="answer-meta">
          Sources {evidence_count} &middot;
          {escape(format_tokens(total_tokens))} tokens{escape(estimated)} &middot;
          {escape(format_ms(timings.get('total')))} &middot;
          {escape(route_name)} &middot;
          {escape(str(metadata.get('model_name') or model_name))}
          <span class="chat-subtitle">(in {escape(format_tokens(input_tokens))} / out {escape(format_tokens(output_tokens))})</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    warnings = [str(item) for item in metadata.get("warnings") or [] if item]
    if warnings:
        with st.expander("Warnings", expanded=False):
            for warning in warnings:
                st.warning(warning)


def render_sources(metadata: dict[str, Any]) -> None:
    evidence = list(metadata.get("evidence") or [])
    used_ids = list(metadata.get("evidence_ids") or [])
    if used_ids:
        used = set(used_ids)
        evidence = [item for item in evidence if item.get("evidence_id") in used]
    if not evidence:
        return
    with st.expander(f"Sources ({len(evidence)})", expanded=False):
        for item in evidence:
            render_source_card(item)


def render_source_card(item: dict[str, Any]) -> None:
    metadata = item.get("metadata") or {}
    source_id = str(item.get("evidence_id") or "source")
    source_kind = str(item.get("source_kind") or "source").replace("_", " ").title()
    source_name = str(item.get("source_name") or "Unknown source")
    record_id = item.get("source_record_id") or metadata.get("ntsb_number") or metadata.get("mkey") or ""
    score = item.get("score")
    score_text = f" | score {float(score):.3f}" if isinstance(score, (int, float)) else ""
    text = str(item.get("text") or "")
    if len(text) > 900:
        text = text[:897].rstrip() + "..."
    st.markdown(
        f"""
        <div class="source-card">
          <div><strong>{escape(source_id)}</strong> &middot; {escape(source_kind)} &middot; {escape(source_name)}</div>
          <div class="chat-subtitle">Record: {escape(str(record_id))}{escape(score_text)}</div>
          <div class="source-text">{escape(text)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def group_sessions(sessions: list[ConversationSession]) -> dict[str, list[ConversationSession]]:
    grouped: dict[str, list[ConversationSession]] = defaultdict(list)
    now = datetime.now(timezone.utc)
    for session in sessions:
        updated = session.updated_at
        if updated is None:
            grouped["Older"].append(session)
            continue
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_days = (now - updated).days
        if age_days <= 0:
            grouped["Today"].append(session)
        elif age_days <= 7:
            grouped["Previous 7 days"].append(session)
        else:
            grouped["Older"].append(session)
    return grouped


def session_total_tokens(messages: list[ConversationMessage]) -> int:
    total = 0
    for message in messages:
        if message.role != "assistant":
            continue
        usage = message.metadata.get("token_usage") or {}
        total += int(usage.get("total_tokens") or 0)
    return total
