from __future__ import annotations

from dashboard.queries import (
    DISPLAY_METRICS,
    public_config,
    public_model_versions,
    is_public_metric,
    metric_definition,
    normalized_delta,
)


def test_public_config_filters_private_fields() -> None:
    filtered = public_config(
        {
            "top_k": 5,
            "prompt_version": "prompt-v2",
            "database_url": "postgresql://secret",
            "trace_id": "abc",
            "api_key": "secret",
            "raw_output": {"hidden": True},
        }
    )

    assert filtered == {"top_k": 5, "prompt_version": "prompt-v2"}


def test_public_model_versions_filters_unknown_fields() -> None:
    filtered = public_model_versions(
        {
            "generator_model": "gpt-test",
            "embedding_model": "embed-test",
            "langsmith_project": "private-project",
            "trace_url": "https://example.test/trace",
        }
    )

    assert filtered == {
        "generator_model": "gpt-test",
        "embedding_model": "embed-test",
    }


def test_delta_direction_for_quality_and_duplicate_metrics() -> None:
    assert normalized_delta("mrr", 0.1) == 0.1
    assert normalized_delta("duplicate_ratio", 0.1) == -0.1
    assert normalized_delta("retrieved_tokens", 100) is None


def test_display_metrics_are_public_and_named() -> None:
    for metric_name in DISPLAY_METRICS:
        assert is_public_metric(metric_name)
        assert metric_definition(metric_name).label
