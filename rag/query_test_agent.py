"""Interactive CLI for the controlled aviation agent."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from agent.dependencies import AgentDependencies
from agent.service import AviationAgentService
from rag.guardrails import GuardrailError, RAG_SECURITY, warmup_security


def _print_summary(result, *, verbose: bool) -> None:
    route = result.route
    print("\nRoute:")
    if route is None:
        print("  none")
    else:
        sources = ", ".join(route.sources) if route.sources else "none"
        print(f"  route: {route.route}")
        print(f"  sources: {sources}")
        print(f"  reason: {route.reason}")
        if verbose and route.document_query:
            print(f"  document_query: {route.document_query}")
        if verbose and route.accident_question:
            print(f"  accident_question: {route.accident_question}")

    print("\nTools:")
    if not result.tool_calls:
        print("  none")
    for call in result.tool_calls:
        extra = f", matches={call.total_matches}" if call.total_matches is not None else ""
        status = call.status if not call.error else f"{call.status}: {call.error}"
        print(f"  {call.tool_name}: {status}, evidence={call.evidence_count}{extra}, {call.latency_ms:.0f} ms")

    print("\nFallbacks:")
    if not result.fallbacks:
        print("  none")
    for fallback in result.fallbacks:
        print(f"  {fallback.stage}: {fallback.action} ({fallback.cause})")

    if verbose:
        print("\nEvidence:")
        if not result.evidence:
            print("  none")
        for item in result.evidence:
            record = f" record={item.source_record_id}" if item.source_record_id else ""
            print(f"  {item.evidence_id}: {item.source_kind} {item.source_name}{record}")

    if result.warnings:
        print("\nWarnings:")
        for warning in result.warnings:
            print(f"  - {warning}")

    print("\nAnswer:")
    print(result.answer)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Query the controlled aviation agent.")
    parser.add_argument("question", nargs="*", help="Question to ask. If omitted, interactive mode starts.")
    parser.add_argument("--verbose", action="store_true", help="Show route details and evidence IDs.")
    parser.add_argument("--graph", action="store_true", help="Print the graph as Mermaid and exit.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.graph:
        service = AviationAgentService(AgentDependencies())
        print(service.draw_mermaid())
        return

    if RAG_SECURITY:
        print("Loading Prompt Guard from local cache...")
        try:
            warmup_security()
        except GuardrailError as exc:
            print(f"\nSecurity startup failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print()

    service = AviationAgentService()

    if args.question:
        question = " ".join(args.question)
        result = await service.arun(question)
        _print_summary(result, verbose=args.verbose)
        return

    print("Controlled aviation agent query")
    print("Type 'exit' to quit.\n")
    while True:
        question = input("Question: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        try:
            result = await service.arun(question)
            _print_summary(result, verbose=args.verbose)
        except Exception as exc:
            print(f"Error: {exc}")
        print()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
