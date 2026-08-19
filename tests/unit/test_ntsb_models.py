import pytest

from ntsb.models import NTSBCase, NTSBSearchQuery, NTSBSearchResult


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
    case = NTSBCase(mkey=7, make="Boeing", model="747", raw={"extra": True})

    assert case.identifier == "7"
    assert case.aircraft == "Boeing 747"
    payload = case.to_dict()
    assert payload["identifier"] == "7"
    assert payload["aircraft"] == "Boeing 747"
    assert payload["raw"] == {"extra": True}


def test_case_context_contains_only_present_fields_and_identifier():
    case = NTSBCase(ntsb_number="WPR24LA001", event_date="2024-02-03", fatalities=2)

    context = case.to_context()

    assert "[Fuente: NTSB | Caso: WPR24LA001]" in context
    assert "Fecha: 2024-02-03" in context
    assert "Fallecidos: 2" in context
    assert "Aeronave:" not in context


def test_search_result_serializes_query_and_cases_and_count_context():
    query = NTSBSearchQuery(intent="count")
    result = NTSBSearchResult(
        cases=[NTSBCase(ntsb_number="A1")],
        query=query,
        matches_found=3,
        truncated=True,
        warnings=["limited"],
    )

    assert "3 matching" in result.context_items()[0]["texto"]
    payload = result.to_dict()
    assert payload["query"]["intent"] == "count"
    assert payload["cases"][0]["identifier"] == "A1"
    assert payload["warnings"] == ["limited"]
