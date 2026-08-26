"""LangGraph workflow for the controlled aviation agent."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Literal
from typing_extensions import TypedDict

from agent.dependencies import AgentDependencies
from agent.policies import select_ntsb_detail_requests
from agent.router import RouterService
from agent.schemas import AgentState, FallbackRecord, GroundedAnswer, ToolCallRecord
from agent.synthesis import synthesize_answer, validate_grounded_answer
from agent.tools import AgentTools


class GraphState(TypedDict, total=False):
    question: str
    original_question: str | None
    session_id: str | None
    conversation_context: str | None
    standalone_question: str | None
    route: dict[str, Any] | None
    document_evidence: list[dict[str, Any]]
    accident_evidence: list[dict[str, Any]]
    api_evidence: list[dict[str, Any]]
    detail_requests: list[dict[str, Any]]
    tool_calls: list[dict[str, Any]]
    fallbacks: list[dict[str, Any]]
    warnings: list[str]
    final_answer: dict[str, Any] | None


def _state(raw: dict[str, Any]) -> AgentState:
    return AgentState.model_validate(raw)


def _dump(state: AgentState) -> dict[str, Any]:
    return state.model_dump()


async def _run_tool(name: str, coroutine) -> tuple[Any | None, ToolCallRecord]:
    started = time.perf_counter()
    try:
        result = await coroutine
        return result, ToolCallRecord(
            tool_name=name,
            status="success",
            latency_ms=result.latency_ms or (time.perf_counter() - started) * 1000,
            evidence_count=len(result.evidence),
            total_matches=result.total_matches,
        )
    except Exception as exc:
        return None, ToolCallRecord(
            tool_name=name,
            status="error",
            latency_ms=(time.perf_counter() - started) * 1000,
            error=f"{exc.__class__.__name__}: {exc}",
        )


def build_graph(deps: AgentDependencies):
    from langgraph.graph import END, START, StateGraph

    router = RouterService(deps.router_model)
    tools = AgentTools(deps)
    builder = StateGraph(GraphState)

    async def validate_input(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        from rag.guardrails import RAG_SECURITY, _run_detector, moderate, validate_question

        cleaned = validate_question(state.question)
        if RAG_SECURITY:
            _run_detector(cleaned)
            moderate(cleaned, label="question")
        state.question = cleaned
        state.original_question = state.original_question or cleaned
        return _dump(state)

    async def route_question(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        decision, fallbacks = await router.route(
            state.question,
            conversation_context=state.conversation_context,
        )
        state.route = decision
        state.standalone_question = decision.standalone_question or state.question
        state.fallbacks.extend(fallbacks)
        return _dump(state)

    def after_route(raw: dict[str, Any]) -> Literal["search_sources", "finish_abstain"]:
        route = _state(raw).route
        return "finish_abstain" if route is None or route.route == "abstain" else "search_sources"

    async def finish_abstain(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        state.final_answer = GroundedAnswer(
            answer="I don't have that information in my sources.",
            evidence_ids=[],
            abstained=True,
            limitations=["The question is outside the supported aviation sources."],
        )
        return _dump(state)

    async def search_sources(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        assert state.route is not None
        tasks = []
        if "documents" in state.route.sources:
            tasks.append((
                "search_embedded_documents",
                tools.search_embedded_documents(
                    state.route.document_query or state.standalone_question or state.question,
                    top_k=deps.max_document_results,
                ),
            ))
        if "accidents" in state.route.sources:
            tasks.append((
                "search_accident_index",
                tools.search_accident_index(state.route.accident_question or state.standalone_question or state.question),
            ))

        results = await asyncio.gather(*[_run_tool(name, task) for name, task in tasks])
        for result, call in results:
            state.tool_calls.append(call)
            if result is None:
                state.fallbacks.append(
                    FallbackRecord(
                        stage=call.tool_name,
                        cause=call.error or "tool_error",
                        action="continue_with_available_evidence",
                        result="partial" if state.all_evidence else "no_evidence_yet",
                    )
                )
                continue
            state.warnings.extend(result.warnings)
            if result.tool_name == "search_embedded_documents":
                state.document_evidence.extend(result.evidence)
            elif result.tool_name == "search_accident_index":
                state.accident_evidence.extend(result.evidence)
                if result.stale:
                    state.warnings.append("The local NTSB index may be stale.")
        return _dump(state)

    async def assess_detail_policy(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        state.detail_requests = select_ntsb_detail_requests(
            state.standalone_question or state.question,
            state.accident_evidence,
            max_requests=deps.max_ntsb_detail_calls,
        )
        return _dump(state)

    def after_detail_policy(raw: dict[str, Any]) -> Literal["fetch_ntsb_detail", "synthesize"]:
        return "fetch_ntsb_detail" if _state(raw).detail_requests else "synthesize"

    async def fetch_ntsb_detail(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        if not state.detail_requests:
            return _dump(state)
        calls = []
        for request in state.detail_requests[: deps.max_ntsb_detail_calls]:
            calls.append((
                "fetch_ntsb_case_detail",
                tools.fetch_ntsb_case_detail(ntsb_number=request.ntsb_number, mkey=request.mkey),
            ))
        results = await asyncio.gather(*[_run_tool(name, task) for name, task in calls])
        for result, call in results:
            state.tool_calls.append(call)
            if result is None:
                state.fallbacks.append(
                    FallbackRecord(
                        stage="fetch_ntsb_detail",
                        cause=call.error or "api_error",
                        action="use_local_ntsb_evidence",
                        result="partial",
                    )
                )
                continue
            state.api_evidence.extend(result.evidence)
            state.warnings.extend(result.warnings)
        return _dump(state)

    async def synthesize(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        answer = await synthesize_answer(
            deps.generator_client,
            model_name=deps.model_name,
            question=state.standalone_question or state.question,
            evidence=state.all_evidence,
            warnings=state.warnings,
            conversation_context=state.conversation_context,
            max_input_tokens=deps.max_input_tokens,
            max_evidence_tokens=deps.max_evidence_tokens,
            max_output_tokens=deps.max_output_tokens,
            safety_margin_tokens=deps.context_safety_margin_tokens,
        )
        state.final_answer = answer
        return _dump(state)

    async def validate_answer(raw: dict[str, Any]) -> dict[str, Any]:
        state = _state(raw)
        if state.final_answer is not None:
            answer, fallbacks = validate_grounded_answer(state.final_answer, state.all_evidence)
            state.final_answer = answer
            state.fallbacks.extend(fallbacks)
            if answer.answer:
                from rag.guardrails import RAG_SECURITY, check_output, moderate

                if RAG_SECURITY:
                    check_output(answer.answer)
                    moderate(answer.answer, label="answer")
        return _dump(state)

    builder.add_node("validate_input", validate_input)
    builder.add_node("route_question", route_question)
    builder.add_node("finish_abstain", finish_abstain)
    builder.add_node("search_sources", search_sources)
    builder.add_node("assess_detail_policy", assess_detail_policy)
    builder.add_node("fetch_ntsb_detail", fetch_ntsb_detail)
    builder.add_node("synthesize", synthesize)
    builder.add_node("validate_answer", validate_answer)

    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "route_question")
    builder.add_conditional_edges(
        "route_question",
        after_route,
        {"search_sources": "search_sources", "finish_abstain": "finish_abstain"},
    )
    builder.add_edge("finish_abstain", END)
    builder.add_edge("search_sources", "assess_detail_policy")
    builder.add_conditional_edges(
        "assess_detail_policy",
        after_detail_policy,
        {"fetch_ntsb_detail": "fetch_ntsb_detail", "synthesize": "synthesize"},
    )
    builder.add_edge("fetch_ntsb_detail", "synthesize")
    builder.add_edge("synthesize", "validate_answer")
    builder.add_edge("validate_answer", END)
    return builder.compile()
