import hashlib
import json
import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langsmith import traceable
from pgvector import Vector
from pgvector.psycopg2 import register_vector
import psycopg2
from psycopg2.extras import RealDictCursor

from ingestion.embedder import embed_text

load_dotenv()

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "evaluation_data" / "corpus_manifest.json"

db_connection = psycopg2.connect(
    os.environ["DATABASE_URL"],
    options="-c statement_timeout=10000",
)
register_vector(db_connection)


@lru_cache(maxsize=1)
def _manifest_by_path():
    if not MANIFEST_PATH.exists():
        return {}
    with MANIFEST_PATH.open(encoding="utf-8") as file:
        manifest = json.load(file)
    return {
        document["path"]: document
        for document in manifest.get("documents", [])
        if document.get("path") and document.get("document_id")
    }


def _document_id_from_source_file(source_file):
    if not source_file or not str(source_file).startswith("data/raw/"):
        return None
    relative = str(source_file)[len("data/raw/"):]
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]


def _candidate_source_files(row):
    source_file = row.get("source_file")
    if source_file:
        yield str(source_file)

    aircraft = str(row.get("aircraft") or "").strip()
    font = str(row.get("font") or "").strip().lower()
    if not aircraft:
        return

    names = [aircraft]
    underscored = aircraft.replace(" ", "_")
    if underscored != aircraft:
        names.append(underscored)

    for name in names:
        if font == "wiki" or "wiki" in font:
            yield f"data/raw/wiki/{name}.txt"
        elif font in {"pdf", "pdf_text"} or "pdf" in font:
            yield f"data/raw/pdf_to_txt/{name}.txt"


def _fill_missing_metadata(rows):
    manifest = _manifest_by_path()
    filled = []
    for raw_row in rows:
        row = dict(raw_row)
        matched_source_file = None
        for source_file in _candidate_source_files(row):
            document = manifest.get(source_file)
            if document:
                row["document_id"] = row.get("document_id") or document["document_id"]
                row["source_file"] = row.get("source_file") or source_file
                matched_source_file = source_file
                break
            if row.get("document_id") is None:
                document_id = _document_id_from_source_file(source_file)
                if document_id:
                    row["document_id"] = document_id
                    row["source_file"] = row.get("source_file") or source_file
                    matched_source_file = source_file
                    break

        if row.get("token_count") is None:
            row["token_count"] = (len(str(row.get("texto") or "")) + 3) // 4
        if matched_source_file and not row.get("source_file"):
            row["source_file"] = matched_source_file
        filled.append(row)
    return filled


@traceable(run_type="retriever", name="hybrid_search")
def search_context(question, aircraft=None, top_k=5):
    query_vector = embed_text(question)

    with db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            select
                h.texto,
                h.aircraft,
                h.font,
                h.chunk_id,
                h.chunk_id as parent_id,
                p.document_id,
                p.source_file,
                p.token_count,
                h.similarity,
                h.similarity as rrf_score
            from find_similar_parents_hybrid(%s, %s, %s, %s) h
            left join parent_chunks p on p.parent_id = h.chunk_id
            order by h.similarity desc
            """,
            (Vector(query_vector), question, aircraft, top_k),
        )
        results = _fill_missing_metadata(cursor.fetchall())

    logger.info(
        "Retrieved %d parent chunks: %s",
        len(results),
        [(r["chunk_id"], round(r["similarity"], 4)) for r in results],
    )
    return results
