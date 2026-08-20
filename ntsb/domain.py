"""Domain types for the indexed NTSB read model."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class NTSBSearchQuery:
    """Validated filters understood by the PostgreSQL NTSB repository."""

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
    needs_detail: bool = False
    sort: str = "date_desc"
    limit: int = 10
    goal: str = "search"
    ranking_field: str | None = None
    ranking_order: str = "desc"
    requested_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.intent = self.intent if self.intent in {"search", "detail", "count"} else "search"
        self.sort = self.sort if self.sort in {"date_asc", "date_desc"} else "date_desc"
        self.limit = max(1, min(int(self.limit or 10), 100))
        valid_goals = {"lookup", "search", "count", "rank", "compare", "explain"}
        if self.goal == "search" and self.ranking_field:
            self.goal = "rank"
        elif self.goal == "search" and self.intent == "count":
            self.goal = "count"
        if self.goal not in valid_goals:
            self.goal = (
                "rank" if self.ranking_field
                else "lookup" if self.intent == "detail" or self.ntsb_number or self.mkey is not None
                else "count" if self.intent == "count"
                else "search"
            )
        valid_ranking_fields = {"fatalities", "injuries", "date"}
        if self.ranking_field not in valid_ranking_fields:
            self.ranking_field = None
        if self.ranking_order not in {"asc", "desc"}:
            self.ranking_order = "desc"
        self.requested_fields = [str(value) for value in (self.requested_fields or [])]
        for name in ("start_date", "end_date"):
            value = getattr(self, name)
            if value:
                try:
                    setattr(self, name, date.fromisoformat(str(value)).isoformat())
                except ValueError as exc:
                    raise ValueError(f"{name} must use YYYY-MM-DD format") from exc
        if self.mkey is not None:
            self.mkey = int(self.mkey)
        self.needs_detail = bool(self.needs_detail)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NTSBAircraft:
    aircraft_sequence: int = 1
    make: str | None = None
    model: str | None = None
    registration: str | None = None
    category: str | None = None
    operation: str | None = None
    damage: str | None = None


@dataclass
class NTSBCase:
    """One case from the local NTSB index."""

    ntsb_number: str | None = None
    mkey: int | None = None
    event_date: str | None = None
    event_time: str | None = None
    city: str | None = None
    location: str | None = None
    state: str | None = None
    country: str | None = None
    country_code: str | None = None
    event_type: str | None = None
    severity: str | None = None
    investigation_status: str | None = None
    fatalities: int | None = None
    serious_injuries: int | None = None
    minor_injuries: int | None = None
    total_injuries: int | None = None
    narrative: str | None = None
    probable_cause: str | None = None
    airport: str | None = None
    runway: str | None = None
    source_updated_at: str | None = None
    synced_at: str | None = None
    detail_fetched_at: str | None = None
    detail_context: str | None = None
    aircraft_list: list[NTSBAircraft] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    @property
    def primary_aircraft(self) -> NTSBAircraft | None:
        return self.aircraft_list[0] if self.aircraft_list else None

    @property
    def make(self) -> str | None:
        return self.primary_aircraft.make if self.primary_aircraft else None

    @property
    def model(self) -> str | None:
        return self.primary_aircraft.model if self.primary_aircraft else None

    @property
    def registration(self) -> str | None:
        return self.primary_aircraft.registration if self.primary_aircraft else None

    @property
    def aircraft(self) -> str:
        aircraft_names = []
        for aircraft in self.aircraft_list:
            name = " ".join(part for part in (aircraft.make, aircraft.model) if part).strip()
            if name and name not in aircraft_names:
                aircraft_names.append(name)
        return "; ".join(aircraft_names)

    @property
    def identifier(self) -> str:
        return str(self.ntsb_number or self.mkey or "unknown")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["aircraft"] = self.aircraft
        result["make"] = self.make
        result["model"] = self.model
        result["registration"] = self.registration
        result["identifier"] = self.identifier
        return result


@dataclass
class NTSBSearchResult:
    cases: list[NTSBCase] = field(default_factory=list)
    query: NTSBSearchQuery = field(default_factory=NTSBSearchQuery)
    total_matches: int = 0
    limit: int = 10
    offset: int = 0
    snapshot_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_synced_at: str | None = None
    stale: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def matches_found(self) -> int:
        return self.total_matches

    @property
    def truncated(self) -> bool:
        if self.query.goal in {"rank", "compare"}:
            return False
        return self.total_matches > self.offset + len(self.cases)

    def context_items(self) -> list[dict[str, Any]]:
        from ntsb.context import context_items_from_result

        return context_items_from_result(self)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["cases"] = [case.to_dict() for case in self.cases]
        result["query"] = self.query.to_dict()
        result["truncated"] = self.truncated
        result["matches_found"] = self.matches_found
        return result
