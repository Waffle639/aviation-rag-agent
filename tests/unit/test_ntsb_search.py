from datetime import date, datetime, timezone

from ntsb.models import NTSBSearchQuery
from ntsb.context import detail_payload_to_context
from ntsb.postgres_repository import PostgresNTSBCaseRepository
from ntsb.search import NTSBSearchService, context_from_result
from ntsb.sync.service import NTSBSyncService
from ntsb.sync.normalizer import normalize_case, records


def test_normalizer_preserves_multi_aircraft_and_detail_fields():
    normalized = normalize_case(
        {
            "mkey": 42,
            "ntsbNumber": "ERA26LA212",
            "eventDate": "2026-08-18T12:00:00Z",
            "country": "United States",
            "totalFatal": "2",
            "probableCause": "Loss of control.",
            "aircrafts": [
                {"aircraftMake": "Cessna", "aircraftModel": "172", "aircraftRegistrationNumber": "N123AB"},
                {"aircraftMake": "Piper", "aircraftModel": "PA-28", "aircraftRegistrationNumber": "N987CD"},
            ],
            "events": [{"eventTier2Name": "Loss of control"}],
            "findings": [{"findingDescription": "Pilot failed to maintain airspeed"}],
            "airports": [{"airportFacilityName": "Test Airport", "airportRunwayId": "18"}],
        }
    )

    assert normalized is not None
    assert normalized.case.mkey == 42
    assert normalized.case.event_date == "2026-08-18"
    assert normalized.case.country_code == "US"
    assert normalized.case.fatalities == 2
    assert normalized.case.probable_cause == "Loss of control."
    assert normalized.case.aircraft == "Cessna 172; Piper PA-28"
    assert normalized.events == ["Loss of control"]
    assert normalized.findings == ["Pilot failed to maintain airspeed"]
    assert normalized.airports[0]["runway"] == "18"


def test_records_extracts_common_payload_shapes():
    assert records({"data": {"records": [{"mkey": 1}]}}) == [{"mkey": 1}]
    assert records({"mkey": 2, "ntsbNumber": "A"}) == [{"mkey": 2, "ntsbNumber": "A"}]
    assert records(None) == []


def test_detail_payload_context_renders_official_fields_without_raw_noise():
    context = detail_payload_to_context(
        {
            "mkey": 1,
            "ntsbNumber": "DCA26WA297",
            "internalCorrelationToken": "ignored",
            "aircrafts": [{"aircraftMake": "Boeing", "aircraftDamage": "None"}],
            "events": [{"eventTier2Name": "Air traffic event"}],
            "findings": [{"findingDescription": "Controller instruction"}],
            "weather": {"visibility": "10 miles"},
        }
    )

    assert "ntsbNumber: DCA26WA297" in context
    assert "aircraftMake: Boeing" in context
    assert "eventTier2Name: Air traffic event" in context
    assert "findingDescription: Controller instruction" in context
    assert "weather.visibility: 10 miles" in context
    assert "internalCorrelationToken" not in context


def test_sync_dedupes_batch_by_mkey_and_ntsb_number():
    first = normalize_case({"mkey": 1, "ntsbNumber": "A1"})
    duplicate_mkey = normalize_case({"mkey": 1, "ntsbNumber": "A2"})
    duplicate_number = normalize_case({"mkey": 2, "ntsbNumber": "A1"})
    unique = normalize_case({"mkey": 3, "ntsbNumber": "A3"})

    deduped, skipped = NTSBSyncService._dedupe_batch([
        first,
        duplicate_mkey,
        duplicate_number,
        unique,
    ])

    assert [item.case.mkey for item in deduped] == [1, 3]
    assert skipped == 2


def test_repository_builds_sql_filters_for_country_registration_and_text():
    repository = PostgresNTSBCaseRepository(connection=object())

    where_sql, params = repository._where(
        NTSBSearchQuery(country="United States", registration="N123", text="engine failure")
    )

    assert "c.country_code = %s" in where_sql
    assert "upper(a.registration) like upper(%s)" in where_sql
    assert "c.search_tsv @@ plainto_tsquery" in where_sql
    assert params == ["US", "%N123%", "engine failure"]


def test_repository_orders_rankings_by_requested_metric():
    repository = PostgresNTSBCaseRepository(connection=object())

    assert repository._order_sql(NTSBSearchQuery(goal="rank", ranking_field="fatalities")).startswith("c.fatalities desc")
    assert repository._order_sql(NTSBSearchQuery(sort="date_asc")).startswith("c.event_date asc")


def test_row_to_case_and_context_compatibility():
    repository = PostgresNTSBCaseRepository(connection=object())
    row = {
        "ntsb_number": "A1",
        "mkey": 1,
        "event_date": date(2024, 1, 1),
        "event_time": None,
        "city": "Los Angeles",
        "location": "Los Angeles, CA",
        "state": "CA",
        "country": "United States",
        "country_code": "US",
        "event_type": "Accident",
        "severity": "Fatal",
        "investigation_status": "Completed",
        "fatalities": 1,
        "serious_injuries": None,
        "minor_injuries": None,
        "total_injuries": None,
        "narrative": "Narrative",
        "probable_cause": None,
        "airport": None,
        "runway": None,
        "source_updated_at": datetime(2024, 1, 2, tzinfo=timezone.utc),
        "synced_at": datetime(2024, 1, 3, tzinfo=timezone.utc),
        "aircraft_rows": [{"aircraft_sequence": 1, "make": "Cessna", "model": "172", "registration": "N1", "category": None, "operation": None, "damage": None}],
        "event_rows": ["Impact"],
        "finding_rows": [],
    }

    case = repository._row_to_case(row)
    result = NTSBSearchService(connection=object())._row_to_case(row)
    context = context_from_result(type("Result", (), {"cases": [case], "query": NTSBSearchQuery(), "total_matches": 1})())

    assert case.aircraft == "Cessna 172"
    assert result.identifier == "A1"
    assert context[0]["font"] == "NTSB:A1"
