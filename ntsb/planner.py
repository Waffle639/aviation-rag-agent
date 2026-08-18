"""Turn a natural-language question into a bounded NTSB search query."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from ntsb.models import NTSBSearchQuery

QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["search", "detail", "count"]},
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
        "sort": {"type": "string", "enum": ["date_asc", "date_desc"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "required": [
        "intent", "ntsb_number", "mkey", "registration", "start_date", "end_date",
        "make", "model", "location", "state", "country", "severity", "event_type",
        "investigation_status", "text", "sort", "limit",
    ],
    "additionalProperties": False,
}

PLANNER_INSTRUCTIONS = """You extract structured filters for an aviation accident search in the NTSB API.
Return only the supplied JSON schema. Never create URLs, headers, SQL, or unsupported API parameters.
Use null for unknown filters. Resolve explicit dates to ISO YYYY-MM-DD when possible.
Use intent=detail only when the user identifies one NTSB number or mkey.
Use intent=count when the user explicitly asks how many; otherwise use search.
Use text only for descriptive terms such as an engine failure or runway excursion.
The current date is supplied by the application when needed; do not invent dates.
"""


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
    return NTSBSearchQuery(**parsed)
