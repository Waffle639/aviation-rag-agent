import os

from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg2 import register_vector
import psycopg2
from psycopg2.extras import RealDictCursor

from ingestion.embedder import embed_text

load_dotenv()

db_connection = psycopg2.connect(os.environ["DATABASE_URL"])
register_vector(db_connection)


def search_context(question, aircraft=None, top_k=5):
    query_vector = embed_text(question)

    with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "SELECT * FROM find_similar_parents(%s, %s, %s)",
            (Vector(query_vector), aircraft, top_k),
        )
        results = cursor.fetchall()

        if not results:
            cursor.execute(
                "SELECT * FROM find_similar(%s, %s, %s)",
                (Vector(query_vector), aircraft, top_k),
            )
            results = cursor.fetchall()

        return results
