# Aviation RAG Agent

A RAG system that answers technical questions about aircraft using official manuals and spec sheets. Built from scratch — no LangChain abstractions — so every layer of the stack (ingestion, chunking, embeddings, vector search, grounded generation) is an explicit, observable decision.

## Pipeline

```
PDF manuals + Wikipedia extracts
        ↓
cleaning and parent-child chunking
        ↓
embeddings + tsvector generation
        ↓
Supabase + pgvector (HNSW) + GIN full-text index
        ↓
hybrid search (vector + keyword, RRF fusion) → dedupe → parents
        ↓
grounded generation with citations + guardrails
```

## Setup

```bash
python configure.py  # guided setup: database, local security model, smoke test
```

One command handles everything. Configuration lives in `.env` (see `.env.example`).

## Design decisions

**Parent-child chunking.** Small children (~500 chars) are embedded for precise matching; their paragraph-aligned parents (~2000 chars) are what the model actually sees. Search small, return big.

**Hybrid search (vector + keyword, RRF).** Pure vector search loses exact tokens like "Vso" or "V1". HNSW handles semantic similarity, a GIN full-text index handles lexical matching, and Reciprocal Rank Fusion merges both by rank position — no score normalisation needed. The RRF logic lives as a PostgreSQL function (`find_similar_parents_hybrid`), so the fusion happens inside the database, not in application code.

**HNSW over IVFFlat.** Better recall, no training step — and no degraded index while the table is still empty.

**Idempotent ingestion.** Stable chunk IDs and upserts: re-running the pipeline never duplicates or re-embeds. API failures retry with backoff; failed batches are reported by ID for selective retries.

**Grounded generation.** The model answers only from retrieved context, cites aircraft and source, reports discrepancies between sources instead of silently picking one — and says "I don't have that information" when the data isn't there.

## Security

- **Local prompt-injection detector.** Meta's Prompt Guard 2 runs on CPU — questions never leave the machine, and its ~100ms is invisible next to generation. The same classifier scans user questions at query time and every chunk at ingestion: defense at the two points where untrusted text enters the system.
- **Fine-tuned on aviation data.** The base model knows generic injection patterns. A fine-tuned variant (`models/prompt-guard-aviation/`) tightens the decision boundary for this domain — see `notebooks/finetune_prompt_guard.ipynb`.
- **Defense in depth.** OpenAI Moderation screens both input and output, the prompt treats retrieved context strictly as data (never instructions), and answers are scanned for system-prompt leaks.
- **Fail-closed, human in the loop.** Guardrails gate behind a single switch (`RAG_SECURITY`, on by default); at query time a missing detector raises instead of silently degrading. Flagged ingestion chunks are logged for human review, never auto-deleted — aviation documents produce false positives.

## Tests

Unit, integration and e2e tests covering chunking logic, guardrail behaviour and the full query pipeline. Run with `pytest`.

## Evaluation

The evaluation registry lives in the separate `evaluation` PostgreSQL schema. It
is intentionally not part of the RAG corpus tables: golden cases are expected
answers and must never be retrieved as context.

Create a local corpus manifest and validate the initial English dataset without
database credentials:

```bash
python -m evaluation.manifest
python -m evaluation.validate_dataset
```

After configuring `DATABASE_URL`, apply the normal schema and load the first
evaluation seed:

```bash
python -m ingestion.setup_database
python -m evaluation.load_dataset
```

The seed contains 36 proposed cases based on the downloaded TXT sources,
including one explicit out-of-corpus question. The first run against this fixed
dataset will become `baseline-v1`; later retrieval and generation experiments
are stored as separate evaluation runs and compared with that baseline.

Run the current RAG against the dataset and persist the structured traces:

```bash
python -m evaluation.runner --dataset aviation_golden_v1 --run-name baseline-v1 --run-type baseline
```

This baseline runner needs a configured `DATABASE_URL`, an indexed corpus in the
RAG tables, and `OPENAI_API_KEY`. It stores each answer, retrieval list, selected
context, token counts and timings under `evaluation.runs` and related tables.

## What's next

- **NTSB as a second source** — accident records via a structured API, a different access pattern than vector search.
- **Routing agent (LangGraph)** — the question decides the path: manuals, accidents, or both. Explicit graph, no hidden abstractions.
- **Evaluation with RAGAS** — faithfulness and context recall, to attribute failures to retrieval or generation with numbers, not opinions.

## What "done" looks like

A system that answers questions about specific aircraft, always citing its source, and honest enough to say "I don't have that information" when the data isn't there. That last part is the hard one.
