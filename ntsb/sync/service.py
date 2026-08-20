"""Backfill and incremental synchronization for the local NTSB index."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, Iterable

from langsmith import tracing_context
import psycopg2
from psycopg2.extras import Json

from ntsb.sync.api_client import NTSBAPIClient
from ntsb.sync.config import NTSBSyncConfig
from ntsb.sync.normalizer import NormalizedCase, marker, normalize_case, records

logger = logging.getLogger(__name__)


@dataclass
class SyncStats:
    pages: int = 0
    records_received: int = 0
    cases_upserted: int = 0
    details_fetched: int = 0
    skipped_existing: int = 0
    rejected: int = 0


class NTSBSyncService:
    def __init__(
        self,
        api_client: NTSBAPIClient | None = None,
        config: NTSBSyncConfig | None = None,
        connection: Any | None = None,
    ):
        self._api_client = api_client
        self.config = config or NTSBSyncConfig.from_env()
        self._connection = connection

    @property
    def api_client(self) -> NTSBAPIClient:
        if self._api_client is None:
            self._api_client = NTSBAPIClient()
        return self._api_client

    def run_backfill(
        self,
        *,
        hydrate_details: bool = True,
        refresh_existing: bool = False,
    ) -> SyncStats:
        with tracing_context(enabled=False):
            return asyncio.run(
                self.backfill(
                    hydrate_details=hydrate_details,
                    refresh_existing=refresh_existing,
                )
            )

    def run_incremental(self, *, hydrate_details: bool = True) -> SyncStats:
        with tracing_context(enabled=False):
            return asyncio.run(self.incremental(hydrate_details=hydrate_details))

    def status(self) -> dict[str, Any]:
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection.cursor() as cursor:
                cursor.execute("select count(*), max(synced_at), min(event_date), max(event_date) from ntsb.cases")
                total, last_synced_at, min_event_date, max_event_date = cursor.fetchone()
                cursor.execute(
                    """
                    select stream, last_successful_start, last_successful_end, marker, status, error, updated_at
                    from ntsb.sync_state
                    order by stream
                    """
                )
                checkpoints = [
                    {
                        "stream": row[0],
                        "last_successful_start": row[1].isoformat() if row[1] else None,
                        "last_successful_end": row[2].isoformat() if row[2] else None,
                        "marker": row[3],
                        "status": row[4],
                        "error": row[5],
                        "updated_at": row[6].isoformat() if row[6] else None,
                    }
                    for row in cursor.fetchall()
                ]
        finally:
            if close_connection:
                connection.close()
        return {
            "cases": int(total),
            "last_synced_at": last_synced_at.isoformat() if last_synced_at else None,
            "event_date_min": min_event_date.isoformat() if min_event_date else None,
            "event_date_max": max_event_date.isoformat() if max_event_date else None,
            "checkpoints": checkpoints,
        }

    async def backfill(
        self,
        *,
        hydrate_details: bool = True,
        refresh_existing: bool = False,
    ) -> SyncStats:
        with tracing_context(enabled=False):
            start = self._backfill_start()
            today = datetime.now(timezone.utc).date()
            stats = SyncStats()
            async with self.api_client.async_session() as session:
                while start <= today:
                    end = min(start + timedelta(days=self.config.window_days - 1), today)
                    window_stats = await self._sync_date_window(
                        start.isoformat(),
                        end.isoformat(),
                        stream="backfill",
                        hydrate_details=hydrate_details,
                        skip_existing=not refresh_existing,
                        session=session,
                    )
                    self._merge_stats(stats, window_stats)
                    start = end + timedelta(days=1)
            return stats

    async def incremental(self, *, hydrate_details: bool = True) -> SyncStats:
        with tracing_context(enabled=False):
            now = datetime.now(timezone.utc)
            start_at = self._incremental_start(now)
            async with self.api_client.async_session() as session:
                return await self._sync_modified_window(
                    start_at.date().isoformat(),
                    now.date().isoformat(),
                    stream="incremental",
                    hydrate_details=hydrate_details,
                    session=session,
                )

    async def sync_case_detail(
        self,
        *,
        ntsb_number: str | None = None,
        mkey: int | str | None = None,
        session: Any | None = None,
    ) -> NormalizedCase | None:
        with tracing_context(enabled=False):
            payload = await self.api_client.get_aviation_case(
                ntsb_number=ntsb_number,
                mkey=mkey,
                session=session,
            )
            normalized = self._normalize_records(records(payload))
            if not normalized:
                return None
            self.upsert_cases(normalized, cache_detail=True)
            return normalized[0]

    async def _sync_date_window(
        self,
        start_date: str,
        end_date: str,
        *,
        stream: str,
        hydrate_details: bool,
        skip_existing: bool,
        session: Any,
    ) -> SyncStats:
        async def fetch_page(marker_value: str | None) -> Any:
            return await self.api_client.get_cases_by_date_range(
                start_date=start_date,
                end_date=end_date,
                marker=marker_value,
                session=session,
            )

        return await self._sync_paged_window(
            fetch_page,
            stream=stream,
            window_start=start_date,
            window_end=end_date,
            hydrate_details=hydrate_details,
            skip_existing=skip_existing,
            session=session,
        )

    async def _sync_modified_window(
        self,
        start_date: str,
        end_date: str,
        *,
        stream: str,
        hydrate_details: bool,
        session: Any,
    ) -> SyncStats:
        async def fetch_page(marker_value: str | None) -> Any:
            return await self.api_client.get_cases_by_modified_date_range(
                start_date=start_date,
                end_date=end_date,
                marker=marker_value,
                session=session,
            )

        return await self._sync_paged_window(
            fetch_page,
            stream=stream,
            window_start=start_date,
            window_end=end_date,
            hydrate_details=hydrate_details,
            skip_existing=False,
            session=session,
        )

    async def _sync_paged_window(
        self,
        fetch_page: Any,
        *,
        stream: str,
        window_start: str,
        window_end: str,
        hydrate_details: bool,
        skip_existing: bool,
        session: Any,
    ) -> SyncStats:
        stats = SyncStats()
        run_id = self._start_run(stream)
        next_marker = None
        try:
            while True:
                payload = await fetch_page(next_marker)
                raw_records = records(payload)
                stats.pages += 1
                stats.records_received += len(raw_records)
                normalized = self._normalize_records(raw_records)
                stats.rejected += len(raw_records) - len(normalized)
                normalized, skipped_duplicates = self._dedupe_batch(normalized)
                stats.skipped_existing += skipped_duplicates
                if skip_existing and normalized:
                    existing_mkeys, existing_numbers = self._existing_case_keys(normalized)
                    before_skip = len(normalized)
                    normalized = [
                        item for item in normalized
                        if item.case.mkey not in existing_mkeys
                        and (item.case.ntsb_number or "").upper() not in existing_numbers
                    ]
                    stats.skipped_existing += before_skip - len(normalized)
                if hydrate_details and normalized:
                    normalized = await self._hydrate_cases(normalized, session=session)
                    stats.details_fetched += len(normalized)
                stats.cases_upserted += self.upsert_cases(normalized, cache_detail=hydrate_details)
                next_marker = marker(payload)
                self._update_checkpoint(stream, window_start, window_end, next_marker, "running", None)
                logger.info(
                    "NTSB sync window=%s..%s page=%d records=%d skipped_existing=%d marker=%s",
                    window_start,
                    window_end,
                    stats.pages,
                    len(raw_records),
                    stats.skipped_existing,
                    next_marker,
                )
                if not next_marker or not raw_records:
                    break
            self._update_checkpoint(stream, window_start, window_end, None, "idle", None)
            self._finish_run(run_id, "completed", stats, None)
            return stats
        except Exception as exc:
            self._update_checkpoint(stream, window_start, window_end, next_marker, "failed", str(exc))
            self._finish_run(run_id, "failed", stats, str(exc))
            raise

    async def _hydrate_cases(self, cases: list[NormalizedCase], *, session: Any) -> list[NormalizedCase]:
        semaphore = asyncio.Semaphore(self.api_client.config.max_concurrency)

        async def hydrate_one(item: NormalizedCase) -> NormalizedCase:
            try:
                async with semaphore:
                    payload = await self.api_client.get_aviation_case(
                        ntsb_number=item.case.ntsb_number,
                        mkey=item.case.mkey,
                        session=session,
                    )
                detail_records = records(payload)
                if not detail_records:
                    return item
                detail = normalize_case(detail_records[0])
                return detail or item
            except Exception as exc:
                logger.warning("NTSB detail sync failed for %s: %s", item.case.identifier, exc)
                return item

        return await asyncio.gather(*(hydrate_one(item) for item in cases))

    def upsert_cases(self, cases: Iterable[NormalizedCase], *, cache_detail: bool = False) -> int:
        cases, _ = self._dedupe_batch(list(cases))
        if not cases:
            return 0
        connection = self._connect()
        close_connection = self._connection is None
        upserted = 0
        try:
            with connection:
                with connection.cursor() as cursor:
                    for item in cases:
                        if self._upsert_case(cursor, item, cache_detail=cache_detail):
                            upserted += 1
            return upserted
        finally:
            if close_connection:
                connection.close()

    def _upsert_case(self, cursor: Any, item: NormalizedCase, *, cache_detail: bool) -> bool:
        case = item.case
        if case.ntsb_number:
            cursor.execute(
                "select mkey from ntsb.cases where upper(ntsb_number) = upper(%s)",
                (case.ntsb_number,),
            )
            row = cursor.fetchone()
            if row and int(row[0]) != case.mkey:
                logger.warning(
                    "Skipping NTSB duplicate ntsb_number=%s existing_mkey=%s incoming_mkey=%s",
                    case.ntsb_number,
                    row[0],
                    case.mkey,
                )
                return False
        cursor.execute(
            """
            insert into ntsb.cases (
                mkey, ntsb_number, event_date, event_time, city, location, state, country,
                country_code, event_type, severity, investigation_status, fatalities,
                serious_injuries, minor_injuries, total_injuries, narrative, probable_cause,
                airport, runway, source_updated_at, synced_at, payload_hash
            ) values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, now(), %s
            )
            on conflict (mkey) do update set
                ntsb_number = coalesce(excluded.ntsb_number, ntsb.cases.ntsb_number),
                event_date = coalesce(excluded.event_date, ntsb.cases.event_date),
                event_time = coalesce(excluded.event_time, ntsb.cases.event_time),
                city = coalesce(excluded.city, ntsb.cases.city),
                location = coalesce(excluded.location, ntsb.cases.location),
                state = coalesce(excluded.state, ntsb.cases.state),
                country = coalesce(excluded.country, ntsb.cases.country),
                country_code = coalesce(excluded.country_code, ntsb.cases.country_code),
                event_type = coalesce(excluded.event_type, ntsb.cases.event_type),
                severity = coalesce(excluded.severity, ntsb.cases.severity),
                investigation_status = coalesce(excluded.investigation_status, ntsb.cases.investigation_status),
                fatalities = coalesce(excluded.fatalities, ntsb.cases.fatalities),
                serious_injuries = coalesce(excluded.serious_injuries, ntsb.cases.serious_injuries),
                minor_injuries = coalesce(excluded.minor_injuries, ntsb.cases.minor_injuries),
                total_injuries = coalesce(excluded.total_injuries, ntsb.cases.total_injuries),
                narrative = coalesce(excluded.narrative, ntsb.cases.narrative),
                probable_cause = coalesce(excluded.probable_cause, ntsb.cases.probable_cause),
                airport = coalesce(excluded.airport, ntsb.cases.airport),
                runway = coalesce(excluded.runway, ntsb.cases.runway),
                source_updated_at = coalesce(excluded.source_updated_at, ntsb.cases.source_updated_at),
                synced_at = now(),
                payload_hash = coalesce(excluded.payload_hash, ntsb.cases.payload_hash)
            """,
            (
                case.mkey,
                case.ntsb_number,
                case.event_date,
                case.event_time,
                case.city,
                case.location,
                case.state,
                case.country,
                case.country_code,
                case.event_type,
                case.severity,
                case.investigation_status,
                case.fatalities,
                case.serious_injuries,
                case.minor_injuries,
                case.total_injuries,
                case.narrative,
                case.probable_cause,
                case.airport,
                case.runway,
                case.source_updated_at,
                item.payload_hash,
            ),
        )
        if item.aircraft:
            cursor.execute("delete from ntsb.aircraft where case_mkey = %s", (case.mkey,))
        for aircraft in item.aircraft:
            cursor.execute(
                """
                insert into ntsb.aircraft (
                    case_mkey, aircraft_sequence, make, model, registration, category, operation, damage
                ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    case.mkey,
                    aircraft.aircraft_sequence,
                    aircraft.make,
                    aircraft.model,
                    aircraft.registration,
                    aircraft.category,
                    aircraft.operation,
                    aircraft.damage,
                ),
            )
        if item.events:
            cursor.execute("delete from ntsb.events where case_mkey = %s", (case.mkey,))
        for index, event_text in enumerate(item.events, start=1):
            cursor.execute(
                "insert into ntsb.events (case_mkey, event_sequence, event_text) values (%s, %s, %s)",
                (case.mkey, index, event_text),
            )
        if item.findings:
            cursor.execute("delete from ntsb.findings where case_mkey = %s", (case.mkey,))
        for index, finding_text in enumerate(item.findings, start=1):
            cursor.execute(
                "insert into ntsb.findings (case_mkey, finding_sequence, finding_text) values (%s, %s, %s)",
                (case.mkey, index, finding_text),
            )
        if item.airports:
            cursor.execute("delete from ntsb.airports where case_mkey = %s", (case.mkey,))
        for index, airport in enumerate(item.airports, start=1):
            cursor.execute(
                """
                insert into ntsb.airports (case_mkey, airport_sequence, airport_name, runway)
                values (%s, %s, %s, %s)
                """,
                (case.mkey, index, airport.get("airport_name"), airport.get("runway")),
            )
        if cache_detail:
            cursor.execute(
                """
                insert into ntsb.detail_cache (case_mkey, payload, payload_hash, fetched_at)
                values (%s, %s, %s, now())
                on conflict (case_mkey) do update set
                    payload = excluded.payload,
                    payload_hash = excluded.payload_hash,
                    fetched_at = now()
                """,
                (case.mkey, Json(item.raw), item.payload_hash),
            )
        return True

    def _normalize_records(self, raw_records: list[dict[str, Any]]) -> list[NormalizedCase]:
        normalized = []
        for raw in raw_records:
            item = normalize_case(raw)
            if item is not None:
                normalized.append(item)
        return normalized

    @staticmethod
    def _dedupe_batch(cases: list[NormalizedCase]) -> tuple[list[NormalizedCase], int]:
        seen_mkeys: set[int] = set()
        seen_numbers: set[str] = set()
        deduped: list[NormalizedCase] = []
        skipped = 0
        for item in cases:
            mkey = item.case.mkey
            number = (item.case.ntsb_number or "").upper()
            if mkey in seen_mkeys or (number and number in seen_numbers):
                skipped += 1
                continue
            seen_mkeys.add(mkey)
            if number:
                seen_numbers.add(number)
            deduped.append(item)
        return deduped, skipped

    def _existing_case_keys(self, cases: list[NormalizedCase]) -> tuple[set[int], set[str]]:
        mkeys = [int(item.case.mkey) for item in cases if item.case.mkey is not None]
        numbers = [item.case.ntsb_number for item in cases if item.case.ntsb_number]
        if not mkeys and not numbers:
            return set(), set()
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select mkey, upper(ntsb_number)
                    from ntsb.cases
                    where mkey = any(%s) or upper(ntsb_number) = any(%s)
                    """,
                    (mkeys, [number.upper() for number in numbers]),
                )
                rows = cursor.fetchall()
                return (
                    {int(row[0]) for row in rows if row[0] is not None},
                    {str(row[1]) for row in rows if row[1]},
                )
        finally:
            if close_connection:
                connection.close()

    def _incremental_start(self, now: datetime) -> datetime:
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection.cursor() as cursor:
                cursor.execute("select last_successful_end from ntsb.sync_state where stream = 'incremental'")
                row = cursor.fetchone()
                if row and row[0]:
                    return row[0] - timedelta(days=self.config.overlap_days)
        finally:
            if close_connection:
                connection.close()
        return now - timedelta(days=self.config.overlap_days or 1)

    def _backfill_start(self) -> date:
        configured_start = date.fromisoformat(self.config.start_date)
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select status, last_successful_start, last_successful_end
                    from ntsb.sync_state
                    where stream = 'backfill'
                    """
                )
                row = cursor.fetchone()
                if not row:
                    return configured_start
                status, window_start, window_end = row
                if status == "failed" and window_start:
                    return max(configured_start, window_start.date())
                if window_end:
                    return max(configured_start, window_end.date() + timedelta(days=1))
                return configured_start
        finally:
            if close_connection:
                connection.close()

    def _start_run(self, stream: str) -> int:
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "insert into ntsb.sync_runs (stream) values (%s) returning run_id",
                        (stream,),
                    )
                    return int(cursor.fetchone()[0])
        finally:
            if close_connection:
                connection.close()

    def _finish_run(self, run_id: int, status: str, stats: SyncStats, error: str | None) -> None:
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        update ntsb.sync_runs set finished_at = now(), status = %s, pages = %s,
                            records_received = %s, cases_upserted = %s, details_fetched = %s,
                            skipped_existing = %s, rejected = %s, error = %s
                        where run_id = %s
                        """,
                        (
                            status,
                            stats.pages,
                            stats.records_received,
                            stats.cases_upserted,
                            stats.details_fetched,
                            stats.skipped_existing,
                            stats.rejected,
                            error,
                            run_id,
                        ),
                    )
        finally:
            if close_connection:
                connection.close()

    def _update_checkpoint(
        self,
        stream: str,
        window_start: str,
        window_end: str,
        marker_value: str | None,
        status: str,
        error: str | None,
    ) -> None:
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        insert into ntsb.sync_state (
                            stream, last_successful_start, last_successful_end, marker, status, error, updated_at
                        ) values (%s, %s, %s, %s, %s, %s, now())
                        on conflict (stream) do update set
                            last_successful_start = excluded.last_successful_start,
                            last_successful_end = excluded.last_successful_end,
                            marker = excluded.marker,
                            status = excluded.status,
                            error = excluded.error,
                            updated_at = now()
                        """,
                        (stream, window_start, window_end, marker_value, status, error),
                    )
        finally:
            if close_connection:
                connection.close()

    def _connect(self) -> Any:
        if self._connection is not None:
            return self._connection
        return psycopg2.connect(self.config.database_url, options="-c statement_timeout=60000")

    @staticmethod
    def _merge_stats(total: SyncStats, item: SyncStats) -> None:
        total.pages += item.pages
        total.records_received += item.records_received
        total.cases_upserted += item.cases_upserted
        total.details_fetched += item.details_fetched
        total.skipped_existing += item.skipped_existing
        total.rejected += item.rejected
