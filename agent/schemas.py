"""Typed contracts shared by the aviation agent nodes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


RouteName = Literal["documents", "accidents", "both", "abstain"]
EvidenceKind = Literal["embedded_document", "ntsb_index", "ntsb_api"]


class RouteDecision(BaseModel):
    """Router output. It only chooses which retrieval path to run."""

    route: RouteName
    document_query: str | None = None
    accident_question: str | None = None
    reason: str

    @property
    def sources(self) -> list[str]:
        if self.route == "both":
            return ["documents", "accidents"]
        if self.route == "abstain":
            return []
        return [self.route]

    @model_validator(mode="after")
    def validate_route(self) -> "RouteDecision":
        if self.route in {"documents", "both"} and not self.document_query:
            raise ValueError("document_query is required for documents routes")
        if self.route in {"accidents", "both"} and not self.accident_question:
            raise ValueError("accident_question is required for accidents routes")
        return self


class EvidenceItem(BaseModel):
    evidence_id: str
    source_kind: EvidenceKind
    source_name: str
    source_record_id: str | None = None
    text: str
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    total_matches: int | None = None
    stale: bool = False
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = 0.0


class ToolCallRecord(BaseModel):
    tool_name: str
    status: Literal["success", "error", "skipped"]
    latency_ms: float = 0.0
    evidence_count: int = 0
    total_matches: int | None = None
    error: str | None = None


class FallbackRecord(BaseModel):
    stage: str
    cause: str
    action: str
    result: str | None = None


class DetailRequest(BaseModel):
    ntsb_number: str | None = None
    mkey: int | None = None

    @model_validator(mode="after")
    def validate_identifier(self) -> "DetailRequest":
        if not self.ntsb_number and self.mkey is None:
            raise ValueError("ntsb_number or mkey is required")
        return self


class GroundedAnswer(BaseModel):
    answer: str
    evidence_ids: list[str] = Field(default_factory=list)
    abstained: bool = False
    limitations: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    question: str
    route: RouteDecision | None = None
    answer: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    fallbacks: list[FallbackRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    abstained: bool = False


class AgentState(BaseModel):
    question: str
    route: RouteDecision | None = None
    document_evidence: list[EvidenceItem] = Field(default_factory=list)
    accident_evidence: list[EvidenceItem] = Field(default_factory=list)
    api_evidence: list[EvidenceItem] = Field(default_factory=list)
    detail_requests: list[DetailRequest] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    fallbacks: list[FallbackRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    final_answer: GroundedAnswer | None = None

    @property
    def all_evidence(self) -> list[EvidenceItem]:
        return [*self.document_evidence, *self.accident_evidence, *self.api_evidence]
