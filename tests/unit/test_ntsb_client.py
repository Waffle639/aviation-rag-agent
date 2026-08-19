import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, call

import httpx
import pytest
import requests

from ntsb.client import (
    NTSBAPIError,
    NTSBAuthenticationError,
    NTSBConfig,
    NTSBConfigurationError,
    NTSBClient,
    NTSBResponseError,
    _trace_http_inputs,
    _trace_http_output,
)


def response(status=200, payload=None, headers=None):
    result = Mock()
    result.status_code = status
    result.headers = headers or {}
    result.json.return_value = payload
    return result


def config(**kwargs):
    values = {
        "base_url": "https://api.ntsb.gov/public",
        "api_key": "secret",
        "max_retries": 0,
    }
    values.update(kwargs)
    return NTSBConfig(**values)


def test_date_range_sends_documented_parameters_and_header():
    session = Mock()
    session.get.return_value = response(payload={"items": []})
    client = NTSBClient(config(), session)

    client.get_cases_by_date_range(
        start_date="2024-01-01", end_date="2024-01-31", marker="next"
    )

    kwargs = session.get.call_args.kwargs
    assert kwargs["params"] == {
        "startDate": "2024-01-01",
        "endDate": "2024-01-31",
        "mode": "aviation",
        "marker": "next",
    }
    assert kwargs["headers"]["Ocp-Apim-Subscription-Key"] == "secret"
    assert kwargs["headers"]["User-Agent"] == "aviation-rag-agent/1.0"
    assert kwargs["timeout"] == 20.0


def test_endpoint_status_and_latency_are_logged(caplog):
    session = Mock()
    session.get.return_value = response(payload={"items": []})
    client = NTSBClient(config(), session)

    with caplog.at_level("INFO", logger="ntsb.client"):
        client.get_cases_by_date_range(start_date="2024-01-01", end_date="2024-01-31")

    assert any(
        "NTSB GET /api/Common/v2/GetCasesByDateRange/ status=200" in record.message
        and "elapsed_ms=" in record.message
        for record in caplog.records
    )


def test_empty_response_is_returned_as_none():
    session = Mock()
    session.get.return_value = response(status=204)
    assert NTSBClient(config(), session).get_version() is None


def test_api_error_is_controlled():
    session = Mock()
    session.get.return_value = response(status=403)
    with pytest.raises(NTSBAPIError, match="HTTP 403"):
        NTSBClient(config(), session).get_version()


def test_authentication_error_explains_subscription_key():
    session = Mock()
    session.get.return_value = response(status=403)
    with pytest.raises(NTSBAuthenticationError, match="subscription key"):
        NTSBClient(config(), session).get_version()


def test_retry_after_is_respected(monkeypatch):
    session = Mock()
    session.get.side_effect = [
        response(status=429, headers={"Retry-After": "0"}),
        response(payload={"ok": True}),
    ]
    sleep = Mock()
    monkeypatch.setattr("ntsb.client.time.sleep", sleep)

    result = NTSBClient(config(max_retries=1), session).get_version()

    assert result == {"ok": True}
    sleep.assert_called_once_with(0.0)


def test_missing_key_is_rejected(monkeypatch):
    monkeypatch.delenv("NTSB_API_KEY", raising=False)
    with pytest.raises(NTSBConfigurationError):
        NTSBConfig.from_env()


def test_async_client_uses_httpx_and_preserves_request_contract():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        return httpx.Response(200, json={"ok": True})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
            return await NTSBClient(config(), async_session=session).get_version_async()

    assert asyncio.run(run()) == {"ok": True}
    assert captured["url"] == "https://api.ntsb.gov/public/api/getversion"
    assert captured["headers"]["ocp-apim-subscription-key"] == "secret"


def test_async_retry_after_is_respected(monkeypatch):
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("ntsb.client.asyncio.sleep", no_sleep)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
            return await NTSBClient(config(max_retries=1), async_session=session).get_version_async()

    assert asyncio.run(run()) == {"ok": True}
    assert calls == 2


def test_non_json_success_response_is_a_controlled_response_error():
    session = Mock()
    invalid = response(payload=None)
    invalid.json.side_effect = ValueError("not json")
    session.get.return_value = invalid

    with pytest.raises(NTSBResponseError, match="non-JSON"):
        NTSBClient(config(), session).get_version()


def test_transport_error_retries_then_exposes_api_error(monkeypatch):
    session = Mock()
    session.get.side_effect = requests.Timeout("timed out")
    sleep = Mock()
    monkeypatch.setattr("ntsb.client.time.sleep", sleep)

    with pytest.raises(NTSBAPIError, match="request failed"):
        NTSBClient(config(max_retries=2), session).get_version()

    assert session.get.call_count == 3
    assert sleep.call_args_list == [call(1), call(2)]


