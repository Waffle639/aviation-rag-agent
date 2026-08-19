"""Turn a natural-language question into a bounded NTSB search query."""

from __future__ import annotations

import json
from html import escape
import re
from datetime import date
from typing import Any

from ntsb.models import NTSBSearchQuery

QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["search", "detail", "count"]},
        "goal": {
            "type": "string",
            "enum": ["lookup", "search", "count", "rank", "compare", "explain"],
        },
        "ntsb_number": {"type": ["string", "null"]},
        "mkey": {"type": ["integer", "null"]},
        "registration": {"type": ["string", "null"]},
        "start_date": {"type": ["string", "null"]},
        "end_date": {"type": ["string", "null"]},
        "make": {"type": ["string", "null"]},
        "model": {"type": ["string", "null"]},
        "location": {"type": ["string", "null"]},
        "state": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "severity": {"type": ["string", "null"]},
        "event_type": {"type": ["string", "null"]},
        "investigation_status": {"type": ["string", "null"]},
        "text": {"type": ["string", "null"]},
        "needs_detail": {"type": "boolean"},
        "sort": {"type": "string", "enum": ["date_asc", "date_desc"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        "ranking_field": {"type": ["string", "null"], "enum": ["fatalities", "injuries", "date", None]},
        "ranking_order": {"type": "string", "enum": ["asc", "desc"]},
        "requested_fields": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "case", "date", "aircraft", "registration", "location", "country",
                    "severity", "injuries", "fatalities", "narrative", "probable_cause",
                    "findings", "events", "airport", "runway", "weather", "itinerary",
                ],
            },
        },
        "requires_full_scan": {"type": "boolean"},
    },
    "required": [
        "intent", "goal", "ntsb_number", "mkey", "registration", "start_date", "end_date",
        "make", "model", "location", "state", "country", "severity", "event_type",
        "investigation_status", "text", "needs_detail", "sort", "limit", "ranking_field",
        "ranking_order", "requested_fields", "requires_full_scan",
    ],
    "additionalProperties": False,
}

PLANNER_INSTRUCTIONS = """You extract structured filters for an aviation accident search in the NTSB API.
Return only the supplied JSON schema. Never create URLs, headers, SQL, or unsupported API parameters.
Use null for unknown filters. Resolve explicit dates to ISO YYYY-MM-DD when possible.
Use intent=detail only when the user identifies one NTSB number or mkey.
Use intent=count when the user explicitly asks how many; otherwise use search.
Use goal=lookup for one identified case, goal=search for listing cases, goal=count for totals,
goal=rank when the user asks for the most/least fatal, injured, recent or old case, goal=compare
for comparing cases, and goal=explain when the user asks for causes, clues or evidence.
For "most deaths", use goal=rank, ranking_field=fatalities, ranking_order=desc,
requires_full_scan=true, and do not use date_desc as a substitute for the ranking.
Interpret phrases such as "past 10 years" as an explicit start_date and end_date interval.
Use text only for descriptive terms such as an engine failure or runway excursion.
When a country is specified, prefer its ISO 3166-1 alpha-2 code (for example, US or ES)
instead of a translated or long country name.
Set needs_detail=true when answering requires a narrative, probable cause, detailed injuries,
or another case-specific field that may not be present in the date-range summary. Set it to false
for counts and questions answerable with summary fields such as dates, aircraft, location,
state, country or case identifiers.
requested_fields must contain the information the final answer must show. For causes, clues or
evidence include probable_cause, findings, events and narrative as appropriate. For airport
questions include airport and runway.
The current date is supplied by the application when needed; do not invent dates.
"""


def _repair_query_from_question(question: str, parsed: dict[str, Any]) -> dict[str, Any]:
    """Repair high-confidence intent that must not be lost by the LLM planner."""
    text = question.casefold()
    fatality_rank = re.search(
        r"(?:most|more|highest|greatest|max(?:imum)?|largest|más|mayor|máximo).{0,40}"
        r"(?:death|fatal|victim|casualt|muert|fallecid|víctim)",
        text,
    )
    if fatality_rank:
        requested = set(parsed.get("requested_fields") or [])
        requested.update({"case", "date", "aircraft", "location", "fatalities", "probable_cause", "findings", "events", "narrative"})
        parsed.update(
            {
                "goal": "rank",
                "ranking_field": "fatalities",
                "ranking_order": "desc",
                "requires_full_scan": True,
                "needs_detail": True,
                "requested_fields": sorted(requested),
                "limit": 1,
            }
        )

    years_match = re.search(
        r"(?:past|last|últimos|ultimos|últimas|ultimas)\s+(\d+)\s+(?:years?|años)",
        text,
    )
    if "last decade" in text or "última década" in text or "ultima decada" in text:
        years = 10
    else:
        years = int(years_match.group(1)) if years_match else None
    if years:
        end = date.today()
        try:
            start = end.replace(year=end.year - years)
        except ValueError:
            start = end.replace(year=end.year - years, day=28)
        parsed["start_date"] = start.isoformat()
        parsed["end_date"] = end.isoformat()

    ntsb_match = re.search(r"\b[A-Z]{3}\d{2}[A-Z]{2}\d{3}\b", question.upper())
    if ntsb_match:
        parsed.update({"intent": "detail", "goal": "lookup", "ntsb_number": ntsb_match.group(0)})

    mkey_match = re.search(r"\bmkey\s*[:#]?\s*(\d+)\b", text)
    if mkey_match:
        parsed.update({"intent": "detail", "goal": "lookup", "mkey": int(mkey_match.group(1))})
    return parsed


def plan_query(openai_client: Any, question: str, model: str) -> NTSBSearchQuery:
    response = openai_client.responses.create(
        model=model,
        instructions=PLANNER_INSTRUCTIONS,
        input=f"<question>{escape(question)}</question>",
        text={
            "format": {
                "type": "json_schema",
                "name": "ntsb_search_query",
                "strict": True,
                "schema": QUERY_SCHEMA,
            }
        },
        max_output_tokens=800,
    )
    try:
        parsed = json.loads(response.output_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("The NTSB query planner returned invalid JSON.") from exc
    return NTSBSearchQuery(**_repair_query_from_question(question, parsed))
