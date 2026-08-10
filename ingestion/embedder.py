import json
import logging
import os
import time

import psycopg2
from dotenv import load_dotenv
from langsmith import traceable, tracing_context
from langsmith.wrappers import wrap_openai
from openai import APIError, OpenAI, RateLimitError
from pgvector import Vector
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_values

load_dotenv()

EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 100
MAX_RETRIES = 5
CHUNKS_ROUTE = "data/processed/chunks"
PARENTS_ROUTE = "data/processed/parents"

UPSERT_CHILD_SQL = """
    insert into documents (aircraft, font, chunk_id, texto, embedding, parent_id)
    values %s
    on conflict (chunk_id) do update set
        aircraft = excluded.aircraft,
        font = excluded.font,
        texto = excluded.texto,
        embedding = excluded.embedding,
        parent_id = excluded.parent_id
"""

UPSERT_PARENT_SQL = """
    insert into parent_chunks (aircraft, font, parent_id, texto)
    values %s
    on conflict (parent_id) do update set
        aircraft = excluded.aircraft,
        font = excluded.font,
        texto = excluded.texto
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

openai_client = wrap_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

db_connection = psycopg2.connect(
    os.environ["DATABASE_URL"],
    options="-c statement_timeout=10000",
)
register_vector(db_connection)


def _load_json_files(route):
    items = []
    for entity in sorted(os.listdir(route)):
        entity_path = os.path.join(route, entity)
        if not os.path.isdir(entity_path):
            continue
        for filename in sorted(os.listdir(entity_path)):
            if filename.endswith(".json"):
                with open(os.path.join(entity_path, filename), encoding="utf-8") as f:
                    items.append(json.load(f))
    return items


def load_chunks(chunks_route=CHUNKS_ROUTE):
    return _load_json_files(chunks_route)


def load_parents(parents_route=PARENTS_ROUTE):
    return _load_json_files(parents_route)


def get_existing_chunk_ids():
    with db_connection.cursor() as cursor:
        cursor.execute("select chunk_id from documents")
        return {row[0] for row in cursor.fetchall()}


def get_existing_parent_ids():
    with db_connection.cursor() as cursor:
        cursor.execute("select parent_id from parent_chunks")
        return {row[0] for row in cursor.fetchall()}


# wrap_openai no parchea embeddings.create: se traza con @traceable.
# Un run por lote (100 textos en ingesta, 1 en queries).
@traceable(run_type="llm", name="openai_embedding")
def embed_batch(texts):
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
    raise RuntimeError("embed_batch: unexpected end of retry loop")


def _upsert_with_retry(sql, rows, label):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with db_connection.cursor() as cursor:
                execute_values(cursor, sql, rows)
            db_connection.commit()
            return
        except Exception as e:
            db_connection.rollback()
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            logger.warning(
                "%s upsert failed (%s). Retry %d/%d in %ds.",
                label, e, attempt, MAX_RETRIES, wait,
            )
            time.sleep(wait)


def upsert_child_batch(rows):
    _upsert_with_retry(UPSERT_CHILD_SQL, rows, "Child")


def upsert_parent_batch(rows):
    _upsert_with_retry(UPSERT_PARENT_SQL, rows, "Parent")


def embed_text(text):
    return embed_batch([text])[0]


def _scan_ingestion_chunks(children):
    try:
        from rag.guardrails import RAG_SECURITY
    except ImportError:
        logger.info("guardrails module not importable — skipping ingestion scan.")
        return [], []

    if not RAG_SECURITY:
        logger.info("RAG_SECURITY is disabled — skipping ingestion scan.")
        return [], []

    try:
        from rag.guardrails import _get_detector
        detector = _get_detector()
        if detector is None:
            logger.info("Prompt Guard detector not available — skipping ingestion scan.")
            return [], []
    except Exception as e:
        logger.info("Prompt Guard not available (%s) — skipping ingestion scan.", e)
        return [], []

    suspicious = []
    failed_scan = []
    total = len(children)
    for i, chunk in enumerate(children, 1):
        text = chunk.get("texto", "")
        chunk_id = chunk.get("metadata", {}).get("chunk_id", "?")
        try:
            label, score = detector.classify(text)
            if label == "MALICIOUS":
                suspicious.append((chunk_id, score, text[:120]))
        except Exception as e:
            failed_scan.append((chunk_id, str(e)))
        if i % 50 == 0 or i == total:
            logger.info("Scan progress: %d/%d chunks.", i, total)

    if suspicious:
        logger.warning(
            "PROMPT GUARD: %d chunk(s) flagged as MALICIOUS (human review needed):",
            len(suspicious),
        )
        for chunk_id, score, preview in suspicious:
            logger.warning("  %s (score=%.4f): %s", chunk_id, score, preview)

    if failed_scan:
        logger.error(
            "Scan errors on %d chunk(s): %s",
            len(failed_scan),
            [cid for cid, _ in failed_scan],
        )

    logger.info(
        "Ingestion scan complete: %d scanned, %d suspicious, %d errors.",
        total, len(suspicious), len(failed_scan),
    )
    return suspicious, failed_scan


def run(chunks_route=CHUNKS_ROUTE, parents_route=PARENTS_ROUTE):
    with tracing_context(enabled=False):
        _run(chunks_route, parents_route)


def _run(chunks_route=CHUNKS_ROUTE, parents_route=PARENTS_ROUTE):
    children = load_chunks(chunks_route)
    parents = load_parents(parents_route)

    existing_chunks = get_existing_chunk_ids()
    existing_parents = get_existing_parent_ids()

    pending_children = [c for c in children if c["metadata"]["chunk_id"] not in existing_chunks]
    pending_parents = [p for p in parents if p["metadata"]["parent_id"] not in existing_parents]

    logger.info(
        "Loaded %d children (%d pending), %d parents (%d pending).",
        len(children), len(pending_children),
        len(parents), len(pending_parents),
    )

    _scan_ingestion_chunks(children)

    failed_children = []
    try:
        for i in range(0, len(pending_children), BATCH_SIZE):
            batch = pending_children[i:i + BATCH_SIZE]
            try:
                vectors = embed_batch([c["texto"] for c in batch])
                rows = [
                    (
                        c["metadata"]["aeronave"],
                        c["metadata"]["fuente"],
                        c["metadata"]["chunk_id"],
                        c["texto"],
                        Vector(vector),
                        c["metadata"]["parent_id"],
                    )
                    for c, vector in zip(batch, vectors)
                ]
                upsert_child_batch(rows)
                logger.info("Children: %d/%d ingested.", i + len(batch), len(pending_children))
            except Exception as e:
                failed_children.extend(c["metadata"]["chunk_id"] for c in batch)
                logger.error("Child batch at index %d failed permanently: %s", i, e)

        for i in range(0, len(pending_parents), BATCH_SIZE):
            batch = pending_parents[i:i + BATCH_SIZE]
            try:
                rows = [
                    (
                        p["metadata"]["aeronave"],
                        p["metadata"]["fuente"],
                        p["metadata"]["parent_id"],
                        p["texto"],
                    )
                    for p in batch
                ]
                upsert_parent_batch(rows)
                logger.info("Parents: %d/%d ingested.", i + len(batch), len(pending_parents))
            except Exception as e:
                logger.error("Parent batch at index %d failed permanently: %s", i, e)
    finally:
        db_connection.close()

    logger.info("Done. Children ingested: %d. Failed children: %d.", len(pending_children) - len(failed_children), len(failed_children))
    if failed_children:
        logger.error("Failed child chunk_ids (re-run to retry): %s", failed_children)
        raise SystemExit(1)


if __name__ == "__main__":
    run()
