"""Interactive CLI for the aviation agent with persistent conversation memory."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid

from dotenv import load_dotenv

from agent.memory import PostgresConversationMemoryStore
from agent.service import AviationAgentService, build_default_dependencies
from rag.guardrails import GuardrailError, RAG_SECURITY, warmup_security
from rag.query_test_agent import _print_summary


def _parse_session_id(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("session must be a valid UUID") from exc


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Query the aviation agent with persistent memory.")
    parser.add_argument("question", nargs="*", help="Question to ask. If omitted, interactive mode starts.")
    parser.add_argument("--session", type=_parse_session_id, help="Existing conversation session UUID to load.")
    parser.add_argument("--verbose", action="store_true", help="Show route details and evidence IDs.")
    parser.add_argument("--graph", action="store_true", help="Print the graph as Mermaid and exit.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    load_dotenv()

    if args.graph:
        service = AviationAgentService(build_default_dependencies())
        print(service.draw_mermaid())
        return

    store = PostgresConversationMemoryStore()
    if args.session:
        if not store.session_exists(args.session):
            print(f"Conversation session not found: {args.session}", file=sys.stderr)
            sys.exit(1)
        session_id = args.session
        print(f"Loaded conversation session: {session_id}")
    else:
        session_id = store.create_session()
        print(f"Created conversation session: {session_id}")
        print(f"Continue it later with: python -m rag.query_test_memory --session {session_id}")

    if RAG_SECURITY:
        print("Loading Prompt Guard from local cache...")
        try:
            warmup_security()
        except GuardrailError as exc:
            print(f"\nSecurity startup failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print()

    deps = build_default_dependencies()
    deps.memory_store = store
    service = AviationAgentService(deps)

    if args.question:
        question = " ".join(args.question)
        result = await service.arun(question, session_id=session_id)
        _print_summary(result, verbose=args.verbose)
        return

    print("Controlled aviation agent query with memory")
    print("Type 'exit' to quit.\n")
    while True:
        question = input("Question: ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        try:
            result = await service.arun(question, session_id=session_id)
            _print_summary(result, verbose=args.verbose)
        except Exception as exc:
            print(f"Error: {exc}")
        print()


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
