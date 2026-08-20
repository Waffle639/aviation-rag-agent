"""Repository contract for the local NTSB index."""

from __future__ import annotations

from typing import Protocol

from ntsb.domain import NTSBSearchQuery, NTSBSearchResult


class NTSBRepository(Protocol):
    def search(self, query: NTSBSearchQuery) -> NTSBSearchResult:
        """Return cases from the local NTSB index."""
