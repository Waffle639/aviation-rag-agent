"""Runtime adapters between Streamlit and the async aviation agent."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os

import streamlit as st
from dotenv import load_dotenv

from agent.memory import ConversationMessage, ConversationSession, PostgresConversationMemoryStore
from agent.schemas import AgentResult
from agent.service import AviationAgentService, build_default_dependencies
from rag.guardrails import warmup_security


@dataclass
class ChatRuntime:
    service: AviationAgentService
    store: PostgresConversationMemoryStore
    model_name: str

    def create_session(self) -> str:
        return self.store.create_session()

    def list_sessions(self, *, limit: int, search: str | None = None) -> list[ConversationSession]:
        return self.store.list_sessions(limit=limit, search=search)

    def load_messages(self, session_id: str) -> list[ConversationMessage]:
        return self.store.load_messages(session_id)

    def rename_session(self, session_id: str, title: str) -> None:
        self.store.rename_session(session_id, title)

    def delete_session(self, session_id: str) -> None:
        self.store.delete_session(session_id)

    def ask(self, session_id: str, question: str) -> AgentResult:
        self.store.set_title_if_empty(session_id, title_from_question(question))
        return asyncio.run(self.service.arun(question, session_id=session_id))


@st.cache_resource(show_spinner="Preparing Prompt Guard and chat runtime...")
def get_runtime() -> ChatRuntime:
    load_dotenv()
    prepare_prompt_guard()
    store = PostgresConversationMemoryStore()
    store.ensure_chat_schema()
    deps = build_default_dependencies()
    deps.memory_store = store
    service = AviationAgentService(deps)
    return ChatRuntime(service=service, store=store, model_name=deps.model_name)


def prepare_prompt_guard() -> None:
    if os.getenv("RAG_SECURITY", "true").lower() in ("false", "0", "no", "off"):
        return

    from rag import setup_security

    ok, message = setup_security.check_torch()
    if not ok:
        if os.getenv("CHAT_AUTO_INSTALL_SECURITY_DEPS", "true").lower() in ("false", "0", "no", "off"):
            raise RuntimeError(message)
        ok, message = setup_security.install_torch()
        if not ok:
            raise RuntimeError(f"Could not install Prompt Guard dependencies automatically: {message}")

    ok, _ = setup_security.check_model()
    if not ok:
        ok, message = setup_security.check_hf_token()
        if not ok:
            raise RuntimeError(message)
        ok, message = setup_security.check_license()
        if not ok:
            raise RuntimeError(message)
        ok, message = setup_security.ensure_model_downloaded()
        if not ok:
            raise RuntimeError(message)

    warmup_security()


def title_from_question(question: str) -> str:
    words = " ".join(str(question or "").strip().split())
    if not words:
        return "Untitled chat"
    if len(words) <= 64:
        return words
    return words[:61].rstrip() + "..."
