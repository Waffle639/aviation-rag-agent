"""Compatibility imports for the NTSB synchronization HTTP client."""

from ntsb.sync.api_client import NTSBAPIClient as NTSBClient
from ntsb.sync.config import NTSBSourceConfig as NTSBConfig
from ntsb.sync.errors import (
    NTSBAPIError,
    NTSBAuthenticationError,
    NTSBConfigurationError,
    NTSBError,
    NTSBResponseError,
)

__all__ = [
    "NTSBAPIError",
    "NTSBAuthenticationError",
    "NTSBClient",
    "NTSBConfig",
    "NTSBConfigurationError",
    "NTSBError",
    "NTSBResponseError",
]
