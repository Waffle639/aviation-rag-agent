"""
Interactive query test.

Usage:
    python -m rag.query_test
"""

import logging
import os
import sys

LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "query.log")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setLevel(logging.ERROR)
    root.addHandler(console)


setup_logging()

from rag.guardrails import GuardrailError, _get_detector, PROMPT_GUARD_MODEL  # noqa: E402
from rag.generator import generate_answer  # noqa: E402

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    print("Loading Prompt Guard...")
    _get_detector()
    print()

    question = input("Question: ")

    logger.info("=" * 60)
    logger.info("NEW QUERY")
    logger.info("Question: %s", question)

    try:
        answer = generate_answer(question)
    except GuardrailError as e:
        logger.info("Guardrail blocked query: %s", e)
        print(f"\nBlocked: {e}")
        sys.exit(1)

    logger.info("Final answer: %s", answer)
    print(f"\n{answer}")
