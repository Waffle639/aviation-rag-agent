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

-- ---------------------------------------------------------------------------
-- Evaluation registry
-- ---------------------------------------------------------------------------
-- Evaluation data is deliberately kept outside documents and parent_chunks.
-- Golden cases are expected answers; they must never become RAG context.
create schema if not exists evaluation;

create table if not exists evaluation.datasets (
    dataset_id text primary key,
    name text not null,
    version text not null,
    corpus_manifest_sha256 text,
    status text not null default 'draft'
        check (status in ('draft', 'active', 'retired')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (name, version)
);

create table if not exists evaluation.cases (
    case_id text primary key,
    dataset_id text not null references evaluation.datasets(dataset_id),
    question text not null,
    reference_answer text,
    answerable boolean not null,
    expected_abstention boolean not null default false,
    aircraft text,
    variant text,
    category text not null,
    difficulty text not null default 'medium',
    split text not null default 'development'
        check (split in ('development', 'validation', 'test')),
    expected_facts jsonb not null default '[]'::jsonb,
    expected_numbers jsonb not null default '[]'::jsonb,
    tags jsonb not null default '[]'::jsonb,
    status text not null default 'proposed'
        check (status in ('proposed', 'approved', 'rejected')),
    created_at timestamptz not null default now(),
    check (answerable or expected_abstention),
    check (answerable or reference_answer is null)
);

create index if not exists idx_eval_cases_dataset on evaluation.cases (dataset_id);
create index if not exists idx_eval_cases_category on evaluation.cases (category);
create index if not exists idx_eval_cases_aircraft on evaluation.cases (aircraft);

create table if not exists evaluation.evidence (
    evidence_id bigserial primary key,
    case_id text not null references evaluation.cases(case_id) on delete cascade,
    source_file text not null,
    document_id text,
    parent_id text,
    chunk_id text,
    line_start integer,
    line_end integer,
    quote text not null,
    relevance smallint not null check (relevance between 0 and 3),
    evidence_type text not null default 'direct',
    unique (case_id, source_file, line_start, line_end, quote)
);

create table if not exists evaluation.runs (
    run_id text primary key,
    dataset_id text not null references evaluation.datasets(dataset_id),
    run_name text not null,
    run_type text not null default 'evaluation'
        check (run_type in ('baseline', 'evaluation', 'ablation', 'online_sample')),
    git_commit text,
    corpus_version text,
    prompt_version text,
    config jsonb not null default '{}'::jsonb,
    model_versions jsonb not null default '{}'::jsonb,
    status text not null default 'running'
        check (status in ('running', 'completed', 'failed', 'cancelled')),
    started_at timestamptz not null default now(),
    ended_at timestamptz,
    total_cost numeric,
    total_latency_ms double precision
);

create table if not exists evaluation.case_runs (
    case_run_id bigserial primary key,
    run_id text not null references evaluation.runs(run_id) on delete cascade,
    case_id text not null references evaluation.cases(case_id),
    answer text,
    abstained boolean,
    trace_id text,
    retrieved_count integer,
    context_tokens integer,
    input_tokens integer,
    output_tokens integer,
    estimated_cost numeric,
    latency_ms double precision,
    timings jsonb not null default '{}'::jsonb,
    raw_output jsonb not null default '{}'::jsonb,
    unique (run_id, case_id)
);

create table if not exists evaluation.retrieved_items (
    retrieved_item_id bigserial primary key,
    case_run_id bigint not null references evaluation.case_runs(case_run_id) on delete cascade,
    rank integer not null check (rank > 0),
    document_id text,
    parent_id text,
    chunk_id text,
    aircraft text,
    variant text,
    vector_rank integer,
    keyword_rank integer,
    vector_score double precision,
    keyword_score double precision,
    rrf_score double precision,
    token_count integer,
    relevance smallint check (relevance between 0 and 3),
    is_duplicate boolean not null default false,
    unique (case_run_id, rank)
);

create table if not exists evaluation.context_items (
    context_item_id bigserial primary key,
    case_run_id bigint not null references evaluation.case_runs(case_run_id) on delete cascade,
    position integer not null check (position > 0),
    parent_id text,
    source_file text,
    token_count integer,
    selected boolean not null default true,
    unique (case_run_id, position)
);

create table if not exists evaluation.metrics (
    metric_id bigserial primary key,
    case_run_id bigint references evaluation.case_runs(case_run_id) on delete cascade,
    run_id text not null references evaluation.runs(run_id) on delete cascade,
    case_id text references evaluation.cases(case_id),
    metric_name text not null,
    score double precision,
    details jsonb not null default '{}'::jsonb,
    evaluator_version text not null,
    created_at timestamptz not null default now()
);

create index if not exists idx_eval_metrics_run on evaluation.metrics (run_id);
create index if not exists idx_eval_metrics_name on evaluation.metrics (metric_name);

create table if not exists evaluation.feedback (
    feedback_id text primary key,
    run_id text references evaluation.runs(run_id),
    case_id text references evaluation.cases(case_id),
    trace_id text,
    rating smallint check (rating between 1 and 5),
    label text,
    comment text,
    corrected_answer text,
    promoted_to_case boolean not null default false,
    created_at timestamptz not null default now()
);
