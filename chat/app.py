"""Streamlit chat UI for the aviation RAG agent."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import streamlit.components.v1 as components

from chat import config
from chat.components import (
    format_tokens,
    group_sessions,
    render_landing,
    render_message,
    render_sidebar_brand,
    render_topbar,
    session_label,
    session_total_tokens,
)
from chat.runtime import get_runtime
from chat.styles import CSS


def main() -> None:
    st.set_page_config(
        page_title=config.APP_TITLE,
        page_icon=config.PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    try:
        runtime = get_runtime()
    except Exception as exc:
        render_startup_error(exc)
        return

    if "active_session_id" not in st.session_state:
        st.session_state.active_session_id = None
    if "new_chat_mode" not in st.session_state:
        st.session_state.new_chat_mode = False
    if "pending_turn" not in st.session_state:
        st.session_state.pending_turn = None

    process_query_params()

    with st.sidebar:
        render_sidebar_brand(config.APP_TITLE, config.APP_TAGLINE)
        if st.button("+ New chat", use_container_width=True):
            st.session_state.active_session_id = None
            st.session_state.new_chat_mode = True
            st.query_params.clear()
            st.rerun()

        search = st.text_input("Search conversations", placeholder="Search chats", label_visibility="collapsed")
        sessions = runtime.list_sessions(limit=config.DEFAULT_SESSION_LIMIT, search=search or None)
        if st.session_state.active_session_id is None and sessions and not st.session_state.new_chat_mode:
            st.session_state.active_session_id = sessions[0].id

        render_session_list(runtime, sessions)
        render_sidebar_footer(runtime.model_name, sessions)

    active_session_id = st.session_state.active_session_id
    if not active_session_id:
        render_landing(config.APP_TITLE, config.APP_TAGLINE)
        prompt = render_composer(runtime.model_name, key="new_chat")
        if prompt:
            active_session_id = runtime.create_session()
            st.session_state.active_session_id = active_session_id
            st.session_state.new_chat_mode = False
            st.session_state.pending_turn = {"session_id": active_session_id, "prompt": prompt}
            st.rerun()
        return

    sessions_by_id = {session.id: session for session in runtime.list_sessions(limit=config.DEFAULT_SESSION_LIMIT)}
    active_session = sessions_by_id.get(active_session_id)
    title = session_label(active_session) if active_session else "Untitled chat"

    messages = runtime.load_messages(active_session_id)
    render_topbar(
        title,
        model_name=runtime.model_name,
        total_tokens=session_total_tokens(messages),
        message_count=len(messages),
    )

    for message in messages:
        render_message(message, model_name=runtime.model_name)

    pending_turn = st.session_state.pending_turn
    if pending_turn and pending_turn.get("session_id") == active_session_id:
        st.session_state.pending_turn = None
        run_turn(runtime, active_session_id, str(pending_turn.get("prompt") or ""))
        return

    prompt = render_composer(runtime.model_name, key=f"composer_{active_session_id}")
    if prompt:
        st.session_state.pending_turn = {"session_id": active_session_id, "prompt": prompt}
        st.rerun()
    scroll_to_bottom()


def process_query_params() -> None:
    session_id = query_param("session")
    if session_id:
        st.session_state.active_session_id = session_id
        st.session_state.new_chat_mode = False


def query_param(name: str) -> str | None:
    value = st.query_params.get(name)
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value else None


def render_session_list(runtime, sessions) -> None:
    grouped = group_sessions(sessions)
    for group_name in ("Today", "Previous 7 days", "Older"):
        group = grouped.get(group_name) or []
        if not group:
            continue
        st.markdown(f'<div class="sidebar-section">{group_name}</div>', unsafe_allow_html=True)
        for session in group:
            if session.id == st.session_state.active_session_id:
                st.text_input(
                    "Chat title",
                    value=session_label(session),
                    key=f"inline_title_{session.id}",
                    label_visibility="collapsed",
                    on_change=save_inline_title,
                    args=(runtime, session.id, f"inline_title_{session.id}"),
                )
            elif st.button(session_label(session), key=f"open_{session.id}", use_container_width=True):
                st.session_state.active_session_id = session.id
                st.session_state.new_chat_mode = False
                st.query_params.clear()
                st.rerun()


def save_inline_title(runtime, session_id: str, key: str) -> None:
    title = str(st.session_state.get(key) or "").strip()
    if title:
        runtime.rename_session(session_id, title)


def render_sidebar_footer(model_name: str, sessions) -> None:
    total_tokens = sum(int(session.total_tokens or 0) for session in sessions)
    st.markdown(
        '<div class="sidebar-runtime">' f'{model_name} &middot; {format_tokens(total_tokens)} tokens' '</div>',
        unsafe_allow_html=True,
    )


def render_composer(model_name: str, *, key: str) -> str | None:
    st.markdown('<div class="composer-shell">', unsafe_allow_html=True)
    with st.form(key=f"form_{key}", clear_on_submit=True, border=False):
        prompt = st.text_area(
            "Message",
            placeholder="Ask anything about manuals, procedures or accident records...",
            key=f"input_{key}",
            label_visibility="collapsed",
            height=132,
        )
        meta_col, send_col = st.columns([0.78, 0.22], vertical_alignment="center")
        with meta_col:
            st.markdown(
                f'<div class="composer-meta">+ &nbsp; Evidence-first &nbsp; {model_name} &nbsp; Tokens tracked</div>',
                unsafe_allow_html=True,
            )
        with send_col:
            submitted = st.form_submit_button("Send", use_container_width=True, type="primary")
    st.markdown('</div>', unsafe_allow_html=True)
    if submitted and prompt.strip():
        return prompt.strip()
    return None


def run_turn(runtime, session_id: str, prompt: str) -> None:
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        status = st.status("Understanding your question", expanded=True)
        try:
            status.write("Checking safety and resolving context")
            status.write("Routing to documents, NTSB records or both")
            status.write("Retrieving supporting evidence")
            status.write("Preparing grounded answer and citations")
            result = runtime.ask(session_id, prompt)
        except Exception as exc:
            status.update(label="Request failed", state="error")
            st.error(safe_error_message(exc))
            scroll_to_bottom()
            return
        status.update(label="Answer ready", state="complete", expanded=False)
        st.markdown(result.answer)
    scroll_to_bottom()
    st.rerun()


def scroll_to_bottom() -> None:
    components.html(
        """
        <script>
        window.parent.scrollTo({ top: window.parent.document.body.scrollHeight, behavior: 'smooth' });
        </script>
        """,
        height=0,
    )


def render_startup_error(exc: Exception) -> None:
    st.error("The chat runtime could not start.")
    st.caption(safe_error_message(exc))
    text = str(exc)
    if any(marker in text for marker in ("Prompt Guard", "torch", "transformers", "HF_TOKEN", "License")):
        st.info("Prompt Guard is prepared automatically on startup. If this failed, check HF_TOKEN, model license access and network connectivity.")
    else:
        st.info("Check DATABASE_URL, OPENAI_API_KEY and that the database schema has been applied.")


def safe_error_message(exc: Exception) -> str:
    name = exc.__class__.__name__
    text = str(exc).strip()
    if not text:
        return name
    if len(text) > 260:
        text = text[:257].rstrip() + "..."
    return f"{name}: {text}"


if __name__ == "__main__":
    main()
