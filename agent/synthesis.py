"""Final grounded answer generation and citation validation."""

from __future__ import annotations

from html import escape
import json
import re
from typing import Any

from langsmith import traceable

from agent.prompts import SYNTHESIS_PROMPT
from agent.schemas import EvidenceItem, FallbackRecord, GroundedAnswer


ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "abstained": {"type": "boolean"},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "evidence_ids", "abstained", "limitations"],
    "additionalProperties": False,
}


def format_evidence(evidence: list[EvidenceItem]) -> str:
    blocks = []
    for item in evidence:
        blocks.append(
            "\n".join(
                [
                    f"[{escape(item.evidence_id)}]",
                    f"source_kind: {escape(item.source_kind)}",
                    f"source_name: {escape(item.source_name)}",
                    f"source_record_id: {escape(str(item.source_record_id or ''))}",
                    "text:",
                    escape(item.text),
                ]
            )
        )
    return "\n\n".join(blocks)


def fallback_answer(question: str, evidence: list[EvidenceItem], warnings: list[str]) -> GroundedAnswer:
    if not evidence:
        limitations = warnings or ["No supporting evidence was retrieved."]
        return GroundedAnswer(
            answer="I don't have that information in my sources.",
            evidence_ids=[],
            abstained=True,
            limitations=limitations,
        )
    ids = [item.evidence_id for item in evidence[:5]]
    return GroundedAnswer(
        answer=(
            "I found relevant evidence but the answer generator is not configured. "
            f"Review these evidence IDs: {', '.join(ids)}."
        ),
        evidence_ids=ids,
        abstained=False,
        limitations=["Generator model was not configured.", *warnings],
    )


@traceable(run_type="llm", name="agent_synthesize")
async def synthesize_answer(
    generator_client: Any | None,
    *,
    model_name: str,
    question: str,
    evidence: list[EvidenceItem],
    warnings: list[str],
) -> GroundedAnswer:
    if generator_client is None:
        return fallback_answer(question, evidence, warnings)
    if not evidence:
        return fallback_answer(question, evidence, warnings)

    prompt_input = f"""
<evidence>
{format_evidence(evidence)}
</evidence>

<warnings>
{escape(json.dumps(warnings, ensure_ascii=False))}
</warnings>

<question>
{escape(question)}
</question>
"""
    response = generator_client.responses.create(
        model=model_name,
        instructions=SYNTHESIS_PROMPT,
        input=prompt_input,
        text={
            "format": {
                "type": "json_schema",
                "name": "grounded_answer",
                "strict": True,
                "schema": ANSWER_SCHEMA,
            }
        },
    )
    try:
        return GroundedAnswer(**json.loads(response.output_text))
    except (TypeError, ValueError, json.JSONDecodeError):
        ids = re.findall(r"\[(DOC-\d{3}|NTSB(?:-API)?-\d{3})\]", str(response.output_text))
        return GroundedAnswer(
            answer=str(response.output_text or "").strip() or "I don't have that information in my sources.",
            evidence_ids=ids,
            abstained=str(response.output_text or "").strip().lower()
            == "i don't have that information in my sources.",
            limitations=["Generator returned unstructured output; citation IDs were extracted from text."],
        )


def validate_grounded_answer(
    answer: GroundedAnswer,
    evidence: list[EvidenceItem],
) -> tuple[GroundedAnswer, list[FallbackRecord]]:
    valid_ids = {item.evidence_id for item in evidence}
    used = [evidence_id for evidence_id in answer.evidence_ids if evidence_id in valid_ids]
    invalid = [evidence_id for evidence_id in answer.evidence_ids if evidence_id not in valid_ids]
    fallbacks = []
    if invalid:
        fallbacks.append(
            FallbackRecord(
                stage="validate_citations",
                cause="invalid_evidence_ids",
                action="drop_invalid_ids",
                result=", ".join(invalid),
            )
        )
    if not evidence and not answer.abstained:
        return (
            GroundedAnswer(
                answer="I don't have that information in my sources.",
                evidence_ids=[],
                abstained=True,
                limitations=[*answer.limitations, "No evidence was available."],
            ),
            [
                *fallbacks,
                FallbackRecord(
                    stage="validate_citations",
                    cause="answer_without_evidence",
                    action="force_abstention",
                    result="abstained",
                ),
            ],
        )
    return answer.model_copy(update={"evidence_ids": used}), fallbacks
