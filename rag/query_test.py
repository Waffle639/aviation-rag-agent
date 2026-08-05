"""
Interactive query test.

Console stays clean: only the question prompt and the final answer.
Everything else (retrieved chunks with scores, full prompt, raw model
response) goes to logs/query.log, which is gitignored.

Usage:
    python -m rag.query_test
"""

import logging
import os

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

    # Console: only warnings and errors. INFO detail lives in the file.
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    root.addHandler(console)


# Must run BEFORE importing rag.generator: ingestion.embedder calls
# logging.basicConfig() at import time, and basicConfig is a no-op when
# the root logger already has handlers. Configuring first wins.
setup_logging()

from rag.generator import generate_answer  # noqa: E402

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    question = input("Question: ")

    logger.info("=" * 60)
    logger.info("NEW QUERY")
    logger.info("Question: %s", question)

    answer = generate_answer(question)

    logger.info("Final answer: %s", answer)
    print(answer)
