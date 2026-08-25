"""Tool wrappers around the existing document, NTSB index and NTSB API paths."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langsmith import traceable

from agent.dependencies import AgentDependencies
from agent.schemas import EvidenceItem, ToolResult


def _document_evidence_id(index: int) -> str:
    return f"DOC-{index:03d}"


def _ntsb_evidence_id(index: int, *, api: bool = False) -> str:
    prefix = "NTSB-API" if api else "NTSB"
    return f"{prefix}-{index:03d}"


def document_row_to_evidence(row: dict[str, Any], index: int) -> EvidenceItem:
    source_name = str(row.get("font") or row.get("source") or "document")
    record_id = row.get("parent_id") or row.get("chunk_id") or row.get("document_id")
    return EvidenceItem(
        evidence_id=_document_evidence_id(index),
        source_kind="embedded_document",
        source_name=source_name,
        source_record_id=str(record_id) if record_id is not None else None,
        text=str(row.get("texto") or ""),
        score=float(row["similarity"]) if row.get("similarity") is not None else None,
        metadata={
            "aircraft": row.get("aircraft"),
            "font": row.get("font"),
            "chunk_id": row.get("chunk_id"),
            "parent_id": row.get("parent_id"),
            "document_id": row.get("document_id"),
            "source_file": row.get("source_file"),
            "rrf_score": row.get("rrf_score"),
        },
    )


def ntsb_context_item_to_evidence(item: dict[str, Any], index: int, *, api: bool = False) -> EvidenceItem:
    record_id = item.get("ntsb_number") or item.get("mkey") or item.get("font")
    return EvidenceItem(
        evidence_id=_ntsb_evidence_id(index, api=api),
        source_kind="ntsb_api" if api else "ntsb_index",
        source_name=str(item.get("font") or "NTSB"),
        source_record_id=str(record_id) if record_id is not None else None,
        text=str(item.get("texto") or ""),
        metadata={
            "aircraft": item.get("aircraft"),
            "ntsb_number": item.get("ntsb_number"),
            "mkey": item.get("mkey"),
            "event_date": item.get("event_date"),
            "source": item.get("source"),
        },
    )


class LazyDocumentRepository:
    """Adapter for the existing import-time-heavy document retriever."""

    async def search(self, query: str, aircraft: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
        def _run() -> list[dict[str, Any]]:
            from rag.retrieval import search_context

            return list(search_context(query, aircraft=aircraft, top_k=top_k))

        return await asyncio.to_thread(_run)


class NTSBDetailClient:
    """Small safe wrapper exposing only single-case NTSB detail fetches."""

    async def fetch_case_detail(self, *, ntsb_number: str | None = None, mkey: int | str | None = None) -> Any:
        from ntsb.sync.api_client import NTSBAPIClient

        client = NTSBAPIClient()
        return await client.get_aviation_case(ntsb_number=ntsb_number, mkey=mkey)


class AgentTools:
    def __init__(self, deps: AgentDependencies):
        self.deps = deps

    @traceable(run_type="tool", name="search_embedded_documents")
    async def search_embedded_documents(
        self,
        query: str,
        aircraft: str | None = None,
        top_k: int | None = None,
    ) -> ToolResult:
        started = time.perf_counter()
        query = str(query or "").strip()
        if not query:
            raise ValueError("query is required")
        limit = max(1, min(int(top_k or self.deps.max_document_results), 10))
        repository = self.deps.document_repository or LazyDocumentRepository()
        rows = await repository.search(query, aircraft=aircraft, top_k=limit)
        evidence = [document_row_to_evidence(row, index) for index, row in enumerate(rows, start=1)]
        return ToolResult(
            tool_name="search_embedded_documents",
            evidence=evidence,
            total_matches=len(evidence),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @traceable(run_type="tool", name="search_accident_index")
    async def search_accident_index(self, question: str) -> ToolResult:
        started = time.perf_counter()
        question = str(question or "").strip()
        if not question:
            raise ValueError("question is required")
        if self.deps.planner_client is None:
            raise ValueError("planner_client is required for NTSB accident searches")

        def _run() -> Any:
            from ntsb.planner import plan_query
            from ntsb.postgres_repository import PostgresNTSBCaseRepository

            query = plan_query(self.deps.planner_client, question, self.deps.model_name)
            query.limit = min(query.limit, self.deps.max_accident_results)
            repository = self.deps.accident_repository or PostgresNTSBCaseRepository()
            return repository.search(query)

        result = await asyncio.to_thread(_run)
        context_items = result.context_items()
        evidence = [
            ntsb_context_item_to_evidence(item, index)
            for index, item in enumerate(context_items, start=1)
        ]
        return ToolResult(
            tool_name="search_accident_index",
            evidence=evidence,
            total_matches=result.total_matches,
            stale=bool(result.stale),
            warnings=list(result.warnings),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    @traceable(run_type="tool", name="fetch_ntsb_case_detail")
    async def fetch_ntsb_case_detail(
        self,
        *,
        ntsb_number: str | None = None,
        mkey: int | str | None = None,
    ) -> ToolResult:
        started = time.perf_counter()
        if not ntsb_number and mkey is None:
            raise ValueError("ntsb_number or mkey is required")
        client = self.deps.detail_client or NTSBDetailClient()
        raw = await client.fetch_case_detail(ntsb_number=ntsb_number, mkey=mkey)
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        if raw:
            from ntsb.context import detail_payload_to_context

            evidence.append(
                EvidenceItem(
                    evidence_id="NTSB-API-001",
                    source_kind="ntsb_api",
                    source_name="NTSB API",
                    source_record_id=str(ntsb_number or mkey),
                    text=detail_payload_to_context(raw),
                    metadata={"ntsb_number": ntsb_number, "mkey": mkey},
                )
            )
        else:
            warnings.append("NTSB API returned no detail payload for the selected case.")
        return ToolResult(
            tool_name="fetch_ntsb_case_detail",
            evidence=evidence,
            total_matches=len(evidence),
            warnings=warnings,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    def as_langchain_tools(self):
        """Expose wrappers as LangChain tools for experiments; the graph calls methods directly."""
        from langchain_core.tools import StructuredTool

        return [
            StructuredTool.from_function(coroutine=self.search_embedded_documents),
            StructuredTool.from_function(coroutine=self.search_accident_index),
            StructuredTool.from_function(coroutine=self.fetch_ntsb_case_detail),
        ]
