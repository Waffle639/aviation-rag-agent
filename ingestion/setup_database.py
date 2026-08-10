"""
Database schema setup.

Applies db/schema.sql to the Supabase Postgres database through a direct
psycopg2 connection (DATABASE_URL). This is the one-time DDL step:
pgvector extension, the `documents` table, its indexes, the
`parent_chunks` table, FTS support, and RPC functions.

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
    python -m ingestion.setup_database       # standalone
    python configure.py --db                 # via unified setup
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "db", "schema.sql",
)


def load_statements(path):
    with open(path, encoding="utf-8") as f:
        lines = [line for line in f if not line.strip().startswith("--")]
    sql = "".join(lines)
    return [s.strip() for s in sql.split(";") if s.strip()]


def verify_schema():
    database_url = os.getenv("DATABASE_URL")
    if not database_url or "YOUR-PASSWORD" in database_url:
        return False, (
            "DATABASE_URL is missing or still contains the placeholder. "
            "Set it in .env (Supabase Dashboard -> Project Settings -> Database)."
        )

    try:
        connection = psycopg2.connect(database_url, options="-c statement_timeout=10000")
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
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
                         where n.nspname = 'public' and p.proname = 'find_similar_parents'),
                        (select count(*) from pg_proc p
                         join pg_namespace n on n.oid = p.pronamespace
                         where n.nspname = 'public' and p.proname = 'find_similar_parents_hybrid')
                """)
                row = cursor.fetchone()
                assert row is not None, "Schema verification query returned no rows"
                (
                    extension, table_docs, table_parents,
                    idx_docs, idx_parents, func_similar,
                    func_similar_parents, func_similar_parents_hybrid,
                ) = row
        finally:
            connection.close()

        ok = (
            extension == 1
            and table_docs == 1
            and table_parents == 1
            and idx_docs == 6
            and idx_parents == 3
            and func_similar == 1
            and func_similar_parents == 1
            and func_similar_parents_hybrid == 1
        )
        if ok:
            return True, "Schema verified."
        return False, (
            f"Schema incomplete: extension={extension}, "
            f"documents={table_docs}, parent_chunks={table_parents}, "
            f"idx_docs={idx_docs}, idx_parents={idx_parents}, "
            f"find_similar={func_similar}, "
            f"find_similar_parents={func_similar_parents}, "
            f"find_similar_parents_hybrid={func_similar_parents_hybrid}"
        )
    except Exception as e:
        return False, f"Schema check failed: {e}"


def main():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")

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
    finally:
        connection.close()

    ok, msg = verify_schema()
    print(msg)
    if not ok:
        sys.exit("ERROR: schema verification failed. Check the output above.")

    print("Schema applied and verified successfully.")


if __name__ == "__main__":
    main()
