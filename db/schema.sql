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
    parent_id text,
    created_at timestamptz default now()
);

-- Fast filtering by aircraft
create index if not exists idx_documents_aircraft on documents (aircraft);

-- Join path for parent-child retrieval
create index if not exists idx_documents_parent_id on documents (parent_id);

-- Vector similarity search. HNSW is chosen over IVFFlat: better recall,
-- no training step, and it works correctly even on an empty table
-- (IVFFlat indexes built on empty tables perform poorly until reindexed).
create index if not exists idx_documents_embedding on documents
using hnsw (embedding vector_cosine_ops);

-- Parent chunks: larger context windows, NOT embedded.
-- Returned to the LLM for richer answer generation.
create table if not exists parent_chunks (
    id bigserial primary key,
    aircraft text not null,
    font text not null,
    parent_id text unique not null,
    texto text not null,
    created_at timestamptz default now()
);

create index if not exists idx_parent_chunks_parent_id on parent_chunks (parent_id);

-- Full-text search: generated tsvector column for keyword matching.
-- Postgres computes it automatically; no ingestion changes needed.
-- regconfig 'english' because the source material is in English.
alter table documents
    add column if not exists texto_tsv tsvector
    generated always as (to_tsvector('english', texto)) stored;

-- GIN inverted index: lexeme → posting list of chunk IDs.
-- Chosen over GiST because the corpus is write-once, query-many.
create index if not exists idx_documents_tsv
    on documents using gin (texto_tsv);

-- One-time cleanup: legacy function from the old `documentos` schema.
drop function if exists buscar_similares;

-- Legacy similarity search (direct chunk matching, no parent-child).
-- Kept as fallback for chunks without a parent_id.
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

-- Parent-child similarity search.
-- Searches child embeddings, deduplicates by parent, returns parent texts.
-- Only considers children that have a parent_id.
create or replace function find_similar_parents(
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
    select texto, aircraft, font, chunk_id, similarity
    from (
        select
            p.texto,
            p.aircraft,
            p.font,
            p.parent_id as chunk_id,
            1 - (d.embedding <=> query_embedding) as similarity,
            row_number() over (
                partition by d.parent_id
                order by d.embedding <=> query_embedding
            ) as rn
        from documents d
        join parent_chunks p on d.parent_id = p.parent_id
        where (aircraft_filter is null or d.aircraft = aircraft_filter)
          and d.parent_id is not null
    ) sub
    where rn = 1
    order by similarity desc
    limit top_k
$$;

-- Hybrid search: vector + keyword fused with RRF (Reciprocal Rank Fusion).
-- Two independent search legs (HNSW for vectors, GIN for keywords) each
-- return top candidates by rank. RRF merges by summing 1/(60+rank) per
-- document — no score normalisation needed because only positions matter.
-- When the keyword leg finds nothing (long or vague questions), the
-- vector leg carries the result alone: graceful degradation by design.
create or replace function find_similar_parents_hybrid(
    query_embedding vector(1536),
    query_text text,
    aircraft_filter text default null,
    top_k int default 5,
    candidates int default 30
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
    with vec as (
        select d.parent_id,
               row_number() over (order by d.embedding <=> query_embedding) as rnk
        from documents d
        where d.parent_id is not null
          and (aircraft_filter is null or d.aircraft = aircraft_filter)
        order by d.embedding <=> query_embedding
        limit candidates
    ),
    kw as (
        select d.parent_id,
               row_number() over (
                   order by ts_rank(d.texto_tsv, t.q) desc
               ) as rnk
        from documents d
        cross join lateral (
            select string_agg(lexeme, ' | ' order by lexeme)::tsquery as q
            from unnest(tsvector_to_array(to_tsvector('english', query_text))) as lex(lexeme)
        ) t
        where d.parent_id is not null
          and (aircraft_filter is null or d.aircraft = aircraft_filter)
          and t.q is not null
          and d.texto_tsv @@ t.q
        order by ts_rank(d.texto_tsv, t.q) desc
        limit candidates
    ),
    fused as (
        select parent_id, sum(1.0 / (60 + rnk)) as score
        from (
            select parent_id, rnk from vec
            union all
            select parent_id, rnk from kw
        ) ambas
        group by parent_id
    )
    select p.texto, p.aircraft, p.font, p.parent_id as chunk_id, f.score as similarity
    from fused f
    join parent_chunks p on p.parent_id = f.parent_id
    order by f.score desc
    limit top_k
$$;
