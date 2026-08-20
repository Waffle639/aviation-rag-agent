from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from ntsb.planner import plan_query


def test_planner_requests_strict_schema_and_returns_query():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text='{"intent":"search","goal":"search","ntsb_number":null,"mkey":null,"registration":null,'
        '"start_date":"2024-01-01","end_date":"2024-12-31","make":"Boeing",'
        '"model":"747","location":null,"state":null,"country":null,"severity":null,'
        '"event_type":null,"investigation_status":null,"text":null,"needs_detail":false,'
        '"sort":"date_desc","limit":5,"ranking_field":null,"ranking_order":"desc",'
        '"requested_fields":["aircraft"]}'
    )

    query = plan_query(client, "últimos Boeing 747 de 2024", "gpt-test")

    assert query.make == "Boeing"
    assert query.limit == 5
    assert query.requested_fields == ["aircraft"]
    request = client.responses.create.call_args.kwargs
    assert request["text"]["format"]["name"] == "ntsb_search_query"
    assert request["text"]["format"]["strict"] is True


def test_planner_repairs_fatality_ranking_and_relative_period():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text=(
            '{"intent":"search","ntsb_number":null,"mkey":null,"registration":null,'
            '"start_date":null,"end_date":null,"make":null,"model":null,"location":null,'
            '"state":null,"country":null,"severity":null,"event_type":null,'
            '"investigation_status":null,"text":null,"needs_detail":false,"sort":"date_desc","limit":10,'
            '"goal":"search","ranking_field":null,"ranking_order":"desc","requested_fields":[]}'
        )
    )

    today = date(2026, 8, 19)
    query = plan_query(client, "the accident with more deaths in the past 10 years", "gpt-test", today=today)

    assert query.goal == "rank"
    assert query.ranking_field == "fatalities"
    assert query.ranking_order == "desc"
    assert query.limit == 1
    assert query.start_date == "2016-08-19"
    assert query.end_date == today.isoformat()
    assert "probable_cause" in query.requested_fields


def test_planner_repairs_exact_lookup_and_complete_detail_request():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text=(
            '{"intent":"search","goal":"search","ntsb_number":null,"mkey":null,"registration":null,'
            '"start_date":null,"end_date":null,"make":null,"model":null,"location":null,'
            '"state":null,"country":null,"severity":null,"event_type":null,'
            '"investigation_status":null,"text":null,"needs_detail":false,"sort":"date_desc","limit":10,'
            '"ranking_field":null,"ranking_order":"desc","requested_fields":[]}'
        )
    )

    query = plan_query(client, "resumen completo de ERA26LA212 dime todo lo importante", "gpt-test")

    assert query.goal == "lookup"
    assert query.ntsb_number == "ERA26LA212"
    assert query.needs_detail is True
    assert "narrative" in query.requested_fields
    assert "probable_cause" in query.requested_fields
    client.responses.create.assert_called_once()
