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
        max_output_tokens=int(os.getenv("RAG_AGENT_MAX_OUTPUT_TOKENS", os.getenv("RAG_MAX_OUTPUT_TOKENS", "2000"))),
        max_input_tokens=int(os.getenv("RAG_AGENT_MAX_INPUT_TOKENS", "24000")),
        max_evidence_tokens=int(os.getenv("RAG_AGENT_MAX_EVIDENCE_TOKENS", "16000")),
        max_memory_tokens=int(os.getenv("RAG_AGENT_MAX_MEMORY_TOKENS", "1500")),
        context_safety_margin_tokens=int(os.getenv("RAG_AGENT_CONTEXT_SAFETY_MARGIN_TOKENS", "1000")),
        memory_compaction_trigger_tokens=int(os.getenv("RAG_AGENT_MEMORY_COMPACTION_TRIGGER_TOKENS", "3000")),
        memory_keep_recent_messages=int(os.getenv("RAG_AGENT_MEMORY_KEEP_RECENT_MESSAGES", "4")),
        max_summary_tokens=int(os.getenv("RAG_AGENT_MAX_SUMMARY_TOKENS", "600")),
    )


class AviationAgentService:
    def __init__(self, deps: AgentDependencies | None = None):
        self.deps = deps or build_default_dependencies()
        self.graph = build_graph(self.deps)

    async def arun(self, question: str, *, session_id: str | None = None) -> AgentResult:
        conversation_context = None
        if session_id is not None:
            if self.deps.memory_store is None:
                raise RuntimeError("session_id was provided but no conversation memory store is configured.")
            context = self.deps.memory_store.load_context(
                session_id,
                recent_token_budget=self.deps.max_memory_tokens,
            )
            conversation_context = context.format_for_prompt(max_tokens=self.deps.max_memory_tokens)

        initial = AgentState(
            question=question,
            original_question=question,
            session_id=session_id,
            conversation_context=conversation_context,
        )
        raw = await self.graph.ainvoke(initial.model_dump())
        state = AgentState.model_validate(raw)
        answer = state.final_answer.answer if state.final_answer else "I don't have that information in my sources."
        if session_id is not None and self.deps.memory_store is not None:
            self.deps.memory_store.append_message(session_id, role="user", content=state.original_question or question)
            self.deps.memory_store.append_message(
                session_id,
                role="assistant",
                content=answer,
                metadata={
                    "evidence_ids": state.final_answer.evidence_ids if state.final_answer else [],
                    "abstained": state.final_answer.abstained if state.final_answer else True,
                    "standalone_question": state.standalone_question,
                },
            )
            self.deps.memory_store.compact_if_needed(
                session_id,
                generator_client=self.deps.generator_client,
                model_name=self.deps.model_name,
                trigger_tokens=self.deps.memory_compaction_trigger_tokens,
                keep_recent_messages=self.deps.memory_keep_recent_messages,
                max_summary_tokens=self.deps.max_summary_tokens,
            )
        return AgentResult(
            question=state.original_question or state.question,
            session_id=session_id,
            standalone_question=state.standalone_question,
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
