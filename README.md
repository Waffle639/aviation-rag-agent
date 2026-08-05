# Aviation RAG Agent

A RAG system that answers technical questions about aircraft using official manuals and spec sheets. Built from scratch to understand every layer of the stack: ingestion, chunking, embeddings, vector search and grounded generation.


## Pipeline

```
PDF manuals + Wikipedia extracts
        ↓
cleaning and parent-child chunking
        ↓
embedding (text-embedding-3-small, 1536 dims) + tsvector generation
        ↓
Supabase + pgvector HNSW index + GIN full-text index
        ↓
question → embed + tsquery → hybrid search (RRF) → dedupe → parents
        ↓
grounded generation with citations
```

## Design decisions

**Parent-child chunking.** Children (~500 chars, 100 overlap) get embedded for precise matching; parents (~2000 chars, paragraph-aligned) are what the model actually sees. Search small, return big: a 500-char window locates the right spot, and the 2000-char parent gives the model enough context that the answer doesn't hinge on a sentence cut in half.

**HNSW over IVFFlat.** Better recall and no training step. Also a practical detail: IVFFlat indexes built on empty tables perform poorly until reindexed, and HNSW doesn't have that problem, which matters when the schema is created before the data arrives.


**Idempotent ingestion.** Every chunk gets a stable ID and ingestion is an upsert that skips what already exists, so re-running the pipeline never duplicates or re-embeds. API failures retry with exponential backoff, and failed batches are reported by ID so they can be retried selectively.

**Grounded generation.** The prompt forces the model to answer only from retrieved context, cite aircraft and source, and report discrepancies between sources instead of silently picking one. It also treats the context strictly as data, never as instructions: retrieved documents are untrusted input, and that line is the prompt-injection defense.

**Hybrid search (vector + keyword with RRF).** Pure vector search loses exact tokens like "Vso" or "V1" because embeddings of technical codes carry little signal. Two independent search legs run inside Postgres — HNSW for semantic similarity and GIN-backed full-text search for lexical matching — then Reciprocal Rank Fusion merges them using only rank positions, avoiding the need to normalise incompatible score scales. When the keyword leg finds nothing, the vector leg carries the result alone: graceful degradation by design.

## What's next

**NTSB as a second source.** Accident records come from the NTSB API, a structured source with a different access pattern than vector search, which is exactly what makes it interesting.

**Routing agent (LangGraph).** The question should decide the path: manuals, accidents, or both. LangGraph over CrewAI for the same reason as everything in this project: an explicit graph instead of reasoning hidden behind abstractions.

**Evaluation with RAGAS.** Measure faithfulness and context recall to know, with numbers, whether failures come from retrieval or generation. Without this, "it works" is just an opinion.

## What "done" looks like

A system that answers questions about specific aircraft, always citing its source, and honest enough to say "I don't have that information" when the data isn't there. That last part is the hard one.
