from types import SimpleNamespace
from unittest import mock

import pytest

pytestmark = pytest.mark.e2e

def test_generate_answer_runs_real_pipeline_without_dotenv(
    import_fresh, monkeypatch
):
    """Run the production pipeline while replacing only its external edges."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-e2e-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://e2e:e2e@localhost:9/e2e")

    with import_fresh("rag.generator") as modules:
        generator = modules["rag.generator"]
        response = SimpleNamespace(
            output_text=(
                "According to the Boeing 747 flight manual, the maximum speed "
                "is 490 knots."
            )
        )
        generator.openai_client.responses.create.return_value = response

        retrieved = [
            {
                "aircraft": "Boeing 747",
                "font": "flight manual",
                "chunk_id": "boeing_747_manual_p000",
                "texto": "The Boeing 747 maximum speed is 490 knots.",
                "similarity": 0.91,
            }
        ]
        with (
            mock.patch.object(generator, "search_context", return_value=retrieved) as search,
            mock.patch.object(generator, "_run_detector"),
            mock.patch.object(generator, "moderate"),
            mock.patch.object(generator, "check_output"),
        ):
            answer = generator.generate_answer("  What is the maximum speed?  ")

        assert answer == response.output_text
        search.assert_called_once_with("What is the maximum speed?", top_k=generator.K_TOP)
        request = generator.openai_client.responses.create.call_args.kwargs
        assert request["model"] == generator.MODEL_NAME
        assert "Boeing 747 - flight manual" in request["input"]
        assert "The Boeing 747 maximum speed is 490 knots." in request["input"]
        assert "What is the maximum speed?" in request["input"]
