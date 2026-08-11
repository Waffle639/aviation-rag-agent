"""Load a versioned evaluation seed into the evaluation schema."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SEED = PROJECT_ROOT / "db" / "evaluation_seed_v1.sql"


def load_seed(database_url: str, seed_path: Path) -> tuple[int, int]:
    sql = seed_path.read_text(encoding="utf-8")
    connection = psycopg2.connect(database_url)
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                cursor.execute(
                    """
                    select
                        (select count(*) from evaluation.datasets),
                        (select count(*) from evaluation.cases)
                    """
                )
                dataset_count, case_count = cursor.fetchone()
        return dataset_count, case_count
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    args = parser.parse_args()

    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url or "YOUR-PASSWORD" in database_url:
        raise SystemExit(
            "DATABASE_URL is missing or still contains the placeholder. "
            "Run database setup first and configure .env."
        )
    if not args.seed.exists():
        raise SystemExit(f"Seed file does not exist: {args.seed}")

    dataset_count, case_count = load_seed(database_url, args.seed)
    print(
        f"Loaded evaluation seed from {args.seed}. "
        f"Database now contains {dataset_count} dataset(s) and {case_count} case(s)."
    )


if __name__ == "__main__":
    main()
