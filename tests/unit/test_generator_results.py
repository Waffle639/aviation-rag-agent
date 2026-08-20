from types import SimpleNamespace
from unittest import mock

from ntsb.models import NTSBSearchQuery, NTSBSearchResult


def test_generate_result_preserves_evaluation_metadata_without_usage(import_fresh):
    with import_fresh("rag.generator") as modules:
        generator = modules["rag.generator"]
        generator.openai_client.responses.create.return_value = SimpleNamespace(
            output_text="The answer is 40 knots."
        )
        retrieved = [
            {
                "aircraft": "Cessna 172",
                "font": "manual",
                "parent_id": "p1",
                "chunk_id": "c1",
                "texto": "Vso is 40 knots.",
            }
        ]
        langsmith_extra = {
            "name": "evaluation.baseline.av_0001",
            "metadata": {"case_id": "av_0001", "dataset_id": "dataset"},
        }
        with (
            mock.patch.object(generator, "_run_detector"),
            mock.patch.object(generator, "moderate"),
            mock.patch.object(generator, "check_output"),
            mock.patch.object(generator, "search_context", return_value=retrieved),
        ):
            result = generator.generate_result(
                "What is Vso?", langsmith_extra=langsmith_extra
            )

    assert result.answer == "The answer is 40 knots."
    assert result.metadata["top_k"] == generator.K_TOP
    assert "input_tokens" not in result.token_usage
    assert result.citations[0].parent_id == "p1"
    assert result.citations[0].quote == "Vso is 40 knots."


def test_generate_result_marks_exact_abstention_and_keeps_empty_context(import_fresh):
    with import_fresh("rag.generator") as modules:
        generator = modules["rag.generator"]
        generator.openai_client.responses.create.return_value = SimpleNamespace(
            output_text="I don't have that information in my sources.",
            usage=SimpleNamespace(input_tokens=5, output_tokens=10, total_tokens=15),
        )
        with (
            mock.patch.object(generator, "_run_detector"),
            mock.patch.object(generator, "moderate"),
            mock.patch.object(generator, "check_output"),
            mock.patch.object(generator, "search_context", return_value=[]),
        ):
            result = generator.generate_result("unknown question")

    assert result.abstained is True
    assert result.retrieved_items == []
    assert result.context_items == []
    assert result.citations == []
    assert result.token_usage["total_tokens"] == 15


def test_ntsb_result_includes_truncation_limit_and_safe_empty_context(import_fresh):
    with import_fresh("rag.ntsb_pipeline") as modules:
        pipeline = modules["rag.ntsb_pipeline"]
        pipeline.RAG_SECURITY = False
        plan_response = SimpleNamespace(
            output_text=(
                '{"intent":"search","goal":"search","ntsb_number":null,"mkey":null,"registration":null,'
                '"start_date":null,"end_date":null,"make":null,"model":null,'
                '"location":null,"state":null,"country":null,"severity":null,'
                '"event_type":null,"investigation_status":null,"text":null,"needs_detail":false,"sort":"date_desc",'
                '"limit":2,"ranking_field":null,"ranking_order":"desc","requested_fields":[]}'
            )
        )
        answer_response = SimpleNamespace(
            output_text="I don't have that information in the NTSB records."
        )
        pipeline.openai_client.responses.create.side_effect = [
            plan_response,
            answer_response,
        ]
        service = mock.Mock()
        service.search.return_value = NTSBSearchResult(
            query=NTSBSearchQuery(limit=2),
            total_matches=3,
            warnings=["limited"],
            stale=False,
        )

        result = pipeline.generate_ntsb_result("Which cases match?", repository=service)

    assert result.abstained is True
    assert result.context_items[0]["font"] == "NTSB"
    assert result.metadata["truncated"] is True
    assert result.metadata["warnings"] == ["limited"]
    prompt = pipeline.openai_client.responses.create.call_args_list[1].kwargs
    assert "first page" in prompt["instructions"]
    assert "Probable cause" in prompt["instructions"]
    assert "No NTSB aviation cases matched" in prompt["input"]


def test_ntsb_result_runs_security_checks_and_preserves_case_usage(import_fresh):
    with import_fresh("rag.ntsb_pipeline") as modules:
        pipeline = modules["rag.ntsb_pipeline"]
        plan_response = SimpleNamespace(
            output_text=(
                '{"intent":"search","goal":"search","ntsb_number":null,"mkey":null,"registration":null,'
                '"start_date":null,"end_date":null,"make":null,"model":null,'
                '"location":null,"state":null,"country":null,"severity":null,'
                '"event_type":null,"investigation_status":null,"text":null,"needs_detail":false,"sort":"date_desc",'
                '"limit":1,"ranking_field":null,"ranking_order":"desc","requested_fields":[]}'
            )
        )
        answer_response = SimpleNamespace(
            output_text="Case A1 had an engine failure.",
            usage=SimpleNamespace(input_tokens=20, output_tokens=8, total_tokens=28),
        )
        pipeline.openai_client.responses.create.side_effect = [plan_response, answer_response]
        service = mock.Mock()
        service.search.return_value = NTSBSearchResult(
            cases=[], query=NTSBSearchQuery(limit=1), stale=False
        )
        with (
            mock.patch.object(pipeline, "_run_detector") as detector,
            mock.patch.object(pipeline, "moderate") as moderate,
            mock.patch.object(pipeline, "check_output") as check_output,
        ):
            result = pipeline.generate_ntsb_result("question", repository=service)

    detector.assert_called_once_with("question")
    assert moderate.call_args_list == [
        mock.call("question", label="question"),
        mock.call(answer_response.output_text, label="answer"),
    ]
    check_output.assert_called_once_with(answer_response.output_text)
    assert result.token_usage["total_tokens"] == 28
