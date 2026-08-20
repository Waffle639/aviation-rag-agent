"""Normalize NTSB API payloads into the local relational read model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import re
import unicodedata
from typing import Any, Iterable

try:
    import pycountry
except ImportError:  # pragma: no cover - requirements installs this package.
    pycountry = None

from ntsb.domain import NTSBAircraft, NTSBCase


_ALIASES = {
    "ntsb_number": ("ntsbNumber", "ntsb_number", "reportNumber", "caseNumber", "caseIdentifier"),
    "mkey": ("mkey", "Mkey", "id", "caseId"),
    "event_date": ("eventDate", "event_date", "accidentDate", "date", "occurrenceDate"),
    "event_time": ("eventTimeUtc", "event_time", "eventTime", "occurrenceTime"),
    "city": ("eventCity", "city"),
    "location": ("location", "accidentLocation", "eventLocation", "site", "place"),
    "state": ("state", "stateName", "eventStateOrRegion", "province"),
    "country": ("country", "countryName", "eventCountry"),
    "event_type": ("eventType", "event_type", "accidentType", "occurrenceType"),
    "severity": ("severity", "injuryLevel", "injurySeverity", "highestInjury", "highestInjuryLevel"),
    "investigation_status": ("investigationStatus", "completionStatus", "investigationClass", "status", "caseStatus"),
    "fatalities": ("fatalities", "fatalInjuries", "totalFatalities", "totalFatal", "deathCount"),
    "serious_injuries": ("seriousInjuries", "totalSerious", "seriousInjuryCount"),
    "minor_injuries": ("minorInjuries", "totalMinor", "minorInjuryCount"),
    "total_injuries": ("injuries", "totalInjuries", "injuryCount"),
    "narrative": (
        "narrative", "summary", "eventNarrative", "analysisNarrative",
        "prelimNarrative", "concatenatedFactualNarrative", "description", "synopsis",
    ),
    "probable_cause": ("probableCause", "probable_cause", "cause", "causeText"),
    "source_updated_at": ("lastChangeDateTimeUtc", "lastRevisionDate", "modifiedDate", "updatedAt"),
    "make": ("aircraftMake", "aircraft_make", "make", "manufacturer", "aircraftManufacturer"),
    "model": ("aircraftModel", "aircraft_model", "model", "aircraftType"),
    "registration": ("aircraftRegistrationNumber", "registration", "registrationNumber", "tailNumber"),
    "category": ("aircraftCategory", "category"),
    "operation": ("operation", "flightConductCode", "typeOfOperation"),
    "damage": ("aircraftDamage", "damage"),
}


@dataclass
class NormalizedCase:
    case: NTSBCase
    raw: dict[str, Any]
    payload_hash: str
    aircraft: list[NTSBAircraft] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    airports: list[dict[str, str | None]] = field(default_factory=list)


def norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def country_code(value: Any) -> str | None:
    normalized = norm(value)
    if not normalized or pycountry is None:
        return None
    try:
        country = pycountry.countries.lookup(normalized)
    except LookupError:
        return None
    return country.alpha_2.upper()


def flatten(value: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    result = result or {}
    if isinstance(value, dict):
        for key, child in value.items():
            result[norm(key)] = child
            flatten(child, result)
    elif isinstance(value, list):
        for child in value:
            flatten(child, result)
    return result


def value(flat: dict[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        item = flat.get(norm(alias))
        if item not in (None, "") and not isinstance(item, (dict, list)):
            return item
    return None


def records(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "records", "results", "data", "cases", "aviationCases", "value"):
        child = payload.get(key)
        if isinstance(child, list):
            return [item for item in child if isinstance(item, dict)]
        if isinstance(child, dict):
            nested = records(child)
            if nested:
                return nested
    flat = flatten(payload)
    if value(flat, _ALIASES["ntsb_number"] + _ALIASES["mkey"] + _ALIASES["event_date"]):
        return [payload]
    return []


def marker(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("marker", "nextMarker", "continuationMarker", "nextPageToken", "next"):
        item = payload.get(key)
        if item not in (None, "") and not isinstance(item, (dict, list)):
            return str(item)
    for key in ("metadata", "pagination", "page", "data"):
        found = marker(payload.get(key))
        if found:
            return found
    return None


def nested_records(item: Any, target: str) -> list[dict[str, Any]]:
    if isinstance(item, dict):
        for key, child in item.items():
            if norm(key) == norm(target) and isinstance(child, list):
                return [entry for entry in child if isinstance(entry, dict)]
            found = nested_records(child, target)
            if found:
                return found
    elif isinstance(item, list):
        for child in item:
            found = nested_records(child, target)
            if found:
                return found
    return []


def nested_text(items: list[dict[str, Any]], aliases: Iterable[str]) -> list[str]:
    values: list[str] = []
    for item in items:
        found = value(flatten(item), aliases)
        if found not in (None, ""):
            text = str(found).strip()
            if text and text not in values:
                values.append(text)
    return values


def date_value(item: Any) -> str | None:
    if item in (None, ""):
        return None
    text = str(item).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else None


def timestamp_value(item: Any) -> str | None:
    if item in (None, ""):
        return None
    text = str(item).strip()
    if re.match(r"\d{4}-\d{2}-\d{2}$", text):
        return f"{text}T00:00:00+00:00"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return None


def time_value(item: Any) -> str | None:
    if item in (None, ""):
        return None
    text = str(item).strip()
    match = re.match(r"^(\d{1,2}:\d{2}(?::\d{2})?)", text)
    return match.group(1) if match else None


def int_value(item: Any) -> int | None:
    if item in (None, ""):
        return None
    try:
        return int(float(item))
    except (TypeError, ValueError):
        return None


def payload_hash(raw: dict[str, Any]) -> str:
    serialized = json.dumps(raw, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def normalize_case(raw: dict[str, Any]) -> NormalizedCase | None:
    flat = flatten(raw)
    mkey = int_value(value(flat, _ALIASES["mkey"]))
    ntsb_number = value(flat, _ALIASES["ntsb_number"])
    if mkey is None:
        return None

    raw_aircraft = nested_records(raw, "aircrafts") or nested_records(raw, "aircraft")
    if not raw_aircraft:
        raw_aircraft = [raw]
    aircraft = []
    for index, item in enumerate(raw_aircraft, start=1):
        item_flat = flatten(item)
        candidate = NTSBAircraft(
            aircraft_sequence=index,
            make=value(item_flat, _ALIASES["make"]),
            model=value(item_flat, _ALIASES["model"]),
            registration=value(item_flat, _ALIASES["registration"]),
            category=value(item_flat, _ALIASES["category"]),
            operation=value(item_flat, _ALIASES["operation"]),
            damage=value(item_flat, _ALIASES["damage"]),
        )
        if any((candidate.make, candidate.model, candidate.registration, candidate.category, candidate.operation, candidate.damage)):
            aircraft.append(candidate)

    raw_airports = nested_records(raw, "airports")
    airports = []
    for item in raw_airports:
        item_flat = flatten(item)
        airports.append(
            {
                "airport_name": value(item_flat, ("airportFacilityName", "airportName", "airportLocationId")),
                "runway": value(item_flat, ("airportRunwayId", "runwayId", "runway")),
            }
        )

    raw_events = nested_records(raw, "events")
    raw_findings = nested_records(raw, "findings")
    event_text = nested_text(
        raw_events,
        ("eventTier2Name", "tier2Name", "eventTier1Name", "tier1Name", "cicttEventSOEGroup"),
    )
    finding_text = nested_text(raw_findings, ("findingDescription", "findingReportText", "modifierName"))
    country = value(flat, _ALIASES["country"])
    serious = int_value(value(flat, _ALIASES["serious_injuries"]))
    minor = int_value(value(flat, _ALIASES["minor_injuries"]))
    total_injuries = int_value(value(flat, _ALIASES["total_injuries"]))
    if total_injuries is None:
        total_injuries = sum(item for item in (serious, minor) if item is not None) or None

    case = NTSBCase(
        ntsb_number=str(ntsb_number).strip() if ntsb_number not in (None, "") else None,
        mkey=mkey,
        event_date=date_value(value(flat, _ALIASES["event_date"])),
        event_time=time_value(value(flat, _ALIASES["event_time"])),
        city=value(flat, _ALIASES["city"]),
        location=value(flat, _ALIASES["location"]),
        state=value(flat, _ALIASES["state"]),
        country=country,
        country_code=country_code(country),
        event_type=value(flat, _ALIASES["event_type"]),
        severity=value(flat, _ALIASES["severity"]),
        investigation_status=value(flat, _ALIASES["investigation_status"]),
        fatalities=int_value(value(flat, _ALIASES["fatalities"])),
        serious_injuries=serious,
        minor_injuries=minor,
        total_injuries=total_injuries,
        narrative=value(flat, _ALIASES["narrative"]),
        probable_cause=value(flat, _ALIASES["probable_cause"]),
        airport=airports[0]["airport_name"] if airports else None,
        runway=airports[0]["runway"] if airports else None,
        source_updated_at=timestamp_value(value(flat, _ALIASES["source_updated_at"])),
        aircraft_list=aircraft,
        events=event_text,
        findings=finding_text,
    )
    return NormalizedCase(
        case=case,
        raw=raw,
        payload_hash=payload_hash(raw),
        aircraft=aircraft,
        events=event_text,
        findings=finding_text,
        airports=airports,
    )
