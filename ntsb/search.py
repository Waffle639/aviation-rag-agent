"""Flexible aviation search, local filtering and context extraction."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from ntsb.client import NTSBClient
from ntsb.models import NTSBCase, NTSBSearchQuery, NTSBSearchResult

logger = logging.getLogger(__name__)

_ALIASES = {
    "ntsb_number": ("ntsbn Number", "ntsbNumber", "ntsb_number", "reportNumber", "caseNumber"),
    "mkey": ("mkey", "Mkey", "id", "caseId"),
    "event_date": ("eventDate", "event_date", "accidentDate", "date", "occurrenceDate"),
    "make": ("aircraftMake", "aircraft_make", "make", "manufacturer", "aircraftManufacturer"),
    "model": ("aircraftModel", "aircraft_model", "model", "aircraftType"),
    "registration": ("aircraftRegistrationNumber", "registration", "registrationNumber", "tailNumber"),
    "location": ("location", "accidentLocation", "eventCity", "eventLocation", "city", "site", "place"),
    "state": ("state", "stateName", "eventStateOrRegion", "province"),
    "country": ("country", "countryName", "eventCountry"),
    "event_type": ("eventType", "event_type", "accidentType", "occurrenceType"),
    "severity": ("severity", "injuryLevel", "injurySeverity", "highestInjury", "highestInjuryLevel"),
    "investigation_status": ("investigationStatus", "completionStatus", "investigationClass", "status", "caseStatus"),
    "fatalities": ("fatalities", "fatalInjuries", "totalFatalities", "totalFatal", "deathCount"),
    "injuries": ("injuries", "seriousInjuries", "totalInjuries", "totalSerious", "totalMinor", "injuryCount"),
    "narrative": (
        "narrative", "summary", "eventNarrative", "analysisNarrative",
        "prelimNarrative", "concatenatedFactualNarrative", "description", "synopsis",
    ),
    "probable_cause": ("probableCause", "probable_cause", "cause", "causeText"),
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _flatten(value: Any, result: dict[str, Any] | None = None) -> dict[str, Any]:
    result = result or {}
    if isinstance(value, dict):
        for key, child in value.items():
            result[_norm(key)] = child
            _flatten(child, result)
    elif isinstance(value, list):
        for child in value:
            _flatten(child, result)
    return result


def _value(flat: dict[str, Any], aliases: Iterable[str]) -> Any:
    for alias in aliases:
        value = flat.get(_norm(alias))
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return value
    return None


def _records(payload: Any) -> list[dict[str, Any]]:
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
            nested = _records(child)
            if nested:
                return nested
    flat = _flatten(payload)
    if _value(flat, _ALIASES["ntsb_number"] + _ALIASES["mkey"] + _ALIASES["event_date"]):
        return [payload]
    return []


def _marker(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("marker", "nextMarker", "continuationMarker", "nextPageToken", "next"):
        value = payload.get(key)
        if value not in (None, "") and not isinstance(value, (dict, list)):
            return str(value)
    for key in ("metadata", "pagination", "page", "data"):
        value = payload.get(key)
        found = _marker(value)
        if found:
            return found
    return None


def _date_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10] if re.match(r"\d{4}-\d{2}-\d{2}", text) else text


def _number(value: Any) -> int | float | str | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return str(value)


def normalize_case(raw: dict[str, Any]) -> NTSBCase:
    flat = _flatten(raw)
    mkey = _value(flat, _ALIASES["mkey"])
    try:
        if mkey is not None:
            mkey = int(mkey)
    except (TypeError, ValueError):
        pass
    return NTSBCase(
        ntsb_number=_value(flat, _ALIASES["ntsb_number"]),
        mkey=mkey,
        event_date=_date_value(_value(flat, _ALIASES["event_date"])),
        make=_value(flat, _ALIASES["make"]),
        model=_value(flat, _ALIASES["model"]),
        registration=_value(flat, _ALIASES["registration"]),
        location=_value(flat, _ALIASES["location"]),
        state=_value(flat, _ALIASES["state"]),
        country=_value(flat, _ALIASES["country"]),
        event_type=_value(flat, _ALIASES["event_type"]),
        severity=_value(flat, _ALIASES["severity"]),
        investigation_status=_value(flat, _ALIASES["investigation_status"]),
        fatalities=_number(_value(flat, _ALIASES["fatalities"])),
        injuries=_number(_value(flat, _ALIASES["injuries"])),
        narrative=_value(flat, _ALIASES["narrative"]),
        probable_cause=_value(flat, _ALIASES["probable_cause"]),
        raw=raw,
    )


def _contains(actual: Any, expected: str) -> bool:
    return _norm(expected) in _norm(actual)


def _matches(case: NTSBCase, query: NTSBSearchQuery) -> bool:
    checks = (
        (case.make, query.make),
        (case.model, query.model),
        (case.location, query.location),
        (case.state, query.state),
        (case.country, query.country),
        (case.event_type, query.event_type),
        (case.investigation_status, query.investigation_status),
    )
    if any(expected and not _contains(actual, expected) for actual, expected in checks):
        return False
    if query.registration and not _contains(case.registration, query.registration):
        return False
    if query.severity:
        severity = _norm(case.severity)
        if "fatal" in _norm(query.severity):
            if "fatal" not in severity and not (isinstance(case.fatalities, (int, float)) and case.fatalities > 0):
                return False
        elif not _contains(case.severity, query.severity):
            return False
    if query.text:
        haystack = " ".join(
            _norm(value)
            for value in (case.narrative, case.probable_cause, case.event_type, case.location, case.severity)
            if value
        )
        if _norm(query.text) not in haystack:
            return False
    if query.start_date and case.event_date and case.event_date < query.start_date:
        return False
    if query.end_date and case.event_date and case.event_date > query.end_date:
        return False
    return True


class NTSBSearchService:
    def __init__(self, client: NTSBClient | None = None):
        self.client = client or NTSBClient()

    def search(self, query: NTSBSearchQuery) -> NTSBSearchResult:
        log_query = {
            key: (value[:120] + "..." if isinstance(value, str) and len(value) > 120 else value)
            for key, value in query.to_dict().items()
            if value not in (None, "", False)
        }
        logger.info("NTSB search started intent=%s filters=%s", query.intent, log_query)
        if query.intent == "detail" or query.ntsb_number or query.mkey is not None:
            logger.info(
                "NTSB strategy=detail endpoint=/api/Aviation/v1/GetAviationCase/ "
                "ntsb_number=%s mkey=%s",
                query.ntsb_number,
                query.mkey,
            )
            payload = self.client.get_aviation_case(ntsb_number=query.ntsb_number, mkey=query.mkey)
            cases = [normalize_case(item) for item in _records(payload)]
            logger.info("NTSB detail response cases=%d", len(cases))
            return self._result(
                query, cases, 1, len(cases), query.start_date, query.end_date,
                matches_found=len(cases),
            )

        if query.registration and not any(
            (query.start_date, query.end_date, query.make, query.model, query.location, query.state, query.country, query.text)
        ):
            logger.info(
                "NTSB strategy=registration endpoint=/api/Aviation/v1/GetAviationCasesFiltered/ "
                "aircraftRegistrationNumber=%s",
                query.registration,
            )
            payload = self.client.get_cases_by_registration(query.registration)
            raw_cases = _records(payload)
            cases = [case for case in (normalize_case(item) for item in raw_cases) if _matches(case, query)]
            logger.info(
                "NTSB registration response records=%d local_matches=%d",
                len(raw_cases),
                len(cases),
            )
            return self._result(
                query, cases, 1, len(raw_cases), query.start_date, query.end_date,
                matches_found=len(cases),
            )

        requested_start, requested_end = self._window(query)
        start, end = requested_start, requested_end
        lower_bound = date.fromisoformat(query.start_date) if query.start_date else None
        requested_start_date = date.fromisoformat(requested_start)
        requested_end_date = date.fromisoformat(requested_end)
        requested_days = (requested_end_date - requested_start_date).days
        window_days = min(requested_days, self.client.config.search_window_days)
        if query.intent != "count" and requested_days > window_days:
            start = (requested_end_date - timedelta(days=window_days)).isoformat()
        logger.info(
            "NTSB strategy=date_range endpoint=/api/Common/v2/GetCasesByDateRange/ "
            "server_filters=%s local_filters=%s",
            {"startDate": start, "endDate": end, "mode": "aviation"},
            {
                key: value
                for key, value in log_query.items()
                if key not in {"intent", "start_date", "end_date", "sort", "limit"}
            },
        )
        covered_start, covered_end = start, end
        payload_cases: list[NTSBCase] = []
        pages = 0
        records_examined = 0
        truncated = False
        days = max(1, (date.fromisoformat(end) - date.fromisoformat(start)).days)
        windows = 1 if query.intent == "count" else self.client.config.max_windows
        for window_index in range(windows):
            window_cases, window_pages, window_records, window_truncated = self._fetch_window(start, end)
            payload_cases.extend(window_cases)
            pages += window_pages
            records_examined += window_records
            truncated = truncated or window_truncated
            filtered_now = [case for case in payload_cases if _matches(case, query)]
            if query.intent != "count" and len({case.identifier for case in filtered_now}) >= query.limit:
                break
            if (
                window_index == windows - 1
                or (lower_bound and date.fromisoformat(start) <= lower_bound)
            ):
                break
            previous_end = date.fromisoformat(start) - timedelta(days=1)
            end = previous_end.isoformat()
            next_start = previous_end - timedelta(days=days * 2)
            start = max(lower_bound, next_start).isoformat() if lower_bound else next_start.isoformat()
            days *= 2
            covered_start = start
        else:
            truncated = True

        unique: dict[str, NTSBCase] = {}
        for index, case in enumerate(payload_cases):
            identifier = case.identifier
            if identifier == "unknown":
                identifier = f"unknown:{index}"
            unique[identifier] = case
        candidates = list(unique.values())
        hydrated: dict[str, NTSBCase] = {}
        filtered = [case for case in candidates if _matches(case, query)]
        unique = {}
        for case in filtered:
            unique[case.identifier] = case
        logger.info(
            "NTSB local filtering candidates=%d matches=%d filters=%s",
            len(candidates),
            len(unique),
            {
                key: value
                for key, value in log_query.items()
                if key not in {"intent", "start_date", "end_date", "sort", "limit"}
            },
        )

        # The date-range endpoint already includes the fields needed by most
        # filters. Only hydrate summaries when they did not yield enough
        # matches; otherwise a simple "last five" query would fan out into
        # hundreds of detail requests.
        if len(unique) < query.limit and self._needs_detail_for_filter(query):
            logger.info(
                "NTSB local filtering returned %d/%d; hydrating summaries missing filter fields "
                "max_hydration=%d",
                len(unique),
                query.limit,
                self.client.config.max_hydration,
            )
            candidates = self._hydrate_missing_fields(candidates, query, hydrated)
            filtered = [case for case in candidates if _matches(case, query)]
            unique = {}
            for case in filtered:
                unique[case.identifier] = case
            logger.info("NTSB local filtering after hydration matches=%d", len(unique))

        cases = list(unique.values())
        cases.sort(key=lambda item: item.event_date or "", reverse=query.sort == "date_desc")
        cases = self._hydrate(cases[: query.limit], hydrated)
        logger.info(
            "NTSB search finished matches=%d returned=%d pages=%d records_examined=%d "
            "covered_start=%s covered_end=%s truncated=%s",
            len(unique),
            len(cases),
            pages,
            records_examined,
            covered_start,
            covered_end,
            truncated,
        )
        return self._result(
            query, cases, pages, records_examined, covered_start, covered_end, truncated,
            matches_found=len(unique),
        )

    def _fetch_window(self, start: str, end: str) -> tuple[list[NTSBCase], int, int, bool]:
        cases: list[NTSBCase] = []
        pages = 0
        records_examined = 0
        marker = None
        truncated = False
        while pages < self.client.config.max_pages and records_examined < self.client.config.max_records:
            payload = self.client.get_cases_by_date_range(start_date=start, end_date=end, marker=marker)
            pages += 1
            raw_cases = _records(payload)
            records_examined += len(raw_cases)
            cases.extend(normalize_case(item) for item in raw_cases)
            marker = _marker(payload)
            logger.info(
                "NTSB date page window=%s..%s page=%d records=%d marker=%s "
                "total_records=%d",
                start,
                end,
                pages,
                len(raw_cases),
                marker[:40] + "..." if marker and len(marker) > 40 else marker,
                records_examined,
            )
            if not marker or not raw_cases:
                break
        else:
            truncated = True
        return cases, pages, records_examined, truncated

    def _window(self, query: NTSBSearchQuery) -> tuple[str, str]:
        today = date.today()
        end = query.end_date or today.isoformat()
        start = query.start_date
        if not start:
            end_date = date.fromisoformat(end)
            start = (end_date - timedelta(days=90)).isoformat()
        return start, end

    def _hydrate(
        self,
        cases: list[NTSBCase],
        cache: dict[str, NTSBCase] | None = None,
    ) -> list[NTSBCase]:
        cache = cache if cache is not None else {}
        hydrated = []
        detail_requests = 0
        for case in cases:
            if case.identifier in cache:
                hydrated.append(cache[case.identifier])
                continue
            if not case.ntsb_number and case.mkey is None:
                cache[case.identifier] = case
                hydrated.append(case)
                continue
            try:
                detail_requests += 1
                payload = self.client.get_aviation_case(ntsb_number=case.ntsb_number, mkey=case.mkey)
                details = _records(payload)
                result = normalize_case({**case.raw, **details[0]}) if details else case
            except Exception as exc:  # Details are an enrichment, not search availability.
                logger.warning("Could not hydrate NTSB case %s: %s", case.identifier, exc)
                result = case
            cache[case.identifier] = result
            hydrated.append(result)
        if detail_requests:
            logger.info(
                "NTSB detail hydration requested=%d cache_hits=%d returned=%d",
                detail_requests,
                len(cases) - detail_requests,
                len(hydrated),
            )
        return hydrated

    def _hydrate_missing_fields(
        self,
        cases: list[NTSBCase],
        query: NTSBSearchQuery,
        cache: dict[str, NTSBCase],
    ) -> list[NTSBCase]:
        """Hydrate summaries before local filtering, without an unbounded fan-out."""
        needs = []
        for case in cases:
            missing = (
                (query.make and not case.make)
                or (query.model and not case.model)
                or (query.location and not case.location)
                or (query.state and not case.state)
                or (query.country and not case.country)
                or (query.event_type and not case.event_type)
                or (query.investigation_status and not case.investigation_status)
                or (query.severity and not case.severity and case.fatalities is None)
                or (query.text and not (case.narrative or case.probable_cause))
                or (query.registration and not case.registration)
            )
            if missing:
                needs.append(case)
        self._hydrate(needs[: self.client.config.max_hydration], cache)
        return [cache.get(case.identifier, case) for case in cases]

    @staticmethod
    def _needs_detail_for_filter(query: NTSBSearchQuery) -> bool:
        return any(
            (
                query.make, query.model, query.location, query.state, query.country,
                query.event_type, query.investigation_status, query.severity,
                query.text, query.registration,
            )
        )

    @staticmethod
    def _result(
        query: NTSBSearchQuery,
        cases: list[NTSBCase],
        pages: int,
        records: int,
        start: str | None,
        end: str | None,
        truncated: bool = False,
        matches_found: int = 0,
    ) -> NTSBSearchResult:
        return NTSBSearchResult(
            cases=cases[: query.limit],
            query=query,
            pages_examined=pages,
            records_examined=records,
            matches_found=matches_found,
            truncated=truncated,
            covered_start=start,
            covered_end=end,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            warnings=["Search reached a configured limit."] if truncated else [],
        )


def context_from_result(result: NTSBSearchResult) -> list[dict[str, Any]]:
    return result.context_items()
