"""Flexible aviation search, local filtering and context extraction."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

try:
    import pycountry
except ImportError:  # pragma: no cover - requirements install provides this package.
    pycountry = None

from ntsb.client import NTSBClient
from ntsb.models import NTSBCase, NTSBSearchQuery, NTSBSearchResult

logger = logging.getLogger(__name__)


def _run_async(coroutine: Any) -> Any:
    """Run async work from the existing synchronous public API."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coroutine).result()

_ALIASES = {
    "ntsb_number": ("ntsbn Number", "ntsbNumber", "ntsb_number", "reportNumber", "caseNumber"),
    "mkey": ("mkey", "Mkey", "id", "caseId"),
    "event_date": ("eventDate", "event_date", "accidentDate", "date", "occurrenceDate"),
    "event_time": ("eventTimeUtc", "event_time", "eventTime", "occurrenceTime"),
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
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _country_code(value: Any) -> str | None:
    """Return an ISO-3166 alpha-2 code without maintaining a country map."""
    normalized = _norm(value)
    if not normalized or pycountry is None:
        return None
    try:
        country = pycountry.countries.lookup(normalized)
    except LookupError:
        return None
    return country.alpha_2.casefold()


def _country_matches(actual: Any, expected: Any) -> bool:
    actual_code = _country_code(actual)
    expected_code = _country_code(expected)
    if actual_code and expected_code:
        return actual_code == expected_code
    return _norm(actual) == _norm(expected)


def _matching_count(cases: Iterable[NTSBCase], query: NTSBSearchQuery) -> int:
    """Count unique summary matches without treating unknown cases as duplicates."""
    identifiers: set[str] = set()
    for index, case in enumerate(cases):
        if not _matches(case, query):
            continue
        identifier = case.identifier
        identifiers.add(identifier if identifier != "unknown" else f"unknown:{index}")
    return len(identifiers)


def _ranking_value(case: NTSBCase, field_name: str) -> int | float | str | None:
    if field_name == "fatalities":
        if case.fatalities is not None:
            return case.fatalities
        # A non-fatal highest injury level is sufficient to rank the case at zero
        # without paying for a detail request. Unknown/fatal summaries remain candidates.
        if case.severity and "fatal" not in _norm(case.severity):
            return 0
        return None
    if field_name == "injuries":
        return case.injuries
    if field_name == "date":
        return case.event_date
    return None


def _needs_fatality_detail(case: NTSBCase) -> bool:
    return (
        case.fatalities is None
        and bool(case.severity)
        and "fatal" in _norm(case.severity)
    )


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


def _nested_records(value: Any, target: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if _norm(key) == _norm(target) and isinstance(child, list):
                return [item for item in child if isinstance(item, dict)]
            found = _nested_records(child, target)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _nested_records(child, target)
            if found:
                return found
    return []


def _nested_text(records: list[dict[str, Any]], aliases: Iterable[str]) -> list[str]:
    values: list[str] = []
    for record in records:
        flat = _flatten(record)
        value = _value(flat, aliases)
        if value not in (None, ""):
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


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
    airports = _nested_records(raw, "airports")
    events = _nested_records(raw, "events")
    findings = _nested_records(raw, "findings")
    airport_name = _value(
        _flatten(airports[0]) if airports else {},
        ("airportFacilityName", "airportName", "airportLocationId"),
    )
    runway_id = _value(
        _flatten(airports[0]) if airports else {},
        ("airportRunwayId", "runwayId", "runway"),
    )
    runway = str(runway_id) if runway_id not in (None, "") else None
    event_text = _nested_text(
        events,
        ("eventTier2Name", "tier2Name", "eventTier1Name", "tier1Name", "cicttEventSOEGroup"),
    )
    finding_text = _nested_text(
        findings,
        ("findingDescription", "findingReportText", "modifierName"),
    )
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
        event_time=_value(flat, _ALIASES["event_time"]),
        event_type=_value(flat, _ALIASES["event_type"]),
        severity=_value(flat, _ALIASES["severity"]),
        investigation_status=_value(flat, _ALIASES["investigation_status"]),
        fatalities=_number(_value(flat, _ALIASES["fatalities"])),
        injuries=_number(_value(flat, _ALIASES["injuries"])),
        narrative=_value(flat, _ALIASES["narrative"]),
        probable_cause=_value(flat, _ALIASES["probable_cause"]),
        airport=airport_name,
        runway=runway,
        events=event_text,
        findings=finding_text,
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
        (case.event_type, query.event_type),
        (case.investigation_status, query.investigation_status),
    )
    if any(expected and not _contains(actual, expected) for actual, expected in checks):
        return False
    if query.country and not _country_matches(case.country, query.country):
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
        upper_bound = date.fromisoformat(query.end_date) if query.end_date else requested_end_date
        requested_days = (requested_end_date - requested_start_date).days
        window_days = min(requested_days, self.client.config.search_window_days)
        if query.intent != "count" and requested_days > window_days:
            if query.sort == "date_desc":
                start = (requested_end_date - timedelta(days=window_days)).isoformat()
            else:
                end = (requested_start_date + timedelta(days=window_days)).isoformat()
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
        prefetched_windows = (
            self._fetch_rank_windows(
                self._rank_window_specs(
                    start,
                    end,
                    query,
                    lower_bound,
                    upper_bound,
                    days,
                    windows,
                )
            )
            if query.goal == "rank" and query.requires_full_scan
            else None
        )
        window_count = len(prefetched_windows) if prefetched_windows is not None else windows
        if prefetched_windows is not None:
            rank_specs = self._rank_window_specs(
                start,
                end,
                query,
                lower_bound,
                upper_bound,
                days,
                windows,
            )
            covered_start = min(window_start for window_start, _ in rank_specs)
            covered_end = max(window_end for _, window_end in rank_specs)
        for window_index in range(window_count):
            if prefetched_windows is not None:
                window_cases, window_pages, window_records, window_truncated = prefetched_windows[window_index]
            else:
                window_cases, window_pages, window_records, window_truncated = self._fetch_window(
                    start,
                    end,
                    query=query,
                    existing_cases=payload_cases,
                )
            payload_cases.extend(window_cases)
            pages += window_pages
            records_examined += window_records
            truncated = truncated or window_truncated
            if self._can_stop_early(query) and _matching_count(payload_cases, query) >= query.limit:
                break
            if (
                window_index == window_count - 1
                or (
                    query.sort == "date_desc"
                    and lower_bound
                    and date.fromisoformat(start) <= lower_bound
                )
                or (
                    query.sort == "date_asc"
                    and upper_bound
                    and date.fromisoformat(end) >= upper_bound
                )
            ):
                break
            if query.sort == "date_desc":
                previous_end = date.fromisoformat(start) - timedelta(days=1)
                end = previous_end.isoformat()
                next_start = previous_end - timedelta(days=days * 2)
                start = max(lower_bound, next_start).isoformat() if lower_bound else next_start.isoformat()
                covered_start = start
            else:
                previous_start = date.fromisoformat(end) + timedelta(days=1)
                start = previous_start.isoformat()
                next_end = previous_start + timedelta(days=days * 2)
                end = min(upper_bound, next_end).isoformat() if upper_bound else next_end.isoformat()
                covered_end = end
            days *= 2
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
        for index, case in enumerate(filtered):
            identifier = case.identifier
            if identifier == "unknown":
                identifier = f"unknown:{index}"
            unique[identifier] = case
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
        if candidates and not unique:
            logger.warning(
                "NTSB filters returned no matches candidates=%d observed_country=%s "
                "observed_state=%s observed_event_type=%s",
                len(candidates),
                self._observed_values(candidates, "country"),
                self._observed_values(candidates, "state"),
                self._observed_values(candidates, "event_type"),
            )

        # The date-range endpoint already includes the fields needed by most
        # filters. Only hydrate summaries when they did not yield enough
        # matches; otherwise a simple "last five" query would fan out into
        # hundreds of detail requests.
        ranking_detail_needed = query.goal == "rank" and any(
            _needs_fatality_detail(case) for case in candidates
        )
        if (
            (
                query.intent != "count"
                and len(unique) < query.limit
                and self._needs_detail_for_filter(query)
            )
            or ranking_detail_needed
        ):
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
        if query.goal == "rank" and query.ranking_field:
            available = [
                case for case in cases
                if _ranking_value(case, query.ranking_field) is not None
            ]
            missing = [
                case for case in cases
                if _ranking_value(case, query.ranking_field) is None
            ]
            available.sort(
                key=lambda item: _ranking_value(item, query.ranking_field),
                reverse=query.ranking_order == "desc",
            )
            cases = available + missing
            unknown_rank = sum(
                _ranking_value(case, query.ranking_field) is None for case in cases
            )
            if unknown_rank:
                logger.warning(
                    "NTSB ranking has %d cases without %s in the summary; "
                    "they were not hydrated automatically",
                    unknown_rank,
                    query.ranking_field,
                )
        else:
            cases.sort(key=lambda item: item.event_date or "", reverse=query.sort == "date_desc")
        if self._should_hydrate(query):
            cases = self._hydrate(cases[: query.limit], hydrated)
        else:
            cases = cases[: query.limit]
            logger.info(
                "NTSB detail hydration skipped needs_detail=%s intent=%s",
                query.needs_detail,
                query.intent,
            )
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

    def _fetch_window(
        self,
        start: str,
        end: str,
        *,
        query: NTSBSearchQuery | None = None,
        existing_cases: list[NTSBCase] | None = None,
    ) -> tuple[list[NTSBCase], int, int, bool]:
        cases: list[NTSBCase] = []
        existing_cases = existing_cases or []
        pages = 0
        records_examined = 0
        marker = None
        truncated = False
        while pages < self.client.config.max_pages and records_examined < self.client.config.max_records:
            payload = self.client.get_cases_by_date_range(start_date=start, end_date=end, marker=marker)
            pages += 1
            raw_cases = _records(payload)
            records_examined += len(raw_cases)
            marker = _marker(payload)
            matched_identifiers = {
                case.identifier
                for case in existing_cases
                if query is not None and _matches(case, query)
            }
            early_stop = False
            records_processed = 0
            for raw_index, raw_case in enumerate(raw_cases):
                case = normalize_case(raw_case)
                cases.append(case)
                records_processed = raw_index + 1
                if query is None or not self._can_stop_early(query) or not _matches(case, query):
                    continue
                identifier = case.identifier
                if identifier == "unknown":
                    identifier = f"unknown:{len(existing_cases) + raw_index}"
                matched_identifiers.add(identifier)
                if len(matched_identifiers) >= query.limit:
                    early_stop = True
                    break
            logger.info(
                "NTSB date page window=%s..%s page=%d records_received=%d "
                "records_processed=%d marker=%s total_records=%d",
                start,
                end,
                pages,
                len(raw_cases),
                records_processed,
                marker[:40] + "..." if marker and len(marker) > 40 else marker,
                records_examined,
            )
            if early_stop:
                logger.info(
                    "NTSB early stop after summary match window=%s..%s page=%d "
                    "records_received=%d records_processed=%d matches=%d limit=%d",
                    start,
                    end,
                    pages,
                    len(raw_cases),
                    records_processed,
                    len(matched_identifiers),
                    query.limit,
                )
                break
            if not marker or not raw_cases:
                break
        else:
            truncated = True
        return cases, pages, records_examined, truncated

    def _rank_window_specs(
        self,
        start: str,
        end: str,
        query: NTSBSearchQuery,
        lower_bound: date | None,
        upper_bound: date | None,
        days: int,
        windows: int,
    ) -> list[tuple[str, str]]:
        specs: list[tuple[str, str]] = []
        for _ in range(windows):
            specs.append((start, end))
            if query.sort == "date_desc":
                if lower_bound and date.fromisoformat(start) <= lower_bound:
                    break
                previous_end = date.fromisoformat(start) - timedelta(days=1)
                end = previous_end.isoformat()
                next_start = previous_end - timedelta(days=days * 2)
                start = max(lower_bound, next_start).isoformat() if lower_bound else next_start.isoformat()
            else:
                if upper_bound and date.fromisoformat(end) >= upper_bound:
                    break
                previous_start = date.fromisoformat(end) + timedelta(days=1)
                start = previous_start.isoformat()
                next_end = previous_start + timedelta(days=days * 2)
                end = min(upper_bound, next_end).isoformat() if upper_bound else next_end.isoformat()
            days *= 2
        return specs

    def _fetch_rank_windows(
        self,
        specs: list[tuple[str, str]],
    ) -> list[tuple[list[NTSBCase], int, int, bool]]:
        return _run_async(self._fetch_rank_windows_async(specs))

    async def _fetch_rank_windows_async(
        self,
        specs: list[tuple[str, str]],
    ) -> list[tuple[list[NTSBCase], int, int, bool]]:
        async with self.client.async_session() as session:
            return await asyncio.gather(
                *(self._fetch_rank_window_async(start, end, session) for start, end in specs)
            )

    async def _fetch_rank_window_async(
        self,
        start: str,
        end: str,
        session: Any,
    ) -> tuple[list[NTSBCase], int, int, bool]:
        cases: list[NTSBCase] = []
        pages = 0
        records_examined = 0
        marker = None
        truncated = False
        while pages < self.client.config.max_pages and records_examined < self.client.config.max_records:
            payload = await self.client.get_cases_by_date_range_async(
                start_date=start,
                end_date=end,
                marker=marker,
                session=session,
            )
            pages += 1
            raw_cases = _records(payload)
            records_examined += len(raw_cases)
            cases.extend(normalize_case(item) for item in raw_cases)
            marker = _marker(payload)
            logger.info(
                "NTSB rank date page window=%s..%s page=%d records_received=%d "
                "marker=%s total_records=%d",
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
        return _run_async(self._hydrate_async(cases, cache))

    async def _hydrate_async(
        self,
        cases: list[NTSBCase],
        cache: dict[str, NTSBCase],
    ) -> list[NTSBCase]:
        """Hydrate independent cases concurrently while preserving result order."""
        semaphore = asyncio.Semaphore(self.client.config.max_concurrency)

        async def hydrate_one(
            case: NTSBCase,
            session: Any,
        ) -> tuple[NTSBCase, bool]:
            if case.identifier in cache:
                return cache[case.identifier], False
            if not case.ntsb_number and case.mkey is None:
                return case, False
            try:
                async with semaphore:
                    payload = await self.client.get_aviation_case_async(
                        ntsb_number=case.ntsb_number,
                        mkey=case.mkey,
                        session=session,
                    )
                details = _records(payload)
                result = normalize_case({**case.raw, **details[0]}) if details else case
                return result, True
            except Exception as exc:  # Details are an enrichment, not search availability.
                logger.warning("Could not hydrate NTSB case %s: %s", case.identifier, exc)
                return case, True

        async with self.client.async_session() as session:
            results = await asyncio.gather(*(hydrate_one(case, session) for case in cases))

        hydrated = []
        detail_requests = 0
        for case, requested in results:
            if requested:
                detail_requests += 1
            cache[case.identifier] = case
            hydrated.append(case)
        if detail_requests:
            logger.info(
                "NTSB detail hydration requested=%d cache_hits=%d returned=%d",
                detail_requests,
                len(cases) - detail_requests,
                len(hydrated),
            )
        return hydrated

    @staticmethod
    def _should_hydrate(query: NTSBSearchQuery) -> bool:
        """Only request details when the planner says the summary cannot answer."""
        return query.intent != "count" and (query.needs_detail or bool(query.text))

    @staticmethod
    def _can_stop_early(query: NTSBSearchQuery) -> bool:
        return (
            query.intent != "count"
            and not query.requires_full_scan
            and query.goal not in {"rank", "compare"}
        )

    @staticmethod
    def _observed_values(cases: list[NTSBCase], field_name: str) -> list[str]:
        values = {
            str(getattr(case, field_name))
            for case in cases
            if getattr(case, field_name) not in (None, "")
        }
        return sorted(values)[:10]

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
                or (
                    query.goal == "rank"
                    and _needs_fatality_detail(case)
                )
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
        warnings = ["Search reached a configured limit."] if truncated else []
        if truncated and query.goal in {"rank", "compare"}:
            warnings.append("Ranking is incomplete and cannot guarantee the global result.")
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
            warnings=warnings,
        )


def context_from_result(result: NTSBSearchResult) -> list[dict[str, Any]]:
    return result.context_items()
