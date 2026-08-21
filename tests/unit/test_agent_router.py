import pytest

from agent.router import deterministic_route
from agent.schemas import RouteDecision


def test_route_decision_requires_source_queries():
    with pytest.raises(ValueError):
        RouteDecision(route="documents", reason="missing query")


def test_deterministic_router_selects_documents():
    decision = deterministic_route("What is the Cessna 172 stall speed?")

    assert decision.route == "documents"
    assert decision.sources == ["documents"]
    assert decision.document_query


def test_deterministic_router_selects_accidents_for_ntsb_case():
    decision = deterministic_route("What was the probable cause of WPR23FA001?")

    assert decision.route == "accidents"
    assert decision.sources == ["accidents"]
    assert decision.accident_question


def test_deterministic_router_selects_both():
    decision = deterministic_route("What does the manual say about stall recovery and what accidents involved stalls?")

    assert decision.route == "both"
    assert decision.sources == ["documents", "accidents"]


def test_deterministic_router_abstains_outside_domain():
    decision = deterministic_route("How do I cook pasta?")

    assert decision.route == "abstain"
    assert decision.sources == []
