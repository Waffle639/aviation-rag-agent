from __future__ import annotations

from dashboard.queries import (
    DISPLAY_METRICS,
    concept_metric,
    display_metrics_for_run,
    public_config,
    public_model_versions,
    is_public_metric,
    metric_definition,
    normalized_delta,
    run_top_k,
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
            "prompt_guard_model": "guard-test",
            "langsmith_project": "private-project",
            "trace_url": "https://example.test/trace",
        }
    )

    assert filtered == {
        "generator_model": "gpt-test",
        "embedding_model": "embed-test",
        "prompt_guard_model": "guard-test",
    }


def test_delta_direction_for_quality_and_duplicate_metrics() -> None:
    assert normalized_delta("mrr", 0.1) == 0.1
    assert normalized_delta("duplicate_ratio", 0.1) == -0.1
    assert normalized_delta("retrieved_tokens", 100) is None


def test_display_metrics_are_public_and_named() -> None:
    for metric_name in DISPLAY_METRICS:
        assert is_public_metric(metric_name)
        assert metric_definition(metric_name).label


def test_dynamic_metric_names_are_public_and_described() -> None:
    assert is_public_metric("recall_at_7")
    assert is_public_metric("ndcg_at_12")
    assert not is_public_metric("recall_at_0")
    assert not is_public_metric("unsafe_metric")
    assert metric_definition("recall_at_7").label == "Recall@7"
    assert metric_definition("recall_at_7").description


def test_display_metrics_follow_run_top_k() -> None:
    run = {"public_config": {"top_k": 3}}

    assert run_top_k(run) == 3
    assert display_metrics_for_run(run) == ("recall_at_3", "mrr", "ndcg_at_3", "hit_rate_at_3")
    assert concept_metric("recall", run) == "recall_at_3"
