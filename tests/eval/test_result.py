from rag.result import Citation, RAGResult, estimate_tokens
from types import SimpleNamespace
from unittest import mock


def test_estimate_tokens_is_zero_for_empty_text():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1


def test_rag_result_serializes_citations_and_runtime_metadata():
    result = RAGResult(
        question="What is the length?",
        answer="250 feet.",
        citations=[Citation("context_001", "Boeing 747", "wiki", "p1", "c1", "250 feet")],
        abstained=False,
        timings_ms={"total": 12.5},
        token_usage={"total_tokens": 10},
    )

    payload = result.to_dict()

    assert payload["citations"][0]["citation_id"] == "context_001"
    assert payload["timings_ms"]["total"] == 12.5
    assert payload["token_usage"]["total_tokens"] == 10


def test_generate_result_keeps_retrieval_context_and_timings(import_fresh):
    with import_fresh("rag.generator") as modules:
        generator = modules["rag.generator"]
        generator.openai_client.responses.create.return_value = SimpleNamespace(
            output_text="The answer is 250 feet.",
            usage=SimpleNamespace(input_tokens=20, output_tokens=6, total_tokens=26),
        )
        retrieved = [
            {
                "aircraft": "Boeing 747",
                "font": "wiki",
                "chunk_id": "boeing_747_wiki_p001",
                "texto": "The Boeing 747-8 is 250 feet long.",
            }
        ]
        with (
            mock.patch.object(generator, "search_context", return_value=retrieved),
            mock.patch.object(generator, "_run_detector"),
            mock.patch.object(generator, "moderate"),
            mock.patch.object(generator, "check_output"),
        ):
            result = generator.generate_result("What is the length?")

    assert result.answer == "The answer is 250 feet."
    assert result.retrieved_items == retrieved
    assert result.context_items == retrieved
    assert result.citations[0].parent_id == "boeing_747_wiki_p001"
    assert result.token_usage["total_tokens"] == 26
    assert result.timings_ms["total"] >= 0
