"""Async HTTP client used only by the NTSB sync process."""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from email.utils import parsedate_to_datetime
import logging
import time
from typing import Any

import httpx

from ntsb.sync.config import NTSBSourceConfig
from ntsb.sync.errors import NTSBAPIError, NTSBAuthenticationError, NTSBResponseError

logger = logging.getLogger(__name__)


def _retry_delay(retry_after: str, attempt: int) -> float:
    if retry_after.replace(".", "", 1).isdigit():
        return min(float(retry_after), 30.0)
    try:
        delay = parsedate_to_datetime(retry_after).timestamp() - time.time()
        return min(max(delay, 0.0), 30.0)
    except (TypeError, ValueError, OverflowError):
        return min(2**attempt, 30.0)


class NTSBAPIClient:
    def __init__(self, config: NTSBSourceConfig | None = None, async_session: httpx.AsyncClient | None = None):
        self.config = config or NTSBSourceConfig.from_env()
        self._async_session = async_session

    @asynccontextmanager
    async def async_session(self):
        if self._async_session is not None:
            yield self._async_session
            return
        limits = httpx.Limits(
            max_connections=self.config.max_concurrency,
            max_keepalive_connections=self.config.max_concurrency,
        )
        async with httpx.AsyncClient(limits=limits) as session:
            yield session

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        if session is None:
            async with self.async_session() as managed_session:
                return await self.get(path, params, session=managed_session)

        url = f"{self.config.base_url}/{path.lstrip('/')}"
        safe_params = {key: value for key, value in (params or {}).items() if value is not None}
        headers = {
            "Accept": "application/json",
            "Ocp-Apim-Subscription-Key": self.config.api_key,
            "User-Agent": self.config.user_agent,
        }
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            started_at = time.perf_counter()
            try:
                response = await session.get(
                    url,
                    params=safe_params,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                logger.info(
                    "NTSB sync GET %s status=%s attempt=%d elapsed_ms=%.0f",
                    path,
                    response.status_code,
                    attempt + 1,
                    elapsed_ms,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.config.max_retries:
                    await asyncio.sleep(_retry_delay(response.headers.get("Retry-After", ""), attempt))
                    continue
                if response.status_code == 204:
                    return None
                if response.status_code in {401, 403}:
                    raise NTSBAuthenticationError(
                        f"NTSB rejected NTSB_API_KEY with HTTP {response.status_code}."
                    )
                if response.status_code >= 400:
                    raise NTSBAPIError(f"NTSB returned HTTP {response.status_code} for {path}.")
                try:
                    return response.json()
                except ValueError as exc:
                    raise NTSBResponseError(f"NTSB returned non-JSON data for {path}.") from exc
            except httpx.RequestError as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2**attempt, 30.0))
        raise NTSBAPIError(f"NTSB request failed for {path}.") from last_error

    async def get_aviation_case(
        self,
        *,
        ntsb_number: str | None = None,
        mkey: int | str | None = None,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        if not ntsb_number and mkey is None:
            raise ValueError("ntsb_number or mkey is required")
        return await self.get(
            "/api/Aviation/v1/GetAviationCase/",
            {"ntsbNumber": ntsb_number, "mkey": mkey},
            session=session,
        )

    async def get_cases_by_registration(
        self, registration: str, *, session: httpx.AsyncClient | None = None
    ) -> Any:
        return await self.get(
            "/api/Aviation/v1/GetAviationCasesFiltered/",
            {"aircraftRegistrationNumber": registration},
            session=session,
        )

    async def get_cases_by_date_range(
        self,
        *,
        start_date: str,
        end_date: str,
        marker: str | None = None,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        return await self.get(
            "/api/Common/v2/GetCasesByDateRange/",
            {"startDate": start_date, "endDate": end_date, "mode": "aviation", "marker": marker},
            session=session,
        )

    async def get_cases_by_modified_date_range(
        self,
        *,
        start_date: str,
        end_date: str,
        marker: str | None = None,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        return await self.get(
            "/api/Common/v1/GetCasesByModifiedDateRange/",
            {"startDate": start_date, "endDate": end_date, "mode": "aviation", "marker": marker},
            session=session,
        )
