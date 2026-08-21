"""Question routing for the controlled aviation agent."""

from __future__ import annotations

import re
from typing import Any

from langsmith import traceable

from agent.prompts import ROUTER_PROMPT
from agent.schemas import FallbackRecord, RouteDecision


_NTSB_NUMBER_RE = re.compile(r"\b[A-Z]{3}\d{2}[A-Z]{2}\d{3}\b", re.IGNORECASE)
_ACCIDENT_TERMS = (
    "accident", "incident", "ntsb", "fatal", "fatality", "fatalities", "injury",
    "injuries", "probable cause", "finding", "crash", "investigation", "victim",
    "muert", "fallecid", "víctim", "victim", "accidente", "incidente", "causa",
    "hallazgo", "lesion", "lesión", "investigación", "investigacion",
)
_DOCUMENT_TERMS = (
    "manual", "poh", "procedure", "limitation", "specification", "speed", "stall",
    "weight", "system", "checklist", "performance", "vso", "vne", "vfe", "vx", "vy",
    "procedimiento", "limitación", "limitacion", "especificación", "especificacion",
    "velocidad", "pérdida", "perdida", "peso", "sistema",
)
_AVIATION_TERMS = _ACCIDENT_TERMS + _DOCUMENT_TERMS + (
    "aircraft", "airplane", "aviation", "flight", "cessna", "boeing", "airbus", "piper",
    "aeronave", "avión", "avion", "aviación", "aviacion", "vuelo",
)


def deterministic_route(question: str) -> RouteDecision:
    """Cheap fallback router for high-confidence cases and model failures."""
    text = question.casefold()
    has_accident = bool(_NTSB_NUMBER_RE.search(question)) or any(term in text for term in _ACCIDENT_TERMS)
    has_documents = any(term in text for term in _DOCUMENT_TERMS)
    has_aviation = has_accident or has_documents or any(term in text for term in _AVIATION_TERMS)

    if not has_aviation:
        return RouteDecision(
            route="abstain",
            reason="The question is outside the aviation sources.",
        )

    if has_accident and has_documents:
        return RouteDecision(
            route="both",
            document_query=question,
            accident_question=question,
            reason="The question contains both technical/documentation and accident-record intent.",
        )
    if has_accident:
        return RouteDecision(
            route="accidents",
            accident_question=question,
            reason="The question asks about accident records or NTSB case details.",
        )
    return RouteDecision(
        route="documents",
        document_query=question,
        reason="Defaulting to the document path because no accident-record intent was detected.",
    )


class RouterService:
    def __init__(self, model: Any | None = None):
        self.model = model

    @traceable(run_type="chain", name="agent_router")
    async def route(self, question: str) -> tuple[RouteDecision, list[FallbackRecord]]:
        if self.model is None:
            return deterministic_route(question), [
                FallbackRecord(
                    stage="router",
                    cause="router_model_not_configured",
                    action="deterministic_route",
                    result="used",
                )
            ]

        try:
            structured = self.model.with_structured_output(RouteDecision)
            messages = [
                ("system", ROUTER_PROMPT),
                ("human", question),
            ]
            if hasattr(structured, "ainvoke"):
                return await structured.ainvoke(messages), []
            return structured.invoke(messages), []
        except Exception as exc:
            decision = deterministic_route(question)
            return decision, [
                FallbackRecord(
                    stage="router",
                    cause=exc.__class__.__name__,
                    action="deterministic_route",
                    result=decision.route,
                )
            ]
