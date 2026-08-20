"""Context rendering for indexed NTSB cases."""

from __future__ import annotations

from typing import Any

from ntsb.domain import NTSBCase, NTSBSearchResult


_DETAIL_KEYWORDS = (
    "ntsb", "mkey", "case", "event", "accident", "incident", "date", "time",
    "city", "state", "country", "location", "aircraft", "registration", "tail",
    "make", "model", "manufacturer", "category", "operation", "operator", "owner",
    "damage", "airport", "runway", "weather", "meteorological", "visibility",
    "wind", "condition", "flight", "itinerary", "departure", "destination", "phase",
    "injury", "injuries", "fatal", "serious", "minor", "occupant", "crew",
    "passenger", "person", "narrative", "summary", "synopsis", "description",
    "prelim", "analysis", "cause", "finding", "eventtier", "cictt", "report",
    "status", "class", "investigation", "lastchange", "revision", "modified",
    "updated",
)


def _interesting_path(path: str) -> bool:
    lowered = path.replace("_", "").replace("-", "").casefold()
    return any(keyword.replace("_", "") in lowered for keyword in _DETAIL_KEYWORDS)


def _format_detail_value(value: Any) -> str | None:
    if value in (None, "") or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = " ".join(text.split())
    return text[:1200] + "..." if len(text) > 1200 else text


def detail_payload_to_context(raw: dict[str, Any], *, max_lines: int = 220) -> str:
    """Render useful public NTSB detail fields without dumping opaque API noise."""
    lines: list[str] = []

    def visit(value: Any, path: str) -> None:
        if len(lines) >= max_lines:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                next_path = f"{path}.{key}" if path else str(key)
                visit(child, next_path)
            return
        if isinstance(value, list):
            for index, child in enumerate(value, start=1):
                visit(child, f"{path}[{index}]")
            return
        formatted = _format_detail_value(value)
        if formatted and _interesting_path(path):
            lines.append(f"{path}: {formatted}")

    visit(raw, "")
    if len(lines) >= max_lines:
        lines.append("Additional official detail fields were omitted because the payload exceeded the context limit.")
    if not lines:
        return "Official NTSB live detail payload was fetched, but no renderable detail fields were found."
    return "Official NTSB live detail payload excerpts:\n" + "\n".join(lines)


def case_to_context(case: NTSBCase) -> str:
    registrations = "; ".join(
        aircraft.registration for aircraft in case.aircraft_list if aircraft.registration
    )
    fields = [
        ("NTSB case", case.ntsb_number or case.mkey),
        ("Date", case.event_date),
        ("Aircraft", case.aircraft or None),
        ("Registration", registrations or None),
        ("Location", case.location),
        ("City", case.city),
        ("State", case.state),
        ("Country", case.country_code or case.country),
        ("Event time", case.event_time),
        ("Event type", case.event_type),
        ("Severity", case.severity),
        ("Fatalities", case.fatalities),
        ("Serious injuries", case.serious_injuries),
        ("Minor injuries", case.minor_injuries),
        ("Total injuries", case.total_injuries),
        ("Investigation status", case.investigation_status),
        ("Airport", case.airport),
        ("Runway", case.runway),
        ("Narrative", case.narrative),
        ("Probable cause", case.probable_cause),
        ("Events", "; ".join(case.events) if case.events else None),
        ("Findings", "; ".join(case.findings) if case.findings else None),
        ("NTSB source updated", case.source_updated_at),
        ("Indexed at", case.synced_at),
        ("Detail fetched at", case.detail_fetched_at),
    ]
    body = "\n".join(f"{label}: {value}" for label, value in fields if value not in (None, ""))
    if case.detail_context:
        body = f"{body}\n{case.detail_context}" if body else case.detail_context
    return f"[Source: NTSB | Case: {case.identifier}]\n{body}"


def case_to_context_item(case: NTSBCase) -> dict[str, Any]:
    return {
        "texto": case_to_context(case),
        "aircraft": case.aircraft,
        "font": f"NTSB:{case.identifier}",
        "source": "NTSB",
        "ntsb_number": case.ntsb_number,
        "mkey": case.mkey,
        "event_date": case.event_date,
    }


def context_items_from_result(result: NTSBSearchResult) -> list[dict[str, Any]]:
    items = [case_to_context_item(case) for case in result.cases]
    if result.query.goal == "count" or result.query.intent == "count":
        items.insert(
            0,
            {
                "texto": (
                    f"NTSB index metadata: {result.total_matches} matching aviation cases "
                    f"were found in PostgreSQL. Last sync: {result.last_synced_at or 'unknown'}."
                ),
                "aircraft": "",
                "font": "NTSB index metadata",
                "source": "NTSB",
            },
        )
    elif result.query.goal in {"rank", "compare"}:
        items.insert(
            0,
            {
                "texto": (
                    f"NTSB index metadata: PostgreSQL selected {len(result.cases)} case(s) from "
                    f"{result.total_matches} matching aviation cases using ranking_field="
                    f"{result.query.ranking_field or 'date'} and ranking_order="
                    f"{result.query.ranking_order}. Last sync: {result.last_synced_at or 'unknown'}."
                ),
                "aircraft": "",
                "font": "NTSB index metadata",
                "source": "NTSB",
            },
        )
    return items
