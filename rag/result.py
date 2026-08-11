"""Structured output for one RAG execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil
from typing import Any


def estimate_tokens(text: str) -> int:
    """Estimate tokens without adding a tokenizer dependency to production."""
    if not text:
        return 0
    return ceil(len(text) / 4)


@dataclass(frozen=True)
class Citation:
    citation_id: str
    aircraft: str
    source: str
    parent_id: str | None
    chunk_id: str | None
    quote: str


@dataclass
class RAGResult:
    question: str
    answer: str
    retrieved_items: list[dict[str, Any]] = field(default_factory=list)
    context_items: list[dict[str, Any]] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    abstained: bool = False
    timings_ms: dict[str, float] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["citations"] = [asdict(citation) for citation in self.citations]
        return result
