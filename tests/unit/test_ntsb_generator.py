from types import SimpleNamespace
from unittest import mock

from ntsb.models import NTSBCase, NTSBSearchQuery, NTSBSearchResult


def test_ntsb_generator_plans_searches_and_grounds_answer(import_fresh):
    with import_fresh("rag.generator") as modules:
        generator = modules["rag.generator"]
        generator.RAG_SECURITY = False
        plan_response = SimpleNamespace(
            output_text=(
                '{"intent":"search","ntsb_number":null,"mkey":null,"registration":null,'
                '"start_date":"2024-01-01","end_date":"2024-12-31","make":"Cessna",'
                '"model":null,"location":null,"state":"CA","country":null,"severity":null,'
                '"event_type":null,"investigation_status":null,"text":null,'
                '"needs_detail":false,"sort":"date_desc","limit":5}'
            )
        )
        answer_response = SimpleNamespace(output_text="Caso NTSB A1: información recuperada.")
        generator.openai_client.responses.create.side_effect = [plan_response, answer_response]
        search_result = NTSBSearchResult(
            cases=[NTSBCase(ntsb_number="A1", make="Cessna", model="172", event_date="2024-01-01")],
            query=NTSBSearchQuery(make="Cessna", start_date="2024-01-01", end_date="2024-12-31"),
        )
        service = mock.Mock()
        service.search.return_value = search_result

        result = generator.generate_ntsb_result("Accidentes de Cessna en California", service=service)

        assert result.answer == answer_response.output_text
        assert result.metadata["source"] == "NTSB"
        assert result.citations[0].source == "NTSB:A1"
        service.search.assert_called_once()
        planner_request = generator.openai_client.responses.create.call_args_list[0].kwargs
        assert planner_request["text"]["format"]["name"] == "ntsb_search_query"
