from types import SimpleNamespace
from unittest import mock

from ntsb.models import NTSBAircraft, NTSBCase, NTSBSearchQuery, NTSBSearchResult


def test_ntsb_generator_plans_searches_and_grounds_answer(import_fresh):
    with import_fresh("rag.ntsb_pipeline") as modules:
        pipeline = modules["rag.ntsb_pipeline"]
        pipeline.RAG_SECURITY = False
        plan_response = SimpleNamespace(
            output_text=(
                '{"intent":"search","goal":"search","ntsb_number":null,"mkey":null,"registration":null,'
                '"start_date":"2024-01-01","end_date":"2024-12-31","make":"Cessna",'
                '"model":null,"location":null,"state":"CA","country":null,"severity":null,'
                '"event_type":null,"investigation_status":null,"text":null,"needs_detail":false,"sort":"date_desc",'
                '"limit":5,"ranking_field":null,"ranking_order":"desc","requested_fields":["aircraft"]}'
            )
        )
        answer_response = SimpleNamespace(output_text="Caso NTSB A1: información recuperada.")
        pipeline.openai_client.responses.create.side_effect = [plan_response, answer_response]
        search_result = NTSBSearchResult(
            cases=[NTSBCase(ntsb_number="A1", mkey=1, aircraft_list=[NTSBAircraft(make="Cessna", model="172")], event_date="2024-01-01")],
            query=NTSBSearchQuery(make="Cessna", start_date="2024-01-01", end_date="2024-12-31"),
            total_matches=1,
            stale=False,
        )
        service = mock.Mock()
        service.search.return_value = search_result

        result = pipeline.generate_ntsb_result("Accidentes de Cessna en California", repository=service)

        assert result.answer == answer_response.output_text
        assert result.metadata["source"] == "NTSB"
        assert result.citations[0].source == "NTSB:A1"
        service.search.assert_called_once()
        planner_request = pipeline.openai_client.responses.create.call_args_list[0].kwargs
        assert planner_request["text"]["format"]["name"] == "ntsb_search_query"
