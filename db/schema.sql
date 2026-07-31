-- Aviation RAG Agent - database schema
-- Applied by ingestion/setup_database.py (or paste into the Supabase SQL Editor).
-- Every statement is idempotent: safe to run multiple times.
--
-- IMPORTANT for setup_database.py: this file is split on ";" and each
-- statement is executed separately (multi-statement queries are unreliable
-- through the Supabase pooler). Therefore function bodies must NOT contain
-- semicolons -- keep the single-statement body below without a trailing ";"

-- pgvector extension (one time per project)
create extension if not exists vector;

create table if not exists documents (
    id bigserial primary key,
    aircraft text not null,
    font text not null,
    chunk_id text unique not null,
    texto text not null,
    embedding vector(1536),
    created_at timestamptz default now()
);

-- Fast filtering by aircraft
create index if not exists idx_documents_aircraft on documents (aircraft);

-- Vector similarity search. HNSW is chosen over IVFFlat: better recall,
-- no training step, and it works correctly even on an empty table
-- (IVFFlat indexes built on empty tables perform poorly until reindexed).
create index if not exists idx_documents_embedding on documents
using hnsw (embedding vector_cosine_ops);

-- One-time cleanup: legacy function from the old `documentos` schema.
-- Its body referenced the dropped table, so it was broken.
drop function if exists buscar_similares;

-- Similarity search RPC used by the retriever.
-- Returns the top_k chunks closest to the query embedding, optionally
-- filtered by aircraft. similarity is cosine similarity in [0, 1].
create or replace function find_similar(
    query_embedding vector(1536),
    aircraft_filter text default null,
    top_k int default 5
)
returns table (
    texto text,
    aircraft text,
    font text,
    chunk_id text,
    similarity float
)
language sql stable
as $$
    select
        texto,
        aircraft,
        font,
        chunk_id,
        1 - (embedding <=> query_embedding) as similarity
    from documents
    where aircraft_filter is null or aircraft = aircraft_filter
    order by embedding <=> query_embedding
    limit top_k
$$;
