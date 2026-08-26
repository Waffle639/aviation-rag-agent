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

alter table documents add column if not exists document_id text;
alter table documents add column if not exists source_file text;
alter table documents add column if not exists token_count integer;

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

alter table parent_chunks add column if not exists document_id text;
alter table parent_chunks add column if not exists source_file text;
alter table parent_chunks add column if not exists token_count integer;

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

-- ---------------------------------------------------------------------------
-- Conversation memory
-- ---------------------------------------------------------------------------
-- Full transcripts are kept here. Only a compact summary plus bounded recent
-- messages are sent to the model on later turns.
create schema if not exists conversation;

create table if not exists conversation.sessions (
    id uuid primary key,
    user_id uuid,
    title text,
    summary jsonb not null default '{}'::jsonb,
    compacted_through integer not null default 0,
    version integer not null default 1,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists conversation.messages (
    id uuid primary key,
    session_id uuid not null references conversation.sessions(id) on delete cascade,
    sequence_number integer not null,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    token_count integer not null default 0,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (session_id, sequence_number)
);

create index if not exists idx_conversation_messages_session_sequence
    on conversation.messages (session_id, sequence_number desc);

create index if not exists idx_conversation_sessions_updated_at
    on conversation.sessions (updated_at desc);

create index if not exists idx_conversation_sessions_active_updated_at
    on conversation.sessions (updated_at desc)
    where archived_at is null;

-- ---------------------------------------------------------------------------
-- NTSB structured aviation case index
-- ---------------------------------------------------------------------------
-- NTSB data is kept as a relational read model, not mixed with the manual
-- vector corpus. The public API is used by the sync job; interactive queries
-- read these tables directly for exact counts, filters and rankings.
create schema if not exists ntsb;

create table if not exists ntsb.cases (
    mkey bigint primary key,
    ntsb_number text unique,
    event_date date,
    event_time time,
    city text,
    location text,
    state text,
    country text,
    country_code text,
    event_type text,
    severity text,
    investigation_status text,
    fatalities integer,
    serious_injuries integer,
    minor_injuries integer,
    total_injuries integer,
    narrative text,
    probable_cause text,
    airport text,
    runway text,
    source_updated_at timestamptz,
    synced_at timestamptz not null default now(),
    payload_hash text,
    search_tsv tsvector generated always as (
        to_tsvector('english', coalesce(ntsb_number, '') || ' ' || coalesce(city, '') || ' ' ||
        coalesce(location, '') || ' ' || coalesce(state, '') || ' ' || coalesce(country, '') || ' ' ||
        coalesce(event_type, '') || ' ' || coalesce(severity, '') || ' ' ||
        coalesce(investigation_status, '') || ' ' || coalesce(narrative, '') || ' ' ||
        coalesce(probable_cause, '') || ' ' || coalesce(airport, '') || ' ' || coalesce(runway, ''))
    ) stored
);

create table if not exists ntsb.aircraft (
    case_mkey bigint not null references ntsb.cases(mkey) on delete cascade,
    aircraft_sequence integer not null default 1,
    make text,
    model text,
    registration text,
    category text,
    operation text,
    damage text,
    primary key (case_mkey, aircraft_sequence)
);

create table if not exists ntsb.events (
    case_mkey bigint not null references ntsb.cases(mkey) on delete cascade,
    event_sequence integer not null default 1,
    event_text text not null,
    primary key (case_mkey, event_sequence)
);

create table if not exists ntsb.findings (
    case_mkey bigint not null references ntsb.cases(mkey) on delete cascade,
    finding_sequence integer not null default 1,
    finding_text text not null,
    primary key (case_mkey, finding_sequence)
);

create table if not exists ntsb.airports (
    case_mkey bigint not null references ntsb.cases(mkey) on delete cascade,
    airport_sequence integer not null default 1,
    airport_name text,
    runway text,
    primary key (case_mkey, airport_sequence)
);

create table if not exists ntsb.detail_cache (
    case_mkey bigint primary key references ntsb.cases(mkey) on delete cascade,
    payload jsonb not null,
    payload_hash text,
    fetched_at timestamptz not null default now()
);

create table if not exists ntsb.sync_state (
    stream text primary key,
    last_successful_start timestamptz,
    last_successful_end timestamptz,
    marker text,
    status text not null default 'idle',
    error text,
    updated_at timestamptz not null default now()
);

create table if not exists ntsb.sync_runs (
    run_id bigserial primary key,
    stream text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null default 'running',
    pages integer not null default 0,
    records_received integer not null default 0,
    cases_upserted integer not null default 0,
    details_fetched integer not null default 0,
    skipped_existing integer not null default 0,
    rejected integer not null default 0,
    error text
);

alter table ntsb.sync_runs add column if not exists skipped_existing integer not null default 0;

create index if not exists idx_ntsb_cases_event_date on ntsb.cases (event_date);
create index if not exists idx_ntsb_cases_ntsb_number on ntsb.cases (ntsb_number);
create index if not exists idx_ntsb_cases_country_code on ntsb.cases (country_code);
create index if not exists idx_ntsb_cases_state on ntsb.cases (state);
create index if not exists idx_ntsb_cases_severity on ntsb.cases (severity);
create index if not exists idx_ntsb_cases_fatalities on ntsb.cases (fatalities desc nulls last);
create index if not exists idx_ntsb_cases_total_injuries on ntsb.cases (total_injuries desc nulls last);
create index if not exists idx_ntsb_cases_source_updated on ntsb.cases (source_updated_at);
create index if not exists idx_ntsb_cases_search_tsv on ntsb.cases using gin (search_tsv);
create index if not exists idx_ntsb_aircraft_registration on ntsb.aircraft (upper(registration));
create index if not exists idx_ntsb_aircraft_make on ntsb.aircraft (lower(make));
create index if not exists idx_ntsb_aircraft_model on ntsb.aircraft (lower(model));
create index if not exists idx_ntsb_events_case_mkey on ntsb.events (case_mkey);
create index if not exists idx_ntsb_findings_case_mkey on ntsb.findings (case_mkey);
create index if not exists idx_ntsb_airports_case_mkey on ntsb.airports (case_mkey);
create index if not exists idx_ntsb_detail_cache_fetched_at on ntsb.detail_cache (fetched_at);

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
    with vec_scores as (
        select d.parent_id,
               min(d.embedding <=> query_embedding) as distance
        from documents d
        where d.parent_id is not null
          and (aircraft_filter is null or d.aircraft = aircraft_filter)
        group by d.parent_id
        order by distance
        limit candidates
    ),
    vec as (
        select parent_id, row_number() over (order by distance) as rnk
        from vec_scores
    ),
    kw_scores as (
        select d.parent_id,
               max(ts_rank(d.texto_tsv, t.q)) as keyword_score
        from documents d
        cross join lateral (
            select string_agg(lexeme, ' | ' order by lexeme)::tsquery as q
            from unnest(tsvector_to_array(to_tsvector('english', query_text))) as lex(lexeme)
        ) t
        where d.parent_id is not null
          and (aircraft_filter is null or d.aircraft = aircraft_filter)
          and t.q is not null
          and d.texto_tsv @@ t.q
        group by d.parent_id
        order by keyword_score desc
        limit candidates
    ),
    kw as (
        select parent_id, row_number() over (order by keyword_score desc) as rnk
        from kw_scores
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
