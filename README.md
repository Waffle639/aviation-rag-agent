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

Evaluation is baseline-first and DB-backed. Golden questions, expected answers
and evidence live in a separate `evaluation` PostgreSQL schema, never in the RAG
corpus tables. That separation matters: evaluation data is ground truth, not
retrievable context.

The initial dataset, `aviation_golden_v1`, contains 36 English cases built from
the downloaded TXT sources, including one explicit out-of-corpus question. A
corpus manifest records source files and hashes so a run can be tied back to the
exact documents it evaluated against.

The first goal is retrieval quality. For each case, evidence rows are converted
into qrels and compared with the ranked results returned by hybrid search. The
deterministic metrics currently tracked are `Recall@k`, `Precision@k`,
`HitRate@k`, `MRR`, `nDCG@k`, duplicate ratio, unique parent ratio, retrieved
item count and retrieved token count. These answer questions like: did we find
the right source, how high did it rank, and how much irrelevant context did we
send to generation?

The second goal is run observability. Each evaluated case stores the generated
answer, abstention decision, retrieved ranking, selected context, estimated
context tokens, model input/output tokens, latency and raw structured output.
This makes quality regressions debuggable instead of just reporting a pass/fail
score.

PostgreSQL is the source of truth for comparisons. `evaluation.runs` represents
one experiment, `evaluation.case_runs` stores per-question outputs,
`evaluation.retrieved_items` and `evaluation.context_items` preserve the evidence
path, and `evaluation.metrics` stores deterministic scores. Later runs can be
compared against `baseline-v1` by metric, case type, aircraft, source, latency or
token usage.

LangSmith is used as the visual trace layer. When tracing is enabled, each case
appears as `evaluation.<run-name>.<case-id>` with tags for `evaluation`, run
type, dataset and run name. The same LangSmith trace id is stored in
`evaluation.case_runs.trace_id`, so a failing DB row can be opened directly as a
trace showing retrieval, prompt construction, model call and final answer.

The next evaluation layer is generation quality: citation correctness,
faithfulness to retrieved context, answer correctness, numeric accuracy,
abstention accuracy and cost/latency trade-offs. Those are intentionally built on
top of the deterministic baseline instead of replacing it with an LLM judge too
early.

## What's next

- **NTSB as a second source** — accident records via a structured API, a different access pattern than vector search.
- **Routing agent (LangGraph)** — the question decides the path: manuals, accidents, or both. Explicit graph, no hidden abstractions.
- **Evaluation with RAGAS** — faithfulness and context recall, to attribute failures to retrieval or generation with numbers, not opinions.

## What "done" looks like

A system that answers questions about specific aircraft, always citing its source, and honest enough to say "I don't have that information" when the data isn't there. That last part is the hard one.
