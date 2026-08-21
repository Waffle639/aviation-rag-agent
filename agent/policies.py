"""Deterministic policy checks for controlled tool usage."""

from __future__ import annotations

import re

from agent.schemas import DetailRequest, EvidenceItem


_DETAIL_TERMS = (
    "cause", "probable cause", "finding", "findings", "narrative", "summary", "detail",
    "details", "full", "complete", "why", "causa", "causas", "hallazgos", "narrativa",
    "resumen", "detalle", "detalles", "completo", "por qué", "porque",
)
_COUNT_OR_RANK_TERMS = (
    "how many", "count", "most", "least", "highest", "lowest", "ranking", "rank",
    "cuántos", "cuantos", "conteo", "más", "mas", "menos", "ranking", "mayor", "menor",
)


def question_requests_detail(question: str) -> bool:
    text = question.casefold()
    return any(term in text for term in _DETAIL_TERMS)


def question_requests_count_or_rank(question: str) -> bool:
    text = question.casefold()
    return any(term in text for term in _COUNT_OR_RANK_TERMS)


def _missing_detail(evidence: EvidenceItem) -> bool:
    text = evidence.text.casefold()
    detail_markers = ("probable cause:", "findings:", "events:", "narrative:")
    if not any(marker in text for marker in detail_markers):
        return True
    missing_markers = (
        "probable cause: none",
        "probable cause: unknown",
        "probable cause: not published",
        "narrative: none",
    )
    return any(marker in text for marker in missing_markers)


def select_ntsb_detail_requests(
    question: str,
    accident_evidence: list[EvidenceItem],
    *,
    max_requests: int = 3,
) -> list[DetailRequest]:
    """Allow live NTSB detail only for selected concrete cases, never broad scans."""
    if not question_requests_detail(question) or question_requests_count_or_rank(question):
        return []

    requests: list[DetailRequest] = []
    seen: set[str] = set()
    for item in accident_evidence:
        ntsb_number = item.metadata.get("ntsb_number")
        mkey = item.metadata.get("mkey")
        identifier = str(ntsb_number or mkey or item.source_record_id or "")
        if not identifier or identifier in seen:
            continue
        if not _missing_detail(item) and not re.search(r"\b[A-Z]{3}\d{2}[A-Z]{2}\d{3}\b", identifier, re.IGNORECASE):
            continue
        try:
            requests.append(
                DetailRequest(
                    ntsb_number=str(ntsb_number) if ntsb_number else None,
                    mkey=int(mkey) if mkey not in (None, "") else None,
                )
            )
        except (TypeError, ValueError):
            continue
        seen.add(identifier)
        if len(requests) >= max_requests:
            break
    return requests
