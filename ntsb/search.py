"""Compatibility layer for the local NTSB PostgreSQL index."""

from __future__ import annotations

from ntsb.context import context_items_from_result
from ntsb.domain import NTSBSearchQuery, NTSBSearchResult
from ntsb.postgres_repository import PostgresNTSBCaseRepository


class NTSBSearchService(PostgresNTSBCaseRepository):
    """Deprecated name kept for callers while queries now use PostgreSQL only."""


def context_from_result(result: NTSBSearchResult) -> list[dict]:
    return context_items_from_result(result)


__all__ = ["NTSBSearchService", "NTSBSearchQuery", "NTSBSearchResult", "context_from_result"]
