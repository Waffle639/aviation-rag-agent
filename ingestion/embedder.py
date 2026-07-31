import json
import logging
import os
import time

import psycopg2
from dotenv import load_dotenv
from openai import APIError, OpenAI, RateLimitError
from pgvector import Vector
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_values

load_dotenv()

# --- Configuration -----------------------------------------------------------

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100       
MAX_RETRIES = 5
CHUNKS_ROUTE = "data/processed/chunks"

UPSERT_SQL = """
    insert into documents (aircraft, font, chunk_id, texto, embedding)
    values %s
    on conflict (chunk_id) do update set
        aircraft = excluded.aircraft,
        font = excluded.font,
        texto = excluded.texto,
        embedding = excluded.embedding
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

missing = [v for v in ("OPENAI_API_KEY", "DATABASE_URL") if not os.getenv(v)]
if missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(missing)}. "
        "Copy .env.example to .env and fill in the values."
    )

if "YOUR-PASSWORD" in os.environ["DATABASE_URL"]:
    raise EnvironmentError(
        "DATABASE_URL still contains the [YOUR-PASSWORD] placeholder. "
        "Set the real database password (Supabase Dashboard -> "
        "Project Settings -> Database)."
    )

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

db_connection = psycopg2.connect(os.environ["DATABASE_URL"])
register_vector(db_connection)


# --- Pipeline steps ----------------------------------------------------------

def load_chunks(chunks_route=CHUNKS_ROUTE):

    chunks = []
    for aircraft in sorted(os.listdir(chunks_route)):
        aircraft_folder = os.path.join(chunks_route, aircraft)
        if not os.path.isdir(aircraft_folder):
            continue
        for filename in sorted(os.listdir(aircraft_folder)):
            if filename.endswith(".json"):
                with open(os.path.join(aircraft_folder, filename), encoding="utf-8") as f:
                    chunks.append(json.load(f))
    return chunks


def get_existing_chunk_ids():
    """
    Returns the set of chunk_ids already stored in `documents`.
    """
    with db_connection.cursor() as cursor:
        cursor.execute("select chunk_id from documents")
        return {row[0] for row in cursor.fetchall()}


def embed_batch(texts):
    """
    Converts a list of texts into embeddings with ONE API call.

    Args:
        texts (list[str]): up to BATCH_SIZE texts.

    Returns:
        list[list[float]]: one 1536-dim vector per input text, same order.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = openai_client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=texts,
            )
            return [item.embedding for item in response.data]
        except (RateLimitError, APIError) as e:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning(
                "Embedding request failed (%s). Retry %d/%d in %ds.",
                e, attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)


def upsert_batch(rows):
    """
    Upserts a batch of rows into `documents` in a single round-trip.

    Args:
        rows (list[tuple]): (aircraft, font, chunk_id, texto, Vector).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with db_connection.cursor() as cursor:
                execute_values(cursor, UPSERT_SQL, rows)
            db_connection.commit()
            return
        except Exception as e:
            db_connection.rollback()
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning(
                "Upsert failed (%s). Retry %d/%d in %ds.",
                e, attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)


def embed_text(text):
    """
    Converts a single text into an embedding with ONE API call.

    Args:
        text (str): the text to embed.

    Returns:
        list[float]: 1536-dim vector.
    """
    return embed_batch([text])[0]


def run(chunks_route=CHUNKS_ROUTE):
    """
    Full pipeline: load chunks -> skip already-ingested ones ->
    embed + upsert in batches -> report.

    A batch that fails after all retries does not stop the run: it is
    logged and reported at the end, and since it was never upserted,
    the next execution will retry it automatically.
    """
    chunks = load_chunks(chunks_route)
    existing = get_existing_chunk_ids()
    pending = [c for c in chunks if c["metadata"]["chunk_id"] not in existing]

    logger.info(
        "Loaded %d chunks: %d already ingested, %d pending.",
        len(chunks), len(chunks) - len(pending), len(pending),
    )

    failed = []
    try:
        for i in range(0, len(pending), BATCH_SIZE):
            batch = pending[i:i + BATCH_SIZE]
            try:
                vectors = embed_batch([c["texto"] for c in batch])
                rows = [
                    (
                        c["metadata"]["aeronave"],
                        c["metadata"]["fuente"],
                        c["metadata"]["chunk_id"],
                        c["texto"],
                        Vector(vector),
                    )
                    for c, vector in zip(batch, vectors)
                ]
                upsert_batch(rows)
                logger.info("Progress: %d/%d chunks ingested.", i + len(batch), len(pending))
            except Exception as e:
                failed.extend(c["metadata"]["chunk_id"] for c in batch)
                logger.error("Batch at index %d failed permanently: %s", i, e)
    finally:
        db_connection.close()

    logger.info("Done. Ingested: %d. Failed: %d.", len(pending) - len(failed), len(failed))
    if failed:
        logger.error("Failed chunk_ids (re-run the script to retry them): %s", failed)
        raise SystemExit(1)


if __name__ == "__main__":
    run()
