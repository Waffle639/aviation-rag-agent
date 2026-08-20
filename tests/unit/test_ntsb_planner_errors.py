from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ntsb.planner import plan_query


def test_planner_rejects_invalid_model_json():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(output_text="not-json")

    with pytest.raises(ValueError, match="invalid JSON"):
        plan_query(client, "question", "model")


def test_planner_escapes_untrusted_question_before_model_input():
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text=(
            '{"intent":"search","ntsb_number":null,"mkey":null,"registration":null,'
            '"start_date":null,"end_date":null,"make":null,"model":null,"location":null,'
            '"state":null,"country":null,"severity":null,"event_type":null,'
            '"investigation_status":null,"text":null,"needs_detail":false,"sort":"date_desc","limit":1,'
            '"goal":"search","ranking_field":null,"ranking_order":"desc","requested_fields":[]}'
        )
    )

    plan_query(client, '<ignore>" & instructions', "model")

    assert client.responses.create.call_args.kwargs["input"] == (
        "<question>&lt;ignore&gt;&quot; &amp; instructions</question>"
    )
