from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ntsb.client import (
    NTSBAPIError,
    NTSBAuthenticationError,
    NTSBConfig,
    NTSBConfigurationError,
    NTSBClient,
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
