import asyncio

from ntsb.domain import NTSBCase, NTSBSearchQuery
from ntsb.enrichment import _fetch_details, enrich_selected_cases, requires_selected_detail_refresh
from ntsb.sync.errors import NTSBAPIError


def test_selected_detail_refresh_only_for_missing_requested_detail():
    query = NTSBSearchQuery(requested_fields=["probable_cause"])

    assert requires_selected_detail_refresh(NTSBCase(mkey=1), query) is True
    assert requires_selected_detail_refresh(NTSBCase(mkey=1, narrative="Summary"), query) is True
    assert requires_selected_detail_refresh(NTSBCase(mkey=1, probable_cause="Known"), query) is False
    assert requires_selected_detail_refresh(NTSBCase(mkey=1, detail_fetched_at="2026-08-20T00:00:00+00:00"), query) is False
    assert requires_selected_detail_refresh(
        NTSBCase(mkey=1, detail_fetched_at="2026-08-20T00:00:00+00:00"),
        NTSBSearchQuery(needs_detail=True),
    ) is True
    assert requires_selected_detail_refresh(NTSBCase(mkey=1), NTSBSearchQuery(requested_fields=["date"])) is False


def test_enrichment_skips_when_api_key_is_missing(monkeypatch):
    monkeypatch.delenv("NTSB_API_KEY", raising=False)
    case = NTSBCase(mkey=1)

    cases, warnings = enrich_selected_cases([case], NTSBSearchQuery(requested_fields=["probable_cause"]))

    assert cases == [case]
    assert "NTSB_API_KEY" in warnings[0]


def test_enrichment_replaces_selected_cases(monkeypatch):
    original = NTSBCase(mkey=1, ntsb_number="A1", event_date="2026-08-20")
    enriched = NTSBCase(mkey=1, probable_cause="Known")

    async def fetch_details(cases):
        return {1: enriched}

    monkeypatch.setenv("NTSB_API_KEY", "key")
    monkeypatch.setattr("ntsb.enrichment._fetch_details", fetch_details)

    cases, warnings = enrich_selected_cases([original], NTSBSearchQuery(requested_fields=["probable_cause"]))

    assert cases[0].ntsb_number == "A1"
    assert cases[0].event_date == "2026-08-20"
    assert cases[0].probable_cause == "Known"
    assert warnings == []


def test_enrichment_reports_controlled_detail_errors(monkeypatch):
    async def fetch_details(cases):
        raise NTSBAPIError("bad gateway")

    monkeypatch.setenv("NTSB_API_KEY", "key")
    monkeypatch.setattr("ntsb.enrichment._fetch_details", fetch_details)

    cases, warnings = enrich_selected_cases([NTSBCase(mkey=1)], NTSBSearchQuery(requested_fields=["findings"]))

    assert len(cases) == 1
    assert warnings == ["NTSB detail enrichment failed: bad gateway"]


def test_fetch_details_uses_sync_service_without_network(monkeypatch):
    class AsyncSessionManager:
        async def __aenter__(self):
            return "session"

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class APIClient:
        def async_session(self):
            return AsyncSessionManager()

    class Service:
        api_client = APIClient()

        async def sync_case_detail(self, *, ntsb_number=None, mkey=None, session=None):
            assert ntsb_number == "A1"
            assert mkey == 1
            assert session == "session"
            return type(
                "Normalized",
                (),
                {
                    "case": NTSBCase(mkey=1, ntsb_number="A1", probable_cause="Known"),
                    "raw": {
                        "mkey": 1,
                        "ntsbNumber": "A1",
                        "probableCause": "Known",
                        "aircrafts": [{"aircraftMake": "Cessna", "aircraftModel": "172"}],
                    },
                },
            )()

    monkeypatch.setattr("ntsb.enrichment.NTSBSyncService", Service)

    result = asyncio.run(_fetch_details([NTSBCase(mkey=1, ntsb_number="A1")]))

    assert result[1].probable_cause == "Known"
    assert "probableCause: Known" in result[1].detail_context
    assert "aircraftMake: Cessna" in result[1].detail_context
