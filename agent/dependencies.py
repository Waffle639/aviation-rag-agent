"""Dependency container and small protocols for the aviation agent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class DocumentRepository(Protocol):
    async def search(self, query: str, aircraft: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        ...


class AccidentRepository(Protocol):
    def search(self, query: Any) -> Any:
        ...


class DetailClient(Protocol):
    async def fetch_case_detail(self, *, ntsb_number: str | None = None, mkey: int | str | None = None) -> Any:
        ...


class ConversationMemoryStore(Protocol):
    def create_session(self) -> str:
        ...

    def session_exists(self, session_id: str) -> bool:
        ...

    def load_context(self, session_id: str, *, recent_token_budget: int) -> Any:
        ...

    def append_message(self, session_id: str, *, role: str, content: str, metadata: dict[str, Any] | None = None) -> int:
        ...

    def compact_if_needed(self, session_id: str, **kwargs: Any) -> bool:
        ...


@dataclass
class AgentDependencies:
    document_repository: DocumentRepository | None = None
    accident_repository: AccidentRepository | None = None
    detail_client: DetailClient | None = None
    memory_store: ConversationMemoryStore | None = None
    router_model: Any | None = None
    generator_client: Any | None = None
    planner_client: Any | None = None
    model_name: str = "gpt-5.4-mini"
    max_document_results: int = 5
    max_accident_results: int = 10
    max_ntsb_detail_calls: int = 3
    max_output_tokens: int = 2000
    max_input_tokens: int = 24000
    max_evidence_tokens: int = 16000
    max_memory_tokens: int = 1500
    context_safety_margin_tokens: int = 1000
    memory_compaction_trigger_tokens: int = 3000
    memory_keep_recent_messages: int = 4
    max_summary_tokens: int = 600
