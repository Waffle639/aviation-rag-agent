import asyncio
import json
from types import SimpleNamespace

from agent.dependencies import AgentDependencies
from agent.memory import ConversationContext, ConversationMessage, deterministic_summary
from agent.schemas import RouteDecision
from agent.service import AviationAgentService


class FakeMemoryStore:
    def __init__(self):
        self.session_id = "550e8400-e29b-41d4-a716-446655440000"
        self.appended = []
        self.compacted = False

    def create_session(self):
        return self.session_id

    def session_exists(self, session_id):
        return session_id == self.session_id

    def load_context(self, session_id, *, recent_token_budget):
        assert session_id == self.session_id
        return ConversationContext(
            session_id=session_id,
            summary={"entities": {"active_aircraft": "Cessna 172S"}},
            recent_messages=[
                ConversationMessage(
                    sequence_number=1,
                    role="user",
                    content="Estoy estudiando el Cessna 172S.",
                    token_count=9,
                )
            ],
        )

    def append_message(self, session_id, *, role, content, metadata=None):
        self.appended.append((session_id, role, content, metadata or {}))
        return len(self.appended)

    def compact_if_needed(self, session_id, **kwargs):
        self.compacted = True
        return False


class FakeRouterModel:
    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        assert "Cessna 172S" in messages[1][1]
        return RouteDecision(
            route="documents",
            standalone_question="What is the Vne of the Cessna 172S?",
            document_query="Cessna 172S Vne limitation",
            reason="The follow-up asks for a documented aircraft speed limitation.",
        )


class FakeDocumentRepository:
    def __init__(self):
        self.queries = []

    async def search(self, query, aircraft=None, top_k=5):
        self.queries.append(query)
        return [
            {
                "texto": "The Cessna 172S never-exceed speed is 163 KIAS.",
                "aircraft": "Cessna 172S",
                "font": "manual",
                "chunk_id": "c1",
                "parent_id": "p1",
                "similarity": 0.9,
            }
        ]


class FakeGeneratorClient:
    class Responses:
        def __init__(self, owner):
            self.owner = owner

        def create(self, **kwargs):
            self.owner.requests.append(kwargs)
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "answer": "The Cessna 172S Vne is 163 KIAS [DOC-001].",
                        "evidence_ids": ["DOC-001"],
                        "abstained": False,
                        "limitations": [],
                    }
                )
            )

    def __init__(self):
        self.requests = []
        self.responses = self.Responses(self)


def test_agent_uses_persistent_memory_for_follow_up(monkeypatch):
    monkeypatch.setattr("rag.guardrails.RAG_SECURITY", False)
    memory = FakeMemoryStore()
    documents = FakeDocumentRepository()
    generator = FakeGeneratorClient()
    deps = AgentDependencies(
        memory_store=memory,
        router_model=FakeRouterModel(),
        document_repository=documents,
        generator_client=generator,
        max_evidence_tokens=2000,
        max_output_tokens=500,
    )
    service = AviationAgentService(deps)

    result = asyncio.run(service.arun("¿Y su Vne?", session_id=memory.session_id))

    assert result.question == "¿Y su Vne?"
    assert result.session_id == memory.session_id
    assert result.standalone_question == "What is the Vne of the Cessna 172S?"
    assert documents.queries == ["Cessna 172S Vne limitation"]
    assert "Cessna 172S" in generator.requests[0]["input"]
    assert generator.requests[0]["max_output_tokens"] == 500
    assert [entry[1] for entry in memory.appended] == ["user", "assistant"]
    assert memory.appended[1][3]["standalone_question"] == "What is the Vne of the Cessna 172S?"
    assert memory.compacted is True


def test_context_format_respects_token_budget():
    context = ConversationContext(
        session_id="550e8400-e29b-41d4-a716-446655440000",
        summary={"objective": "x" * 200},
        recent_messages=[
            ConversationMessage(sequence_number=1, role="user", content="y" * 500, token_count=125),
        ],
    )

    formatted = context.format_for_prompt(max_tokens=40)

    assert "session_id" in formatted
    assert len(formatted) <= 40 * 4 + 20


def test_deterministic_summary_extracts_active_aircraft():
    summary = deterministic_summary(
        {},
        [ConversationMessage(sequence_number=1, role="user", content="Estoy estudiando el Cessna 172S")],
        max_summary_tokens=120,
    )

    assert summary["entities"]["active_aircraft"] == "Cessna 172S"
    assert summary["references"]["su"] == "Cessna 172S"
