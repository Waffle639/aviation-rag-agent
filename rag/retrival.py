import logging
import os

from dotenv import load_dotenv
from langsmith import traceable
from pgvector import Vector
from pgvector.psycopg2 import register_vector
import psycopg2
from psycopg2.extras import RealDictCursor

from ingestion.embedder import embed_text

load_dotenv()

logger = logging.getLogger(__name__)

db_connection = psycopg2.connect(os.environ["DATABASE_URL"])
register_vector(db_connection)


@traceable(run_type="retriever", name="hybrid_search")
def search_context(question, aircraft=None, top_k=5):
    query_vector = embed_text(question)

    with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            "SELECT * FROM find_similar_parents_hybrid(%s, %s, %s, %s)",
            (Vector(query_vector), question, aircraft, top_k),
        )
        results = cursor.fetchall()

    logger.info(
        "Retrieved %d parent chunks: %s",
        len(results),
        [(r["chunk_id"], round(r["similarity"], 4)) for r in results],
    )
    return results
