from agent.policies import select_ntsb_detail_requests
from agent.schemas import EvidenceItem


def test_detail_policy_allows_concrete_missing_case_detail():
    evidence = EvidenceItem(
        evidence_id="NTSB-001",
        source_kind="ntsb_index",
        source_name="NTSB:A1",
        source_record_id="A1",
        text="NTSB case: A1\nNarrative: none",
        metadata={"ntsb_number": "WPR23FA001", "mkey": 123},
    )

    requests = select_ntsb_detail_requests("What was the probable cause?", [evidence])

    assert len(requests) == 1
    assert requests[0].ntsb_number == "WPR23FA001"
    assert requests[0].mkey == 123


def test_detail_policy_blocks_rankings():
    evidence = EvidenceItem(
        evidence_id="NTSB-001",
        source_kind="ntsb_index",
        source_name="NTSB:A1",
        text="NTSB case: A1\nNarrative: none",
        metadata={"ntsb_number": "WPR23FA001", "mkey": 123},
    )

    requests = select_ntsb_detail_requests("Which Cessna accident had the most fatalities and why?", [evidence])

    assert requests == []
