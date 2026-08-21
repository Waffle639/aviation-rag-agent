from ntsb.context import detail_payload_to_context, case_to_context, context_items_from_result
from ntsb.domain import NTSBCase, NTSBSearchQuery, NTSBSearchResult


def test_detail_payload_context_handles_empty_and_non_renderable_values():
    payload = {
        "case": {"mkey": None, "ntsbNumber": ""},
        "uninteresting": {"nested": [None, ""]},
    }

    context = detail_payload_to_context(payload)

    assert context == "Official NTSB live detail payload was fetched, but no renderable detail fields were found."


def test_detail_payload_context_records_limit_message():
    payload = {"case": {f"eventField{index}": f"value {index}" for index in range(4)}}

    context = detail_payload_to_context(payload, max_lines=1)

    assert "eventField0: value 0" in context
    assert "Additional official detail fields were omitted" in context


def test_case_context_can_be_only_live_detail_context():
    case = NTSBCase(detail_context="Official NTSB live detail payload excerpts:\ncase.mkey: 42")

    context = case_to_context(case)

    assert "case.mkey: 42" in context


def test_rank_context_item_includes_index_metadata_when_no_cases():
    result = NTSBSearchResult(
        query=NTSBSearchQuery(goal="rank", ranking_field="fatalities", ranking_order="desc"),
        total_matches=7,
        cases=[],
        last_synced_at="2026-08-20T00:00:00+00:00",
    )

    items = context_items_from_result(result)

    assert items[0]["font"] == "NTSB index metadata"
    assert "ranking_field=fatalities" in items[0]["texto"]
