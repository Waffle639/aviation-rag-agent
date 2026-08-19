from types import SimpleNamespace
from unittest.mock import Mock

from ntsb.planner import plan_query


def test_planner_requests_strict_schema_and_returns_query():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text='{"intent":"search","ntsb_number":null,"mkey":null,"registration":null,'
        '"start_date":"2024-01-01","end_date":"2024-12-31","make":"Boeing",'
        '"model":"747","location":null,"state":null,"country":null,"severity":null,'
        '"event_type":null,"investigation_status":null,"text":null,"needs_detail":false,'
        '"sort":"date_desc","limit":5}'
    )

    query = plan_query(client, "últimos Boeing 747 de 2024", "gpt-test")

    assert query.make == "Boeing"
    assert query.limit == 5
    request = client.responses.create.call_args.kwargs
    assert request["text"]["format"]["name"] == "ntsb_search_query"
    assert request["text"]["format"]["strict"] is True
