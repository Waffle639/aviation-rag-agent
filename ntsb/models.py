"""Small, tolerant domain models for the NTSB public API."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass
class NTSBSearchQuery:
    """Validated filters understood by the NTSB search service."""

    intent: str = "search"
    ntsb_number: str | None = None
    mkey: int | None = None
    registration: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    make: str | None = None
    model: str | None = None
    location: str | None = None
    state: str | None = None
    country: str | None = None
    severity: str | None = None
    event_type: str | None = None
    investigation_status: str | None = None
    text: str | None = None
    sort: str = "date_desc"
    limit: int = 10

    def __post_init__(self) -> None:
        self.intent = self.intent if self.intent in {"search", "detail", "count"} else "search"
        self.sort = self.sort if self.sort in {"date_asc", "date_desc"} else "date_desc"
        self.limit = max(1, min(int(self.limit or 10), 100))
        for name in ("start_date", "end_date"):
            value = getattr(self, name)
            if value:
                try:
                    setattr(self, name, date.fromisoformat(value).isoformat())
                except ValueError as exc:
                    raise ValueError(f"{name} must use YYYY-MM-DD format") from exc
        if self.mkey is not None:
            self.mkey = int(self.mkey)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NTSBCase:
    """Normalized case. ``raw`` keeps fields not yet known by the API contract."""

    ntsb_number: str | None = None
    mkey: int | str | None = None
    event_date: str | None = None
    make: str | None = None
    model: str | None = None
    registration: str | None = None
    location: str | None = None
    state: str | None = None
    country: str | None = None
    event_type: str | None = None
    severity: str | None = None
    investigation_status: str | None = None
    fatalities: int | float | None = None
    injuries: int | float | None = None
    narrative: str | None = None
    probable_cause: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def aircraft(self) -> str:
        return " ".join(part for part in (self.make, self.model) if part).strip()

    @property
    def identifier(self) -> str:
        return str(self.ntsb_number or self.mkey or "unknown")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["aircraft"] = self.aircraft
        result["identifier"] = self.identifier
        return result

    def to_context(self) -> str:
        fields = [
            ("Caso NTSB", self.ntsb_number or self.mkey),
            ("Fecha", self.event_date),
            ("Aeronave", self.aircraft or None),
            ("Matrícula", self.registration),
            ("Lugar", self.location),
            ("Estado", self.state),
            ("País", self.country),
            ("Tipo de evento", self.event_type),
            ("Gravedad", self.severity),
            ("Fallecidos", self.fatalities),
            ("Heridos", self.injuries),
            ("Estado de investigación", self.investigation_status),
            ("Narrativa", self.narrative),
            ("Causa probable", self.probable_cause),
        ]
        body = "\n".join(f"{label}: {value}" for label, value in fields if value not in (None, ""))
        return f"[Fuente: NTSB | Caso: {self.identifier}]\n{body}"


@dataclass
class NTSBSearchResult:
    cases: list[NTSBCase] = field(default_factory=list)
    query: NTSBSearchQuery = field(default_factory=NTSBSearchQuery)
    pages_examined: int = 0
    records_examined: int = 0
    matches_found: int = 0
    truncated: bool = False
    covered_start: str | None = None
    covered_end: str | None = None
    warnings: list[str] = field(default_factory=list)
    fetched_at: str | None = None

    def context_items(self) -> list[dict[str, Any]]:
        items = [
            {
                "texto": case.to_context(),
                "aircraft": case.aircraft,
                "font": f"NTSB:{case.identifier}",
                "ntsb_number": case.ntsb_number,
                "mkey": case.mkey,
                "event_date": case.event_date,
                "source": "NTSB",
            }
            for case in self.cases
        ]
        if self.query.intent == "count":
            items.insert(
                0,
                {
                    "texto": (
                        f"NTSB search metadata: {self.matches_found} matching aviation cases "
                        f"were found in the examined result set."
                    ),
                    "aircraft": "",
                    "font": "NTSB search metadata",
                    "source": "NTSB",
                },
            )
        return items

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["cases"] = [case.to_dict() for case in self.cases]
        result["query"] = self.query.to_dict()
        return result
