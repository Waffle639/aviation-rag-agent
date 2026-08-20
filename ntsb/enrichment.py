"""Targeted NTSB detail enrichment for already selected cases."""

from __future__ import annotations

import asyncio
from dataclasses import fields, replace
import os

from ntsb.domain import NTSBCase, NTSBSearchQuery
from ntsb.context import detail_payload_to_context
from ntsb.sync.errors import NTSBError
from ntsb.sync.service import NTSBSyncService


_DETAIL_FIELDS = {"probable_cause", "findings", "events", "narrative", "airport", "runway", "weather", "itinerary"}


def requires_selected_detail_refresh(case: NTSBCase, query: NTSBSearchQuery) -> bool:
    if query.needs_detail:
        return True
    if case.detail_fetched_at:
        return False
    requested = set(query.requested_fields or [])
    if not requested.intersection(_DETAIL_FIELDS):
        return False
    return any(
        (
            "probable_cause" in requested and not case.probable_cause,
            "narrative" in requested and not case.narrative,
            "events" in requested and not case.events,
            "findings" in requested and not case.findings,
            "airport" in requested and not case.airport,
            "runway" in requested and not case.runway,
            "weather" in requested,
            "itinerary" in requested,
        )
    )


def enrich_selected_cases(cases: list[NTSBCase], query: NTSBSearchQuery) -> tuple[list[NTSBCase], list[str]]:
    if not os.getenv("NTSB_API_KEY"):
        return cases, ["NTSB_API_KEY is not configured; selected case detail enrichment was skipped."]
    targets = [case for case in cases if requires_selected_detail_refresh(case, query)]
    if not targets:
        return cases, []
    try:
        enriched_by_mkey = asyncio.run(_fetch_details(targets))
    except NTSBError as exc:
        return cases, [f"NTSB detail enrichment failed: {exc}"]
    enriched = [_merge_case(case, enriched_by_mkey.get(case.mkey)) for case in cases]
    return enriched, []


def _merge_case(original: NTSBCase, detail: NTSBCase | None) -> NTSBCase:
    if detail is None:
        return original
    values = {}
    for field in fields(NTSBCase):
        original_value = getattr(original, field.name)
        detail_value = getattr(detail, field.name)
        if isinstance(original_value, list):
            values[field.name] = detail_value or original_value
        else:
            values[field.name] = detail_value if detail_value not in (None, "") else original_value
    return replace(original, **values)


async def _fetch_details(cases: list[NTSBCase]) -> dict[int | None, NTSBCase]:
    service = NTSBSyncService()
    results: dict[int | None, NTSBCase] = {}
    async with service.api_client.async_session() as session:
        for case in cases:
            normalized = await service.sync_case_detail(
                ntsb_number=case.ntsb_number,
                mkey=case.mkey,
                session=session,
            )
            if normalized is not None:
                normalized.case.detail_context = detail_payload_to_context(normalized.raw)
                results[normalized.case.mkey] = normalized.case
    return results
