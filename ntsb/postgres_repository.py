"""PostgreSQL-backed NTSB case repository."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any

from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

from ntsb.domain import NTSBAircraft, NTSBCase, NTSBSearchQuery, NTSBSearchResult
from ntsb.sync.normalizer import country_code


load_dotenv()


class NTSBRepositoryError(RuntimeError):
    pass


class PostgresNTSBCaseRepository:
    def __init__(self, connection: Any | None = None, database_url: str | None = None):
        self._connection = connection
        self._database_url = database_url or os.getenv("DATABASE_URL", "")

    def _connect(self) -> Any:
        if self._connection is not None:
            return self._connection
        if not self._database_url or "<password>" in self._database_url or "YOUR-PASSWORD" in self._database_url:
            raise NTSBRepositoryError("DATABASE_URL is missing for the NTSB PostgreSQL index.")
        return psycopg2.connect(self._database_url, options="-c statement_timeout=10000")

    def search(self, query: NTSBSearchQuery) -> NTSBSearchResult:
        connection = self._connect()
        close_connection = self._connection is None
        try:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                where_sql, params = self._where(query)
                total_matches = self._count(cursor, where_sql, params)
                cases = [] if query.goal == "count" or query.intent == "count" else self._cases(cursor, where_sql, params, query)
                last_synced_at = self._last_synced_at(cursor)
        finally:
            if close_connection:
                connection.close()

        stale = self._is_stale(last_synced_at)
        warnings = []
        if stale:
            warnings.append("The local NTSB index is stale or has not completed a sync.")
        return NTSBSearchResult(
            cases=cases,
            query=query,
            total_matches=total_matches,
            limit=query.limit,
            snapshot_at=datetime.now(timezone.utc).isoformat(),
            last_synced_at=last_synced_at,
            stale=stale,
            warnings=warnings,
        )

    def _where(self, query: NTSBSearchQuery) -> tuple[str, list[Any]]:
        clauses = ["true"]
        params: list[Any] = []
        if query.ntsb_number:
            clauses.append("upper(c.ntsb_number) = upper(%s)")
            params.append(query.ntsb_number)
        if query.mkey is not None:
            clauses.append("c.mkey = %s")
            params.append(query.mkey)
        if query.start_date:
            clauses.append("c.event_date >= %s")
            params.append(query.start_date)
        if query.end_date:
            clauses.append("c.event_date <= %s")
            params.append(query.end_date)
        for column, expected in (
            ("c.state", query.state),
            ("c.event_type", query.event_type),
            ("c.investigation_status", query.investigation_status),
        ):
            if expected:
                clauses.append(f"{column} ilike %s")
                params.append(f"%{expected}%")
        if query.location:
            clauses.append("(c.location ilike %s or c.city ilike %s)")
            params.extend([f"%{query.location}%", f"%{query.location}%"])
        if query.country:
            code = country_code(query.country)
            if code:
                clauses.append("c.country_code = %s")
                params.append(code)
            else:
                clauses.append("c.country ilike %s")
                params.append(f"%{query.country}%")
        if query.severity:
            if "fatal" in query.severity.casefold():
                clauses.append("(c.severity ilike %s or coalesce(c.fatalities, 0) > 0)")
                params.append("%fatal%")
            else:
                clauses.append("c.severity ilike %s")
                params.append(f"%{query.severity}%")
        if query.registration:
            clauses.append(
                "exists (select 1 from ntsb.aircraft a where a.case_mkey = c.mkey and upper(a.registration) like upper(%s))"
            )
            params.append(f"%{query.registration}%")
        if query.make:
            clauses.append(
                "exists (select 1 from ntsb.aircraft a where a.case_mkey = c.mkey and a.make ilike %s)"
            )
            params.append(f"%{query.make}%")
        if query.model:
            clauses.append(
                "exists (select 1 from ntsb.aircraft a where a.case_mkey = c.mkey and a.model ilike %s)"
            )
            params.append(f"%{query.model}%")
        if query.text:
            clauses.append("c.search_tsv @@ plainto_tsquery('english', %s)")
            params.append(query.text)
        return " and ".join(clauses), params

    def _count(self, cursor: Any, where_sql: str, params: list[Any]) -> int:
        cursor.execute(f"select count(*) as count from ntsb.cases c where {where_sql}", params)
        return int(cursor.fetchone()["count"])

    def _cases(
        self,
        cursor: Any,
        where_sql: str,
        params: list[Any],
        query: NTSBSearchQuery,
    ) -> list[NTSBCase]:
        order_sql = self._order_sql(query)
        cursor.execute(
            f"""
            select
                c.*,
                dc.fetched_at as detail_fetched_at,
                coalesce((
                    select jsonb_agg(jsonb_build_object(
                        'aircraft_sequence', a.aircraft_sequence,
                        'make', a.make,
                        'model', a.model,
                        'registration', a.registration,
                        'category', a.category,
                        'operation', a.operation,
                        'damage', a.damage
                    ) order by a.aircraft_sequence)
                    from ntsb.aircraft a
                    where a.case_mkey = c.mkey
                ), '[]'::jsonb) as aircraft_rows,
                coalesce((
                    select array_agg(e.event_text order by e.event_sequence)
                    from ntsb.events e
                    where e.case_mkey = c.mkey
                ), array[]::text[]) as event_rows,
                coalesce((
                    select array_agg(f.finding_text order by f.finding_sequence)
                    from ntsb.findings f
                    where f.case_mkey = c.mkey
                ), array[]::text[]) as finding_rows
            from ntsb.cases c
            left join ntsb.detail_cache dc on dc.case_mkey = c.mkey
            where {where_sql}
            order by {order_sql}
            limit %s
            """,
            params + [query.limit],
        )
        return [self._row_to_case(row) for row in cursor.fetchall()]

    def _order_sql(self, query: NTSBSearchQuery) -> str:
        direction = "asc" if query.ranking_order == "asc" else "desc"
        nulls = "nulls first" if direction == "asc" else "nulls last"
        if query.goal == "rank" and query.ranking_field == "fatalities":
            return f"c.fatalities {direction} {nulls}, c.event_date desc nulls last, c.mkey"
        if query.goal == "rank" and query.ranking_field == "injuries":
            return f"c.total_injuries {direction} {nulls}, c.event_date desc nulls last, c.mkey"
        if query.goal == "rank" and query.ranking_field == "date":
            return f"c.event_date {direction} {nulls}, c.mkey"
        date_direction = "asc" if query.sort == "date_asc" else "desc"
        return f"c.event_date {date_direction} nulls last, c.mkey"

    def _last_synced_at(self, cursor: Any) -> str | None:
        cursor.execute(
            """
            select max(value) as last_synced_at
            from (
                select updated_at as value from ntsb.sync_state
                union all
                select synced_at as value from ntsb.cases
            ) source_values
            """
        )
        value = cursor.fetchone()["last_synced_at"]
        return value.isoformat() if value is not None else None

    def _is_stale(self, last_synced_at: str | None) -> bool:
        if not last_synced_at:
            return True
        try:
            max_minutes = int(os.getenv("NTSB_INDEX_MAX_STALENESS_MINUTES", "60"))
            synced = datetime.fromisoformat(last_synced_at.replace("Z", "+00:00"))
            if synced.tzinfo is None:
                synced = synced.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - synced).total_seconds() > max_minutes * 60
        except ValueError:
            return True

    def _row_to_case(self, row: dict[str, Any]) -> NTSBCase:
        aircraft_rows = row.get("aircraft_rows") or []
        aircraft = [NTSBAircraft(**dict(item)) for item in aircraft_rows]
        return NTSBCase(
            ntsb_number=row.get("ntsb_number"),
            mkey=row.get("mkey"),
            event_date=row["event_date"].isoformat() if row.get("event_date") else None,
            event_time=str(row["event_time"]) if row.get("event_time") else None,
            city=row.get("city"),
            location=row.get("location"),
            state=row.get("state"),
            country=row.get("country"),
            country_code=row.get("country_code"),
            event_type=row.get("event_type"),
            severity=row.get("severity"),
            investigation_status=row.get("investigation_status"),
            fatalities=row.get("fatalities"),
            serious_injuries=row.get("serious_injuries"),
            minor_injuries=row.get("minor_injuries"),
            total_injuries=row.get("total_injuries"),
            narrative=row.get("narrative"),
            probable_cause=row.get("probable_cause"),
            airport=row.get("airport"),
            runway=row.get("runway"),
            source_updated_at=row["source_updated_at"].isoformat() if row.get("source_updated_at") else None,
            synced_at=row["synced_at"].isoformat() if row.get("synced_at") else None,
            detail_fetched_at=row["detail_fetched_at"].isoformat() if row.get("detail_fetched_at") else None,
            aircraft_list=aircraft,
            events=list(row.get("event_rows") or []),
            findings=list(row.get("finding_rows") or []),
        )
