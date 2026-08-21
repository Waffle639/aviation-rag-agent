"""Public service API for running the aviation agent."""

from __future__ import annotations

from agent.dependencies import AgentDependencies
from agent.graph import build_graph
from agent.schemas import AgentResult, AgentState


def build_default_dependencies() -> AgentDependencies:
    from dotenv import load_dotenv
    from langchain_openai import ChatOpenAI
    from langsmith.wrappers import wrap_openai
    from openai import OpenAI
    import os

    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is required to run the aviation agent.")
    model_name = os.getenv("RAG_AGENT_MODEL", "gpt-5.4-mini")
    router_model = ChatOpenAI(model=model_name, temperature=0)
    openai_client = wrap_openai(OpenAI(api_key=api_key))
    return AgentDependencies(
        router_model=router_model,
        generator_client=openai_client,
        planner_client=openai_client,
        model_name=model_name,
    )


class AviationAgentService:
    def __init__(self, deps: AgentDependencies | None = None):
        self.deps = deps or build_default_dependencies()
        self.graph = build_graph(self.deps)

    async def arun(self, question: str) -> AgentResult:
        initial = AgentState(question=question)
        raw = await self.graph.ainvoke(initial.model_dump())
        state = AgentState.model_validate(raw)
        answer = state.final_answer.answer if state.final_answer else "I don't have that information in my sources."
        return AgentResult(
            question=state.question,
            route=state.route,
            answer=answer,
            evidence=state.all_evidence,
            evidence_used=state.final_answer.evidence_ids if state.final_answer else [],
            tool_calls=state.tool_calls,
            fallbacks=state.fallbacks,
            warnings=state.warnings + (state.final_answer.limitations if state.final_answer else []),
            abstained=state.final_answer.abstained if state.final_answer else True,
        )

    def draw_mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()
