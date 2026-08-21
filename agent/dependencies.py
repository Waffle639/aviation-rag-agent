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


@dataclass
class AgentDependencies:
    document_repository: DocumentRepository | None = None
    accident_repository: AccidentRepository | None = None
    detail_client: DetailClient | None = None
    router_model: Any | None = None
    generator_client: Any | None = None
    planner_client: Any | None = None
    model_name: str = "gpt-5.4-mini"
    max_document_results: int = 5
    max_accident_results: int = 10
    max_ntsb_detail_calls: int = 3
