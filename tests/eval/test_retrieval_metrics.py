import pytest

from evaluation.metrics.retrieval import (
    RetrievedItem,
    duplicate_ratio,
    evaluate_retrieval,
    hit_rate_at_k,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    retrieved_token_count,
    unique_parent_ratio,
)


RANKED_IDS = ["p2", "p1", "p3", "p4"]
QRELS = {"p1": 3, "p2": 1, "p3": 2}


def test_ranked_metrics_use_graduated_relevance_threshold():
    assert recall_at_k(RANKED_IDS, QRELS, 3) == pytest.approx(1.0)
    assert precision_at_k(RANKED_IDS, QRELS, 3) == pytest.approx(2 / 3)
    assert mean_reciprocal_rank(RANKED_IDS, QRELS) == pytest.approx(1 / 2)
    assert ndcg_at_k(RANKED_IDS, QRELS, 3) == pytest.approx(0.7364, abs=1e-4)


def test_retrieval_efficiency_metrics_count_unique_parents_and_tokens():
    items = [
        RetrievedItem("child-1", parent_id="parent-1", token_count=100),
        RetrievedItem("child-2", parent_id="parent-1", token_count=120),
        RetrievedItem("child-3", parent_id="parent-2", token_count=80),
    ]

    assert unique_parent_ratio(items) == pytest.approx(2 / 3)
    assert duplicate_ratio(items) == pytest.approx(1 / 3)
    assert retrieved_token_count(items) == 300


def test_evaluate_retrieval_returns_named_metrics():
    items = [RetrievedItem(item_id=item_id) for item_id in RANKED_IDS]

    metrics = evaluate_retrieval(items, QRELS, k_values=(3,))

    assert metrics["recall_at_3"] == pytest.approx(1.0)
    assert metrics["precision_at_3"] == pytest.approx(2 / 3)
    assert metrics["ndcg_at_3"] == pytest.approx(0.7364, abs=1e-4)


def test_ranked_quality_metrics_deduplicate_document_ids_before_scoring():
    items = [
        RetrievedItem(item_id="doc-a", parent_id="doc-a-p001"),
        RetrievedItem(item_id="doc-a", parent_id="doc-a-p002"),
        RetrievedItem(item_id="doc-b", parent_id="doc-b-p001"),
    ]

    metrics = evaluate_retrieval(items, {"doc-b": 3}, k_values=(3,))

    assert metrics["mrr"] == pytest.approx(1 / 2)
    assert metrics["recall_at_3"] == pytest.approx(1.0)


@pytest.mark.parametrize("metric", [recall_at_k, precision_at_k, hit_rate_at_k, ndcg_at_k])
@pytest.mark.parametrize("k", [0, -1, True, 1.5])
def test_ranked_metrics_reject_invalid_cutoffs(metric, k):
    with pytest.raises(ValueError, match="positive integer"):
        metric(["p1"], {"p1": 3}, k)


def test_empty_qrels_have_explicit_metric_semantics():
    assert recall_at_k([], {}, 3) == 1.0
    assert precision_at_k([], {}, 3) == 0.0
    assert hit_rate_at_k([], {}, 3) == 0.0
    assert ndcg_at_k([], {}, 3) == 1.0
