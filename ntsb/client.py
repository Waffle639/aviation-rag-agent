"""HTTP client for the NTSB public API."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
import requests
from dotenv import load_dotenv
from langsmith import traceable

load_dotenv()

logger = logging.getLogger(__name__)


def _trace_http_inputs(inputs: Any) -> dict[str, Any]:
    """Keep API keys and client internals out of LangSmith inputs."""
    if not isinstance(inputs, dict):
        return {}
    return {
        "endpoint": inputs.get("path"),
        "params": inputs.get("params"),
    }


def _trace_http_output(output: Any) -> dict[str, Any]:
    """Trace response shape, not the potentially large accident payload."""
    if output is None:
        return {"status": "empty"}
    if isinstance(output, list):
        return {"type": "list", "records": len(output)}
    if isinstance(output, dict):
        records = 0
        for key in ("data", "items", "records", "results", "cases", "aviationCases"):
            value = output.get(key)
            if isinstance(value, list):
                records = len(value)
                break
        return {
            "type": "object",
            "keys": list(output.keys())[:30],
            "records": records,
            "has_marker": any(output.get(key) for key in ("marker", "nextMarker", "continuationMarker")),
        }
    return {"type": type(output).__name__}


class NTSBError(RuntimeError):
    """Base error for controlled NTSB failures."""


class NTSBConfigurationError(NTSBError):
    pass


class NTSBAPIError(NTSBError):
    pass


class NTSBAuthenticationError(NTSBAPIError):
    """The gateway rejected the subscription key or its API subscription."""


class NTSBResponseError(NTSBError):
    pass


@dataclass(frozen=True)
class NTSBConfig:
    base_url: str
    api_key: str
    timeout_seconds: float = 20.0
    max_retries: int = 2
    max_pages: int = 20
    max_records: int = 5000
    max_windows: int = 6
    max_hydration: int = 100
    search_window_days: int = 90
    max_concurrency: int = 5

    @classmethod
    def from_env(cls) -> "NTSBConfig":
        api_key = os.getenv("NTSB_API_KEY", "").strip()
        if not api_key:
            raise NTSBConfigurationError(
                "NTSB_API_KEY is missing. Add the NTSB subscription key to .env."
            )
        base_url = os.getenv("NTSB_API_BASE", "https://api.ntsb.gov/public").strip().rstrip("/")
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=float(os.getenv("NTSB_API_TIMEOUT_SECONDS", "20")),
            max_retries=max(0, int(os.getenv("NTSB_API_MAX_RETRIES", "2"))),
            max_pages=max(1, int(os.getenv("NTSB_API_MAX_PAGES", "20"))),
            max_records=max(1, int(os.getenv("NTSB_API_MAX_RECORDS", "5000"))),
            max_windows=max(1, int(os.getenv("NTSB_API_MAX_WINDOWS", "6"))),
            max_hydration=max(1, int(os.getenv("NTSB_API_MAX_HYDRATION", "100"))),
            search_window_days=max(1, int(os.getenv("NTSB_API_SEARCH_WINDOW_DAYS", "90"))),
            max_concurrency=max(1, int(os.getenv("NTSB_API_MAX_CONCURRENCY", "5"))),
        )


class NTSBClient:
    """NTSB client with synchronous and bounded asynchronous request paths."""

    def __init__(
        self,
        config: NTSBConfig | None = None,
        session: Any | None = None,
        async_session: httpx.AsyncClient | None = None,
    ):
        self.config = config or NTSBConfig.from_env()
        self.session = session or requests.Session()
        self._async_session = async_session
        # Injected synchronous sessions are used by the unit tests and legacy callers.
        # Production clients use httpx natively for async hydration.
        self._use_async_http = session is None or async_session is not None

    @traceable(
        run_type="tool",
        name="ntsb_http_request",
        process_inputs=_trace_http_inputs,
        process_outputs=_trace_http_output,
    )
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.config.base_url}/{path.lstrip('/')}"
        safe_params = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        headers = {
            "Accept": "application/json",
            "Ocp-Apim-Subscription-Key": self.config.api_key,
            # The NTSB gateway rejects requests using requests' default
            # ``python-requests`` user agent, while curl/browser calls work.
            "User-Agent": os.getenv("NTSB_API_USER_AGENT", "aviation-rag-agent/1.0"),
        }
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            request_started = time.perf_counter()
            try:
                logger.info(
                    "NTSB request endpoint=%s params=%s attempt=%d",
                    url,
                    safe_params,
                    attempt + 1,
                )
                response = self.session.get(
                    url,
                    params=safe_params,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                elapsed_ms = (time.perf_counter() - request_started) * 1000
                logger.info(
                    "NTSB GET %s status=%s attempt=%d elapsed_ms=%.0f",
                    path,
                    response.status_code,
                    attempt + 1,
                    elapsed_ms,
                )
                if response.status_code in {429, 502, 503, 504} and attempt < self.config.max_retries:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = float(retry_after) if retry_after.replace(".", "", 1).isdigit() else 2**attempt
                    logger.warning(
                        "Retrying NTSB endpoint %s after HTTP %s in %.1fs.",
                        path,
                        response.status_code,
                        min(delay, 8),
                    )
                    time.sleep(min(delay, 8))
                    continue
                if response.status_code == 204:
                    return None
                if response.status_code in {401, 403}:
                    raise NTSBAuthenticationError(
                        "NTSB rejected NTSB_API_KEY (HTTP "
                        f"{response.status_code}). Copy the Primary or Secondary "
                        "subscription key for the Public API product from the NTSB portal."
                    )
                if response.status_code >= 400:
                    raise NTSBAPIError(f"NTSB returned HTTP {response.status_code} for {path}.")
                try:
                    return response.json()
                except ValueError as exc:
                    raise NTSBResponseError(f"NTSB returned non-JSON data for {path}.") from exc
            except requests.RequestException as exc:
                last_error = exc
                elapsed_ms = (time.perf_counter() - request_started) * 1000
                logger.warning(
                    "NTSB GET %s failed on attempt=%d elapsed_ms=%.0f: %s",
                    path,
                    attempt + 1,
                    elapsed_ms,
                    exc,
                )
                if attempt >= self.config.max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise NTSBAPIError(f"NTSB request failed for {path}.") from last_error

    @asynccontextmanager
    async def async_session(self):
        """Yield one reusable async connection pool for a batch of requests."""
        if self._async_session is not None:
            yield self._async_session
            return
        if not self._use_async_http:
            yield None
            return
        limits = httpx.Limits(
            max_connections=self.config.max_concurrency,
            max_keepalive_connections=self.config.max_concurrency,
        )
        async with httpx.AsyncClient(limits=limits) as session:
            yield session

    async def _aget(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        """Async equivalent of ``_get`` with the same retry/error policy."""
        if not self._use_async_http:
            return await asyncio.to_thread(self._get, path, params)
        if session is None:
            async with self.async_session() as managed_session:
                return await self._aget(path, params, session=managed_session)

        url = f"{self.config.base_url}/{path.lstrip('/')}"
        safe_params = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        headers = {
            "Accept": "application/json",
            "Ocp-Apim-Subscription-Key": self.config.api_key,
            "User-Agent": os.getenv("NTSB_API_USER_AGENT", "aviation-rag-agent/1.0"),
        }
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            request_started = time.perf_counter()
            try:
                logger.info(
                    "NTSB async request endpoint=%s params=%s attempt=%d",
                    url,
                    safe_params,
                    attempt + 1,
                )
                response = await session.get(
                    url,
                    params=safe_params,
                    headers=headers,
                    timeout=self.config.timeout_seconds,
                )
                elapsed_ms = (time.perf_counter() - request_started) * 1000
                logger.info(
                    "NTSB async GET %s status=%s attempt=%d elapsed_ms=%.0f",
                    path,
                    response.status_code,
                    attempt + 1,
                    elapsed_ms,
                )
                if response.status_code in {429, 502, 503, 504} and attempt < self.config.max_retries:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = (
                        float(retry_after)
                        if retry_after.replace(".", "", 1).isdigit()
                        else 2**attempt
                    )
                    logger.warning(
                        "Retrying NTSB async endpoint %s after HTTP %s in %.1fs.",
                        path,
                        response.status_code,
                        min(delay, 8),
                    )
                    await asyncio.sleep(min(delay, 8))
                    continue
                if response.status_code == 204:
                    return None
                if response.status_code in {401, 403}:
                    raise NTSBAuthenticationError(
                        "NTSB rejected NTSB_API_KEY (HTTP "
                        f"{response.status_code}). Copy the Primary or Secondary "
                        "subscription key for the Public API product from the NTSB portal."
                    )
                if response.status_code >= 400:
                    raise NTSBAPIError(f"NTSB returned HTTP {response.status_code} for {path}.")
                try:
                    return response.json()
                except ValueError as exc:
                    raise NTSBResponseError(f"NTSB returned non-JSON data for {path}.") from exc
            except httpx.RequestError as exc:
                last_error = exc
                elapsed_ms = (time.perf_counter() - request_started) * 1000
                logger.warning(
                    "NTSB async GET %s failed on attempt=%d elapsed_ms=%.0f: %s",
                    path,
                    attempt + 1,
                    elapsed_ms,
                    exc,
                )
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2**attempt, 8))
        raise NTSBAPIError(f"NTSB request failed for {path}.") from last_error

    def get_version(self) -> Any:
        return self._get("/api/getversion")

    async def get_version_async(self, *, session: httpx.AsyncClient | None = None) -> Any:
        return await self._aget("/api/getversion", session=session)

    def get_aviation_dictionary(self) -> Any:
        return self._get("/api/Aviation/v1/GetAviationDataDictionary")

    async def get_aviation_dictionary_async(
        self, *, session: httpx.AsyncClient | None = None
    ) -> Any:
        return await self._aget(
            "/api/Aviation/v1/GetAviationDataDictionary", session=session
        )

    def get_aviation_case(self, *, ntsb_number: str | None = None, mkey: int | str | None = None) -> Any:
        if not ntsb_number and mkey is None:
            raise ValueError("ntsb_number or mkey is required")
        return self._get(
            "/api/Aviation/v1/GetAviationCase/",
            {"ntsbNumber": ntsb_number, "mkey": mkey},
        )

    async def get_aviation_case_async(
        self,
        *,
        ntsb_number: str | None = None,
        mkey: int | str | None = None,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        if not ntsb_number and mkey is None:
            raise ValueError("ntsb_number or mkey is required")
        return await self._aget(
            "/api/Aviation/v1/GetAviationCase/",
            {"ntsbNumber": ntsb_number, "mkey": mkey},
            session=session,
        )

    def get_cases_by_registration(self, registration: str) -> Any:
        return self._get(
            "/api/Aviation/v1/GetAviationCasesFiltered/",
            {"aircraftRegistrationNumber": registration},
        )

    async def get_cases_by_registration_async(
        self, registration: str, *, session: httpx.AsyncClient | None = None
    ) -> Any:
        return await self._aget(
            "/api/Aviation/v1/GetAviationCasesFiltered/",
            {"aircraftRegistrationNumber": registration},
            session=session,
        )

    def get_cases_by_date_range(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        marker: str | None = None,
    ) -> Any:
        return self._get(
            "/api/Common/v2/GetCasesByDateRange/",
            {"startDate": start_date, "endDate": end_date, "mode": "aviation", "marker": marker},
        )

    async def get_cases_by_date_range_async(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        marker: str | None = None,
        session: httpx.AsyncClient | None = None,
    ) -> Any:
        return await self._aget(
            "/api/Common/v2/GetCasesByDateRange/",
            {"startDate": start_date, "endDate": end_date, "mode": "aviation", "marker": marker},
            session=session,
        )
