import pytest

from ntsb.context import case_to_context
from ntsb.models import NTSBAircraft, NTSBCase, NTSBSearchQuery, NTSBSearchResult


def test_query_normalizes_invalid_enum_values_and_clamps_limit():
    query = NTSBSearchQuery(intent="unsupported", sort="random", limit=1000)

    assert query.intent == "search"
    assert query.sort == "date_desc"
    assert query.limit == 100


def test_query_converts_mkey_and_iso_dates():
    query = NTSBSearchQuery(
        mkey="42",
        start_date="2024-01-02",
        end_date="2024-12-31",
        limit=0,
    )

    assert query.mkey == 42
    assert query.start_date == "2024-01-02"
    assert query.end_date == "2024-12-31"
    assert query.limit == 10


@pytest.mark.parametrize("field", ["start_date", "end_date"])
def test_query_rejects_invalid_date_format(field):
    with pytest.raises(ValueError, match=field):
        NTSBSearchQuery(**{field: "02/01/2024"})


def test_query_rejects_non_numeric_mkey():
    with pytest.raises(ValueError):
        NTSBSearchQuery(mkey="not-a-number")


def test_case_identifier_fallback_and_serialization():
    case = NTSBCase(mkey=7, aircraft_list=[NTSBAircraft(make="Boeing", model="747")])

    assert case.identifier == "7"
    assert case.aircraft == "Boeing 747"
    payload = case.to_dict()
    assert payload["identifier"] == "7"
    assert payload["aircraft"] == "Boeing 747"
    assert payload["make"] == "Boeing"


def test_case_context_contains_only_present_fields_and_identifier():
    case = NTSBCase(ntsb_number="WPR24LA001", event_date="2024-02-03", fatalities=2)

    context = case_to_context(case)

    assert "[Source: NTSB | Case: WPR24LA001]" in context
    assert "Date: 2024-02-03" in context
    assert "Fatalities: 2" in context
    assert "Aircraft:" not in context


def test_search_result_serializes_query_and_cases_and_count_context():
    query = NTSBSearchQuery(intent="count")
    result = NTSBSearchResult(
        cases=[NTSBCase(ntsb_number="A1")],
        query=query,
        total_matches=3,
        warnings=["limited"],
    )

    assert "3 matching" in result.context_items()[0]["texto"]
    payload = result.to_dict()
    assert payload["query"]["intent"] == "count"
    assert payload["cases"][0]["identifier"] == "A1"
    assert payload["warnings"] == ["limited"]
    assert payload["matches_found"] == 3


def test_rank_result_context_includes_ranking_metadata():
    result = NTSBSearchResult(
        cases=[NTSBCase(ntsb_number="A1")],
        query=NTSBSearchQuery(goal="rank", ranking_field="fatalities", ranking_order="desc"),
        total_matches=10,
    )

    items = result.context_items()

    assert items[0]["font"] == "NTSB index metadata"
    assert "ranking_field=fatalities" in items[0]["texto"]
    assert items[1]["ntsb_number"] == "A1"
    assert result.truncated is False
