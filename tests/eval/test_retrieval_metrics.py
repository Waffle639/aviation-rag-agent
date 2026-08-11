import pytest

from evaluation.metrics.retrieval import (
    RetrievedItem,
    duplicate_ratio,
    evaluate_retrieval,
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
