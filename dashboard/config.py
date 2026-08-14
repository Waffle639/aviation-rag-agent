"""Configuration helpers for the evaluation dashboard."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


APP_TITLE = "Aviation RAG Evaluations"
APP_SUBTITLE = "Evaluation Control Center"


@dataclass(frozen=True)
class DashboardConfig:
    database_url: str
    pool_minconn: int = 1
    pool_maxconn: int = 4
    connect_timeout_seconds: int = 8
    statement_timeout_ms: int = 8000
    require_ssl: bool = True


def _secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    try:
        import streamlit as st
    except Exception:
        return None

    try:
        secret_value = st.secrets.get(name)
    except Exception:
        return None
    return str(secret_value) if secret_value else None


def _int_secret(name: str, default: int) -> int:
    value = _secret(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _with_sslmode(database_url: str) -> str:
    if "sslmode=" in database_url.lower():
        return database_url
    separator = "&" if "?" in database_url else "?"
    return f"{database_url}{separator}sslmode=require"


def load_config() -> DashboardConfig:
    load_dotenv()

    database_url = _secret("DATABASE_URL")
    if not database_url or "YOUR-PASSWORD" in database_url:
        raise RuntimeError(
            "DATABASE_URL is required for the dashboard. Configure it as an "
            "environment variable or Streamlit secret."
        )

    require_ssl = (_secret("DASHBOARD_REQUIRE_SSL") or "true").lower() != "false"
    if require_ssl:
        database_url = _with_sslmode(database_url)

    return DashboardConfig(
        database_url=database_url,
        pool_minconn=_int_secret("DASHBOARD_DB_POOL_MIN", 1),
        pool_maxconn=_int_secret("DASHBOARD_DB_POOL_MAX", 4),
        connect_timeout_seconds=_int_secret("DASHBOARD_DB_CONNECT_TIMEOUT", 8),
        statement_timeout_ms=_int_secret("DASHBOARD_DB_STATEMENT_TIMEOUT_MS", 8000),
        require_ssl=require_ssl,
    )
