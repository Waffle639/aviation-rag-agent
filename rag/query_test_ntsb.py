"""Interactive natural-language query against the local NTSB PostgreSQL index.

Usage:
    python -m rag.query_test_ntsb
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "query_ntsb.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

from rag.ntsb_pipeline import generate_ntsb_answer  # noqa: E402
from rag.guardrails import GuardrailError, RAG_SECURITY, _get_detector  # noqa: E402


if __name__ == "__main__":
    if RAG_SECURITY:
        print("Loading Prompt Guard from local cache...")
        try:
            _get_detector()
        except GuardrailError as exc:
            print(f"\nSecurity startup failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print()

    print("NTSB aviation index query")
    print("Example: What aviation accidents occurred in California during 2024?")
    question = input("Question: ")
    try:
        print(f"\n{generate_ntsb_answer(question)}")
    except GuardrailError as exc:
        print(f"\nBlocked: {exc}")
    except Exception as exc:
        print(f"\nNTSB query failed: {exc}")
