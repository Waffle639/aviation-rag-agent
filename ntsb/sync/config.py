"""Configuration for NTSB API synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import os

from dotenv import load_dotenv

from ntsb.sync.errors import NTSBConfigurationError


load_dotenv()


def _int_env(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError as exc:
        raise NTSBConfigurationError(f"{name} must be an integer") from exc


def _float_env(name: str, default: float, minimum: float = 0.1) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError as exc:
        raise NTSBConfigurationError(f"{name} must be numeric") from exc


@dataclass(frozen=True)
class NTSBSourceConfig:
    base_url: str
    api_key: str
    user_agent: str = "aviation-rag-agent/1.0"
    timeout_seconds: float = 60.0
    max_retries: int = 2
    max_concurrency: int = 5

    @classmethod
    def from_env(cls) -> "NTSBSourceConfig":
        api_key = os.getenv("NTSB_API_KEY", "").strip()
        if not api_key:
            raise NTSBConfigurationError(
                "NTSB_API_KEY is missing. Configure it only for the sync job."
            )
        return cls(
            base_url=os.getenv("NTSB_API_BASE", "https://api.ntsb.gov/public").strip().rstrip("/"),
            api_key=api_key,
            user_agent=os.getenv("NTSB_API_USER_AGENT", "aviation-rag-agent/1.0").strip(),
            timeout_seconds=_float_env("NTSB_API_TIMEOUT_SECONDS", 60.0),
            max_retries=_int_env("NTSB_API_MAX_RETRIES", 2, minimum=0),
            max_concurrency=_int_env("NTSB_SYNC_MAX_CONCURRENCY", 5),
        )


@dataclass(frozen=True)
class NTSBSyncConfig:
    database_url: str
    start_date: str
    window_days: int = 90
    overlap_days: int = 7
    batch_size: int = 500
    detail_cache_ttl_minutes: int = 1440

    @classmethod
    def from_env(cls) -> "NTSBSyncConfig":
        database_url = os.getenv("NTSB_SYNC_DATABASE_URL") or os.getenv("DATABASE_URL", "")
        if not database_url or "<password>" in database_url or "YOUR-PASSWORD" in database_url:
            raise NTSBConfigurationError("DATABASE_URL or NTSB_SYNC_DATABASE_URL is missing.")
        start_date = os.getenv("NTSB_SYNC_START_DATE", "1962-01-01").strip()
        try:
            date.fromisoformat(start_date)
        except ValueError as exc:
            raise NTSBConfigurationError("NTSB_SYNC_START_DATE must use YYYY-MM-DD format") from exc
        return cls(
            database_url=database_url,
            start_date=start_date,
            window_days=_int_env("NTSB_SYNC_WINDOW_DAYS", 90),
            overlap_days=_int_env("NTSB_SYNC_OVERLAP_DAYS", 7, minimum=0),
            batch_size=_int_env("NTSB_SYNC_BATCH_SIZE", 500),
            detail_cache_ttl_minutes=_int_env("NTSB_DETAIL_CACHE_TTL_MINUTES", 1440),
        )
