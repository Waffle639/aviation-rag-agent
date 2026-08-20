"""Controlled errors for NTSB synchronization."""


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
