import json
import asyncio
from types import SimpleNamespace

import pytest

from agent.dependencies import AgentDependencies
from agent.service import AviationAgentService


class FakeDocumentRepository:
    async def search(self, query, aircraft=None, top_k=5):
        return [
            {
                "texto": "The Cessna 172 manual describes stall recovery with nose-down pitch.",
                "aircraft": "Cessna 172",
                "font": "manual",
                "chunk_id": "c1",
                "parent_id": "p1",
                "similarity": 0.9,
            }
        ]


class FakePlannerClient:
    class responses:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "intent": "search",
                        "goal": "search",
                        "ntsb_number": None,
                        "mkey": None,
                        "registration": None,
                        "start_date": None,
                        "end_date": None,
                        "make": "Cessna",
                        "model": "172",
                        "location": None,
                        "state": None,
                        "country": None,
                        "severity": None,
                        "event_type": None,
                        "investigation_status": None,
                        "text": "stall",
                        "needs_detail": False,
                        "sort": "date_desc",
                        "limit": 5,
                        "ranking_field": None,
                        "ranking_order": "desc",
                        "requested_fields": ["narrative"],
                    }
                )
            )


class FakeAccidentRepository:
    def search(self, query):
        from ntsb.domain import NTSBAircraft, NTSBCase, NTSBSearchResult

        return NTSBSearchResult(
            cases=[
                NTSBCase(
                    ntsb_number="WPR23FA001",
                    mkey=123,
                    aircraft_list=[NTSBAircraft(make="Cessna", model="172")],
                    narrative="The accident involved loss of control after a stall.",
                )
            ],
            query=query,
            total_matches=1,
        )


class FakeGeneratorClient:
    class responses:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "answer": "The manual evidence describes stall recovery and the NTSB case involved loss of control after a stall [DOC-001] [NTSB-001].",
                        "evidence_ids": ["DOC-001", "NTSB-001"],
                        "abstained": False,
                        "limitations": [],
                    }
                )
            )


def test_agent_graph_runs_both_sources_without_external_api(monkeypatch):
    pytest.importorskip("langgraph")
    monkeypatch.setattr("rag.guardrails.RAG_SECURITY", False)
    deps = AgentDependencies(
        document_repository=FakeDocumentRepository(),
        accident_repository=FakeAccidentRepository(),
        planner_client=FakePlannerClient(),
        generator_client=FakeGeneratorClient(),
    )
    service = AviationAgentService(deps)

    result = asyncio.run(service.arun("What does the manual say about stall recovery and what accidents involved stalls?"))

    assert result.route.sources == ["documents", "accidents"]
    assert [call.tool_name for call in result.tool_calls] == [
        "search_embedded_documents",
        "search_accident_index",
    ]
    assert result.evidence_used == ["DOC-001", "NTSB-001"]
    assert "stall recovery" in result.answer


def test_agent_graph_abstains_without_calling_tools(monkeypatch):
    pytest.importorskip("langgraph")
    monkeypatch.setattr("rag.guardrails.RAG_SECURITY", False)
    deps = AgentDependencies(
        document_repository=FakeDocumentRepository(),
        accident_repository=FakeAccidentRepository(),
        planner_client=FakePlannerClient(),
        generator_client=FakeGeneratorClient(),
    )
    service = AviationAgentService(deps)

    result = asyncio.run(service.arun("How do I cook pasta?"))

    assert result.route.route == "abstain"
    assert result.route.sources == []
    assert result.tool_calls == []
    assert result.abstained is True
