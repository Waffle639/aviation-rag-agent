# Aviation RAG Agent

[![Core RAG pipeline](assets/core-rag-pipeline.svg)](assets/core-rag-pipeline.svg)

This is not primarily a package for someone to download and run. It is a working case study: every important layer is implemented explicitly so that retrieval quality, context selection, latency and failure modes can be inspected instead of hidden behind a framework.

The corpus combines aircraft manuals, specification sheets and curated aviation extracts. The system answers technical questions with source-aware context, citations and an explicit abstention path when the evidence is missing.

## Why this project exists

The interesting problem is not generating fluent aviation text. It is deciding whether the answer is supported by the right evidence, then being able to explain why a change improved or damaged the system.

That leads to four design priorities:

- **Retrieval before generation:** improve the evidence path before tuning the prompt or model.
- **Context with structure:** search small units for precision, but give the model enough surrounding material to understand the fact.
- **Evaluation as a first-class system:** every experiment is stored, reproducible and comparable against a baseline.
- **Visibility over convenience:** the database, traces and dashboard preserve what happened at each stage.

The main path is deliberately small:

| Stage | What happens | Why it matters |
| --- | --- | --- |
| **Ingest** | PDFs and text extracts are cleaned, normalised and assigned stable provenance. | A result can be traced back to a document and source file. |
| **Structure** | Each document becomes larger `parent` windows and overlapping smaller `child` chunks. | Matching stays precise without starving generation of context. |
| **Index** | Child chunks receive embeddings; PostgreSQL builds a generated `tsvector` and GIN index. | Semantic and exact-term retrieval are available from the same corpus. |
| **Retrieve** | Vector and keyword rankings are fused with Reciprocal Rank Fusion, then collapsed to unique parents. | Exact aviation tokens and semantic questions can both succeed. |
| **Generate** | The model sees only selected parent context and must cite the aircraft and source. | The answer remains grounded and auditable. |
| **Evaluate** | Runs persist rankings, context, answers, timings, tokens and metrics. | A change can be judged by evidence, not by a convincing demo query. |

## Decisions that shape the system

### 1. Parent-child chunking

Chunking is implemented in `ingestion/chunking.py`, rather than delegated to a framework splitter.

```text
document
  -> paragraph-aligned parents      ~2,000 characters
  -> overlapping searchable children ~500 characters, 100 overlap
```

Children are embedded because small passages give more focused matches. Parents are not embedded; they are the richer context returned to the model. In short: **search small, return big**.

This also makes retrieval measurable at two levels: whether the right child was found, and whether the final parent context was useful without repeating the same document several times.

### 2. Hybrid search instead of vector-only search

Vector similarity is good at meaning, but it can underweight exact identifiers and aviation notation such as `V1`, `Vso`, model variants or part numbers. PostgreSQL therefore runs two independent retrieval legs:

- HNSW over `text-embedding-3-small` vectors.
- GIN full-text search over a generated English `tsvector` column.

The database function `find_similar_parents_hybrid` fuses ranks with:

```text
RRF(parent) = sum(1 / (60 + rank))
```

Rank fusion avoids putting cosine distance and keyword scores on an arbitrary shared scale. It also keeps the retrieval contract in the database, close to the indexes, rather than scattering ranking logic through application code.

### 3. Idempotent, observable ingestion

Stable document, parent and child IDs make ingestion safe to repeat. Children and parents are upserted separately, embedding calls run in batches, API and database operations retry with backoff, and failed child IDs are reported for selective re-runs.

Before indexing, every child is scanned for prompt injection. Suspicious or unscannable material blocks ingestion and is logged for review rather than silently discarded. This matters for technical documents because a false positive may still contain legitimate operational language.

### 4. Grounded generation with an abstention path

The generator receives retrieved context inside explicit data boundaries. Its contract is intentionally conservative:

- use only the supplied context;
- cite the aircraft and source;
- report conflicting values instead of choosing silently;
- preserve numeric precision;
- return `I don't have that information in my sources.` when the corpus does not support an answer.

Input validation, local Prompt Guard, OpenAI moderation and output leak checks form a fail-closed defence in depth. Security is applied when untrusted text enters the system: both at ingestion and at query time.

## NTSB integration

The project also includes a separate live-data path for structured aviation accident records from the NTSB public API. It does not add NTSB records to the PostgreSQL/vector corpus.

The NTSB flow is implemented in `ntsb/` and `rag/generator.py`:

