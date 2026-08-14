from pathlib import Path

import pytest


pytestmark = pytest.mark.integration_db


@pytest.fixture(scope="module")
def postgres_connection():
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip(
            "integration_db skipped: install testcontainers[postgres] to run it"
        )

    try:
        container = PostgresContainer("pgvector/pgvector:pg16")
        container.start()
    except Exception as exc:
        pytest.skip(f"integration_db skipped: Docker/pgvector unavailable ({exc})")

    connection = None
    try:
        import psycopg2

        connection = psycopg2.connect(container.get_connection_url())
        connection.autocommit = True
        schema_path = Path(__file__).parents[2] / "db" / "schema.sql"
        statements = [
            statement.strip()
            for statement in schema_path.read_text(encoding="utf-8").split(";")
            if statement.strip()
        ]
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        from pgvector.psycopg2 import register_vector

        register_vector(connection)
    except Exception as exc:
        if connection is not None:
            connection.close()
        container.stop()
        pytest.skip(f"integration_db skipped: could not initialize schema ({exc})")
    try:
        yield connection
    finally:
        connection.close()
        container.stop()


def _vector(first_value, second_value=0.0):
    return [first_value, second_value] + [0.0] * 1534


def _seed(connection):
    with connection.cursor() as cursor:
        cursor.execute("truncate documents, parent_chunks restart identity")
        cursor.executemany(
            "insert into parent_chunks (aircraft, font, parent_id, texto) values (%s, %s, %s, %s)",
            [
                ("Boeing 747", "manual", "parent-vector", "Vector result"),
                ("Boeing 747", "manual", "parent-keyword", "Rareword result"),
                ("Boeing 747", "manual", "parent-third", "Unrelated result"),
            ],
        )
        cursor.executemany(
            """
            insert into documents (aircraft, font, chunk_id, texto, embedding, parent_id)
            values (%s, %s, %s, %s, %s, %s)
            """,
            [
                ("Boeing 747", "manual", "child-vector", "vector evidence", _vector(1.0), "parent-vector"),
                ("Boeing 747", "manual", "child-keyword", "rareword evidence", _vector(0.9, 0.435), "parent-keyword"),
                 ("Boeing 747", "manual", "child-third", "unrelated evidence", _vector(0.0, 1.0), "parent-third"),
            ],
        )


def test_hybrid_rrf_fuses_vector_and_keyword_ranks(postgres_connection):
    _seed(postgres_connection)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "select chunk_id, similarity from find_similar_parents_hybrid(%s, %s, null, 3, 30)",
            (_vector(1.0), "rareword",),
        )
        rows = cursor.fetchall()

    assert [row[0] for row in rows] == [
        "parent-keyword",
        "parent-vector",
        "parent-third",
    ]
    assert rows[0][1] == pytest.approx(1 / 61 + 1 / 62)
    assert rows[1][1] == pytest.approx(1 / 61)


def test_hybrid_rrf_uses_vector_leg_when_keyword_has_no_match(postgres_connection):
    _seed(postgres_connection)
    with postgres_connection.cursor() as cursor:
        cursor.execute(
            "select chunk_id, similarity from find_similar_parents_hybrid(%s, %s, null, 3, 30)",
            (_vector(1.0), "term-that-is-not-in-corpus",),
        )
        rows = cursor.fetchall()

    assert [row[0] for row in rows] == [
        "parent-vector",
        "parent-keyword",
        "parent-third",
    ]
    assert rows[0][1] == pytest.approx(1 / 61)
