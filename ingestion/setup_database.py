"""
Database schema setup.

Applies db/schema.sql to the Supabase Postgres database through a direct
psycopg2 connection (DATABASE_URL). This is the one-time DDL step:
pgvector extension, the `documents` table, its indexes, and the
`find_similar` RPC function.

Guarantees:
  - Idempotent: every statement uses IF NOT EXISTS / CREATE OR REPLACE,
    so re-running always completes any missing piece.
  - Fails fast with a clear message if DATABASE_URL is not configured.

Execution model: statements are executed ONE BY ONE in autocommit mode,
exactly like the Supabase SQL Editor. Sending the whole file as a single
multi-statement query is NOT reliable through the Supabase pooler:
middle statements can be silently skipped (observed in practice: the
CREATE TABLE vanished while CREATE EXTENSION and CREATE FUNCTION applied).

Usage:
    python ingestion/setup_database.py
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

SCHEMA_PATH = "db/schema.sql"


def load_statements(path):
    """
    Reads the schema file and splits it into individual statements.

    Full-line comments are stripped BEFORE splitting, so ";" characters
    inside comments cannot break the split. Still relies on schema.sql
    not using ";" inside function bodies (see the warning at the top of
    that file).
    """
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f if not line.strip().startswith("--")]
    sql = "".join(lines)
    return [s.strip() for s in sql.split(";") if s.strip()]


def main():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

    # Fail fast with a clear message instead of a cryptic auth error
    if not database_url or "YOUR-PASSWORD" in database_url:
        sys.exit(
            "ERROR: DATABASE_URL is missing or still contains the "
            "[YOUR-PASSWORD] placeholder.\n"
            "Set the real database password in .env "
            "(Supabase Dashboard -> Project Settings -> Database).\n"
            "Tip: if the password contains @ # : / ? & it must be "
            "URL-encoded (e.g. @ -> %40, # -> %23)."
        )

    statements = load_statements(SCHEMA_PATH)

    connection = psycopg2.connect(database_url)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

            # Verify every schema object actually exists afterwards.
            # Expected: extension=1, table=1, indexes=4, function=1.
            cursor.execute("""
                select
                    (select count(*) from pg_extension
                     where extname = 'vector'),
                    (select count(*) from information_schema.tables
                     where table_schema = 'public' and table_name = 'documents'),
                    (select count(*) from information_schema.tables
                     where table_schema = 'public' and table_name = 'parent_chunks'),
                    (select count(*) from pg_indexes
                     where tablename = 'documents'),
                    (select count(*) from pg_indexes
                     where tablename = 'parent_chunks'),
                    (select count(*) from pg_proc p
                     join pg_namespace n on n.oid = p.pronamespace
                     where n.nspname = 'public' and p.proname = 'find_similar'),
                    (select count(*) from pg_proc p
                     join pg_namespace n on n.oid = p.pronamespace
                     where n.nspname = 'public' and p.proname = 'find_similar_parents')
            """)
            extension, table_docs, table_parents, idx_docs, idx_parents, func_similar, func_similar_parents = cursor.fetchone()
    finally:
        connection.close()

    print(f"extension vector:             {'OK' if extension == 1 else 'MISSING'}")
    print(f"table documents:              {'OK' if table_docs == 1 else 'MISSING'}")
    print(f"table parent_chunks:          {'OK' if table_parents == 1 else 'MISSING'}")
    print(f"indexes documents (exp 5):    {idx_docs}")
    print(f"indexes parent_chunks (exp 2): {idx_parents}")
    print(f"function find_similar:        {'OK' if func_similar == 1 else 'MISSING'}")
    print(f"function find_similar_parents:{'OK' if func_similar_parents == 1 else 'MISSING'}")

    if not (extension == 1 and table_docs == 1 and table_parents == 1
            and idx_docs == 5 and idx_parents == 2
            and func_similar == 1 and func_similar_parents == 1):
        sys.exit("ERROR: schema verification failed. Check the output above.")

    print("Schema applied and verified successfully.")


if __name__ == "__main__":
    main()