- A planner converts the natural-language question into a bounded `NTSBSearchQuery` using a strict JSON schema.
- The search service supports case detail by NTSB number or `mkey`, registration searches, and date-range searches in aviation mode.
- Results are normalised to `NTSBCase` objects and filtered locally for fields such as aircraft, location, country, severity, investigation status and descriptive text.
- Pagination, date windows, result limits and detail hydration are bounded by configuration. Independent detail requests can run concurrently within the configured limit.
- The generator answers only from the returned NTSB records, cites the NTSB case number when available, reports truncated searches, and abstains with `I don't have that information in the NTSB records.` when the records do not support an answer.

The API client uses the subscription key from `NTSB_API_KEY`, sends the configured User-Agent, and applies retries for transient failures. The remaining `NTSB_API_*` variables in `.env.example` control the endpoint, timeout, pagination, search windows, hydration and concurrency limits.

To run the interactive NTSB query flow after configuring `.env`:

```bash
python -m rag.query_test_ntsb
```

## Evaluation is the decision loop

The project treats evaluation as infrastructure, not as a final report. The runner executes the same RAG path used by the application and persists the complete evidence chain for every case.

[![Evaluation loop](assets/evaluation-loop.svg)](assets/evaluation-loop.svg)

The first dataset, `aviation_golden_v1`, contains 36 English cases built from the downloaded sources, including an explicit out-of-corpus question. Golden answers and evidence live in the separate `evaluation` PostgreSQL schema; they never become searchable RAG context.

The deterministic retrieval layer currently tracks:

- `Recall@k`, `Precision@k`, `HitRate@k`, `MRR` and `nDCG@k`;
- duplicate ratio and unique-parent ratio;
- retrieved item count and estimated retrieved tokens;
- latency, input/output/context tokens and recorded cost;
- abstention decisions and the generated answer for each case.

This separation helps answer two different questions:

1. **Did retrieval find the right evidence, and how high did it rank?**
2. **What did the model actually receive, and what did it produce?**

Generation metrics such as citation correctness, faithfulness and answer correctness can be added on top of this deterministic baseline without losing the underlying retrieval evidence. LangSmith adds a visual trace for each evaluated case and its trace ID is stored with the database result.

## The dashboard

`Aviation RAG Evaluations` is a read-only Streamlit surface for inspecting decisions, not a generic chat demo. It exposes three useful views:

| View | What it answers |
| --- | --- |
| **Overview** | Is the run healthy? How are quality, latency and resource usage trending? |
| **Run Comparison** | Did a candidate beat the baseline, and what was the trade-off in context, cost or latency? |
| **Case Explorer** | Which question changed, what evidence was golden, what was retrieved and what context reached generation? |

The dashboard automatically chooses a compatible baseline from the same dataset. Comparisons also surface mismatches in corpus, prompt version and retrieval budget, because a raw score delta is misleading when the experiment changed more than one variable.

## Repository map

```text
ingestion/       document cleaning, parent-child chunking and embedding/upsert
rag/             retrieval, generation, guardrails and structured results
ntsb/            NTSB API client, query planning, case normalisation and search
assets/          responsive SVG diagrams used by this README
evaluation/      dataset runner, manifest handling and deterministic metrics
dashboard/       read-only Streamlit views over persisted evaluation runs
db/              pgvector, full-text search and evaluation schema
data/raw/        source manuals, PDF text extracts and aviation extracts
tests/           unit, integration and end-to-end coverage
```

The implementation intentionally avoids LangChain abstractions for the core path. LangSmith is used where it adds value: tracing and visual inspection of runs.

## Running the project

Operational setup is intentionally kept secondary to the design. For maintainers who want to reproduce the pipeline:

```bash
python configure.py
```

Configuration lives in `.env`; the expected variables are documented in `.env.example`. The evaluation dashboard has its own lightweight dependencies:

```bash
python -m pip install -r dashboard/requirements.txt
python -m streamlit run dashboard/app.py
```

Tests:

```bash
pytest tests
```

The NTSB flow can be exercised independently from the indexed-document path:

```bash
python -m rag.query_test_ntsb
```

## Current boundary and next experiment

The indexed-document path is the core system. The NTSB flow is available for structured accident records, but it is intentionally kept outside the vector corpus and is not yet selected automatically with the manuals path. The next architectural step is a routing agent that chooses between manuals, NTSB records or both, followed by generation-quality evaluation with RAGAS-style metrics.

## What "done" means here

Not an answer that sounds right once.

An answer that is supported by the right source, whose retrieval path can be inspected, whose changes can be compared against a baseline, and that is willing to say when the evidence is not there.
