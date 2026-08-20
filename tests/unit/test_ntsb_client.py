import asyncio

import pytest

from ntsb.client import NTSBAuthenticationError, NTSBClient, NTSBConfig, NTSBConfigurationError


class Response:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"ok": True}
        self.headers = headers or {}

    def json(self):
        return self._payload


class AsyncSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def config(**overrides):
    values = {
        "base_url": "https://example.test",
        "api_key": "secret",
        "user_agent": "tests/1.0",
        "timeout_seconds": 1,
        "max_retries": 0,
        "max_concurrency": 2,
    }
    values.update(overrides)
    return NTSBConfig(**values)


def test_async_client_sends_headers_and_date_range_params():
    session = AsyncSession(Response(payload={"records": []}))
    client = NTSBClient(config(), async_session=session)

    async def run():
        return await client.get_cases_by_date_range(
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

    result = asyncio.run(run())

    assert result == {"records": []}
    url, kwargs = session.calls[0]
    assert url == "https://example.test/api/Common/v2/GetCasesByDateRange/"
    assert kwargs["params"] == {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
        "mode": "aviation",
    }
    assert kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "secret"
    assert kwargs["headers"]["User-Agent"] == "tests/1.0"


def test_async_client_raises_authentication_error():
    session = AsyncSession(Response(status_code=403))
    client = NTSBClient(config(), async_session=session)

    with pytest.raises(NTSBAuthenticationError):
        asyncio.run(client.get("/api/getversion"))


def test_config_from_env_requires_api_key(monkeypatch):
    monkeypatch.delenv("NTSB_API_KEY", raising=False)

    with pytest.raises(NTSBConfigurationError):
        NTSBConfig.from_env()


def test_config_from_env_reads_sync_concurrency(monkeypatch):
    monkeypatch.setenv("NTSB_API_KEY", "key")
    monkeypatch.setenv("NTSB_API_BASE", "https://example.test/")
    monkeypatch.setenv("NTSB_SYNC_MAX_CONCURRENCY", "4")

    result = NTSBConfig.from_env()

    assert result.base_url == "https://example.test"
    assert result.max_concurrency == 4
