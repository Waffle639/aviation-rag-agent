"""Deterministic retrieval metrics independent of the storage backend."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RetrievedItem:
    """The retrieval fields needed for quality and efficiency metrics."""

    item_id: str
    parent_id: str | None = None
    document_id: str | None = None
    token_count: int = 0


def _relevant_ids(
    qrels: Mapping[str, int], relevance_threshold: int
) -> set[str]:
    return {
        item_id
        for item_id, relevance in qrels.items()
        if relevance >= relevance_threshold
    }


def _unique_ids(item_ids: Iterable[str]) -> list[str]:
    seen = set()
    unique = []
    for item_id in item_ids:
        if item_id not in seen:
            seen.add(item_id)
            unique.append(item_id)
    return unique


def recall_at_k(
    ranked_ids: Sequence[str],
    qrels: Mapping[str, int],
    k: int,
    relevance_threshold: int = 2,
) -> float:
    """Return the fraction of relevant items found in the first ``k`` ranks."""
    relevant = _relevant_ids(qrels, relevance_threshold)
    if not relevant:
        return 1.0
    found = relevant.intersection(_unique_ids(ranked_ids[:k]))
    return len(found) / len(relevant)


def precision_at_k(
    ranked_ids: Sequence[str],
    qrels: Mapping[str, int],
    k: int,
    relevance_threshold: int = 2,
) -> float:
    """Return the fraction of the first ``k`` ranks that are relevant."""
    if k <= 0:
        raise ValueError("k must be positive")
    relevant = _relevant_ids(qrels, relevance_threshold)
    return sum(item_id in relevant for item_id in ranked_ids[:k]) / k


def hit_rate_at_k(
    ranked_ids: Sequence[str],
    qrels: Mapping[str, int],
    k: int,
    relevance_threshold: int = 2,
) -> float:
    """Return 1 when at least one relevant item appears in the first ``k`` ranks."""
    relevant = _relevant_ids(qrels, relevance_threshold)
    return float(bool(relevant.intersection(ranked_ids[:k])))


def mean_reciprocal_rank(
    ranked_ids: Sequence[str],
    qrels: Mapping[str, int],
    relevance_threshold: int = 2,
) -> float:
    """Return the reciprocal rank of the first relevant item for one query."""
    relevant = _relevant_ids(qrels, relevance_threshold)
    for rank, item_id in enumerate(ranked_ids, start=1):
        if item_id in relevant:
            return 1.0 / rank
    return 0.0


def _dcg(relevances: Iterable[int]) -> float:
    return sum(
        (2**relevance - 1) / math.log2(rank + 1)
        for rank, relevance in enumerate(relevances, start=1)
    )


def ndcg_at_k(
    ranked_ids: Sequence[str],
    qrels: Mapping[str, int],
    k: int,
) -> float:
    """Return nDCG@k using the qrels' graded relevance values."""
    actual = [qrels.get(item_id, 0) for item_id in ranked_ids[:k]]
    ideal = sorted(qrels.values(), reverse=True)[:k]
    ideal_dcg = _dcg(ideal)
    if ideal_dcg == 0:
        return 1.0
    return _dcg(actual) / ideal_dcg


def unique_parent_ratio(items: Sequence[RetrievedItem]) -> float:
    """Return the ratio of distinct parents to retrieved items."""
    if not items:
        return 1.0
    parents = {item.parent_id or item.item_id for item in items}
    return len(parents) / len(items)


def duplicate_ratio(items: Sequence[RetrievedItem]) -> float:
    """Return the fraction of retrieved rows duplicated by parent identity."""
    return 1.0 - unique_parent_ratio(items)


def retrieved_token_count(items: Sequence[RetrievedItem]) -> int:
    """Return the total token count carried by retrieved items."""
    return sum(max(item.token_count, 0) for item in items)


def evaluate_retrieval(
    items: Sequence[RetrievedItem],
    qrels: Mapping[str, int],
    k_values: Sequence[int] = (3, 5, 10),
    relevance_threshold: int = 2,
) -> dict[str, float | int]:
    """Calculate the first retrieval metrics for one evaluated query."""
    ranked_ids = [item.item_id for item in items]
    metrics: dict[str, float | int] = {
        "mrr": mean_reciprocal_rank(ranked_ids, qrels, relevance_threshold),
        "unique_parent_ratio": unique_parent_ratio(items),
        "duplicate_ratio": duplicate_ratio(items),
        "retrieved_items": len(items),
        "retrieved_tokens": retrieved_token_count(items),
    }
    for k in k_values:
        metrics[f"recall_at_{k}"] = recall_at_k(
            ranked_ids, qrels, k, relevance_threshold
        )
        metrics[f"precision_at_{k}"] = precision_at_k(
            ranked_ids, qrels, k, relevance_threshold
        )
        metrics[f"hit_rate_at_{k}"] = hit_rate_at_k(
            ranked_ids, qrels, k, relevance_threshold
        )
        metrics[f"ndcg_at_{k}"] = ndcg_at_k(ranked_ids, qrels, k)
    return metrics
