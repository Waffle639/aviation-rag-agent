<div align="center">

# Aviation RAG Agent

**An evidence-first RAG system for technical aviation research.**

</div>

[![Core RAG pipeline](assets/core-rag-pipeline.svg)](assets/core-rag-pipeline.svg)

## How it works

The agent keeps each step explicit and bounded before an answer is produced:

```text
user input + session context
  -> normalize -> Prompt Guard -> moderation
  -> resolve follow-up into a standalone question
  -> route
       |-> documents: parent-child hybrid retrieval
       |-> accidents: local NTSB index -> optional API case detail
       |-> both: run both evidence paths in parallel
       `-> abstain: stop when the sources cannot support the request
  -> rank and fit evidence into the context budget
  -> grounded synthesis
  -> citation validation -> output leak check -> moderation
  -> answer + persisted turn + LangSmith trace
```

| Capability | What it does |
| --- | --- |
| **Parent-child retrieval** | Searches small passages for precision and returns larger parent context for generation. |
| **Hybrid search** | Combines pgvector semantic search with PostgreSQL full-text search through Reciprocal Rank Fusion. |
| **Official NTSB records** | Synchronizes official accident and incident records from the external NTSB API into a relational index for deterministic filters, counts and rankings. |
| **Controlled routing** | Selects technical documents, NTSB records, both sources or abstention before generating an answer. |
| **Grounded answers** | Uses only retrieved evidence, preserves numeric precision and cites the supporting sources. |
| **Conversation memory** | PostgreSQL sessions preserve turns; bounded summaries resolve follow-ups without treating conversation history as aviation evidence. **In progress.** |
| **Chat UI** | Streamlit chatbot with persistent sessions, source inspection, model visibility and token telemetry. |

Interactive NTSB queries run against the synchronized local index. The external API is reserved for synchronization and selected-case detail, keeping broad searches deterministic and API usage bounded.

## Evaluation

Answer quality is bounded by the quality, coverage and provenance of the source documents, and by whether retrieval selects the right evidence. The evaluation loop therefore measures the evidence path before attributing an improvement to the model.

- **Golden cases:** expected answers and evidence remain isolated from the searchable corpus.
- **Retrieval quality:** `Recall@k`, `MRR` and `nDCG@k` measure whether the expected evidence was found and where it ranked.
- **Efficiency:** estimated context and prompt tokens, plus provider input, output and total usage when available, are stored alongside retrieval, context-building, generation and end-to-end latency.
- **Traceability:** persisted run data and LangSmith traces connect each answer to its retrieval, selected context, configuration, timings and failures.

[![Evaluation loop](assets/evaluation-loop.svg)](assets/evaluation-loop.svg)

The initial `aviation_golden_v1` dataset contains 36 numeric, variant-sensitive, document-structure and out-of-corpus cases. The Streamlit dashboard supports run comparison and case-level evidence inspection.

## Security

Security is applied where untrusted content enters and leaves the system. During ingestion, every child chunk is scanned with the locally cached `Llama-Prompt-Guard-2-86M` model. Long content is inspected through overlapping token windows; a malicious result or an unavailable detector blocks indexing instead of silently admitting unchecked text.

At query time, Unicode normalization removes control and obfuscation characters before enforcing input and context limits. The question then passes through the local Prompt Guard detector and the OpenAI Moderation API before retrieval. Generated answers are moderated again, checked for prompt leakage and validated against the evidence IDs returned by the selected tools.

These guardrails fail closed when security is enabled: unavailable protection stops the request rather than degrading invisibly.

## Run

The guided setup creates or checks `.env`, applies the PostgreSQL schema, prepares the local Prompt Guard model and verifies the NTSB API and local index.

```bash
python configure.py
python configure.py --check
```

For the containerized runtime, point `DATABASE_URL` to the prepared Supabase project and run:

```bash
docker compose run --rm model-init
docker compose up -d chat
docker compose up -d dashboard
docker compose run --rm worker python -m rag.query_test_memory
```

Open the chat at `http://localhost:8502` or the evaluation dashboard at `http://localhost:8501`. Additional agent, evaluation, synchronization and deployment commands are documented in [DOCKER.md](DOCKER.md).

## Boundaries

- Research prototype, not an operational flight or maintenance authority.
- Retrieval evaluation is implemented; generation-quality and semantic citation evaluation are the next validation layer.
- Supabase, OpenAI and the NTSB API remain external runtime dependencies.

> Done means an answer supported by inspectable evidence, not one that merely sounds correct.

## Stack

<p align="center">
  <a href="https://skillicons.dev">
    <img src="https://skillicons.dev/icons?i=python,pytorch,postgres,supabase,docker,git" alt="Python, PyTorch, PostgreSQL, Supabase, Docker and Git" />
  </a>
</p>

<p align="center">
  <a href="DOCKER.md">Docker and deployment</a> |
  <a href="LICENSE">License</a>
</p>

---

**Feedback, questions and suggestions are always welcome. 🙌**