@pytest.mark.parametrize("status", [401, 403])
def test_both_authentication_statuses_are_classified(status):
    session = Mock()
    session.get.return_value = response(status=status)

    with pytest.raises(NTSBAuthenticationError, match="NTSB_API_KEY"):
        NTSBClient(config(), session).get_version()


def test_non_retryable_http_error_is_not_retried():
    session = Mock()
    session.get.return_value = response(status=500)

    with pytest.raises(NTSBAPIError, match="HTTP 500"):
        NTSBClient(config(max_retries=3), session).get_version()

    session.get.assert_called_once()


def test_case_requires_at_least_one_identifier():
    client = NTSBClient(config(), Mock())

    with pytest.raises(ValueError, match="required"):
        client.get_aviation_case()


def test_configuration_reads_and_normalizes_all_limits(monkeypatch):
    monkeypatch.setenv("NTSB_API_KEY", " key ")
    monkeypatch.setenv("NTSB_API_BASE", "https://example.test/ ")
    monkeypatch.setenv("NTSB_API_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("NTSB_API_MAX_RETRIES", "-2")
    monkeypatch.setenv("NTSB_API_MAX_PAGES", "0")
    monkeypatch.setenv("NTSB_API_MAX_RECORDS", "0")
    monkeypatch.setenv("NTSB_API_MAX_WINDOWS", "0")
    monkeypatch.setenv("NTSB_API_MAX_HYDRATION", "0")
    monkeypatch.setenv("NTSB_API_SEARCH_WINDOW_DAYS", "0")
    monkeypatch.setenv("NTSB_API_MAX_CONCURRENCY", "0")

    config_from_env = NTSBConfig.from_env()

    assert config_from_env.base_url == "https://example.test"
    assert config_from_env.api_key == "key"
    assert config_from_env.timeout_seconds == 3.5
    assert config_from_env.max_retries == 0
    assert config_from_env.max_pages == 1
    assert config_from_env.max_records == 1
    assert config_from_env.max_windows == 1
    assert config_from_env.max_hydration == 1
    assert config_from_env.search_window_days == 1
    assert config_from_env.max_concurrency == 1


def test_async_non_json_and_auth_errors_match_sync_policy():
    async def run(response_to_return):
        def handler(_request):
            return response_to_return

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
            return await NTSBClient(config(), async_session=session).get_version_async()

    with pytest.raises(NTSBAuthenticationError):
        asyncio.run(run(httpx.Response(401)))

    with pytest.raises(NTSBResponseError, match="non-JSON"):
        asyncio.run(run(httpx.Response(200, content=b"not-json")))


def test_async_transport_error_retries_and_preserves_cause(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection failed", request=request)

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr("ntsb.client.asyncio.sleep", no_sleep)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
            return await NTSBClient(config(max_retries=1), async_session=session).get_version_async()

    with pytest.raises(NTSBAPIError, match="request failed"):
        asyncio.run(run())
    assert calls == 2


def test_async_case_validates_identifier_before_network_call():
    async def run():
        return await NTSBClient(config(), async_session=Mock()).get_aviation_case_async()

    with pytest.raises(ValueError, match="required"):
        asyncio.run(run())


def test_trace_helpers_exclude_secrets_and_payload_contents():
    assert _trace_http_inputs(None) == {}
    assert _trace_http_inputs(
        {"path": "/cases", "params": {"safe": 1}, "api_key": "secret"}
    ) == {"endpoint": "/cases", "params": {"safe": 1}}
    assert _trace_http_output(None) == {"status": "empty"}
    assert _trace_http_output([{"secret": "payload"}]) == {
        "type": "list",
        "records": 1,
    }
    output = _trace_http_output(
        {"items": [1], "marker": "next", "secret": "hidden"}
    )
    assert output["records"] == 1
    assert output["has_marker"] is True
    assert "secret" in output["keys"]
    assert _trace_http_output("text") == {"type": "str"}


def test_async_session_creates_reusable_httpx_pool_for_production_client():
    async def run():
        client = NTSBClient(config())
        async with client.async_session() as session:
            assert isinstance(session, httpx.AsyncClient)
            assert session.is_closed is False
        assert session.is_closed is True

    asyncio.run(run())


def test_sync_dictionary_endpoint_uses_documented_path():
    session = Mock()
    session.get.return_value = response(payload={"fields": []})
    client = NTSBClient(config(), session)

    assert client.get_aviation_dictionary() == {"fields": []}
    assert session.get.call_args.args[0].endswith(
        "/api/Aviation/v1/GetAviationDataDictionary"
    )


def test_async_no_content_returns_none():
    async def run():
        def handler(_request):
            return httpx.Response(204)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as session:
            return await NTSBClient(config(), async_session=session).get_version_async()

    assert asyncio.run(run()) is None
