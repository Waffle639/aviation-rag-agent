# Aviation RAG Agent

## What this is

A learning project to really understand how RAG (Retrieval-Augmented Generation) systems and AI agents work, applied to a real use case: an assistant that answers technical questions about aircraft using official manuals, spec sheets, and real accident data — instead of making things up.

**Current status: nothing is built yet. This is the starting plan.**

## The idea in one sentence

You ask something like *"what's the stall speed of a Boeing 747?"* or *"what accidents has the F-16 had during approach?"*, and the system searches real technical documents (not its general training memory) and answers while citing where the data comes from.


## How it's going to be built (simple)

```
1. Get real aircraft documents (PDF manuals, official spec sheets,
   Wikipedia for historical/contextual background)
        ↓
2. Split those documents into chunks and convert them into
   vectors (embeddings) that represent their meaning
        ↓
3. Store those vectors in a database built for semantic search
   (Supabase + pgvector)
        ↓
4. When someone asks a question, the system searches for the
   most relevant chunks
        ↓
5. An LLM (GPT or Claude) generates the answer using ONLY those
   retrieved chunks as grounding, citing the source
        ↓
6. An agent decides whether to search the manuals, the NTSB
   accident database, or both, depending on the question
```

## Key technical pieces, and why each one matters

- **RAG** — instead of letting the model hallucinate facts, it retrieves real documents first and only then generates an answer grounded in what it found. This is the difference between "sounds right" and "is actually correct."
- **Embeddings** — turning text into numbers that represent meaning, so the system can search by *similarity* instead of exact keyword matching. This is the foundation everything else builds on.
- **Parent-child chunking** — small chunks get embedded for precise search, but the system returns the larger parent section so the LLM has enough context to answer properly. Chosen because plain fixed-size chunking tends to cut technical sections mid-sentence and lose meaning.
- **Hybrid search** — combining semantic search with keyword search. Chosen specifically because aviation data has exact technical codes (Vso, V1) that pure semantic search tends to miss.
- **Agent with routing (LangGraph)** — the system doesn't just answer, it decides *which* source to consult based on the question. This is what separates a simple RAG demo from something that behaves like an actual reasoning system.
- **RAGAS evaluation** — measuring with real numbers whether the system is actually working well or just sounds convincing. Chosen over "it seems to work" because a portfolio project with measured metrics is far more credible than one with vibes-based confidence.

## Stack, and why

- **FastAPI** — backend, already familiar, zero learning curve wasted here
- **Supabase (pgvector)** — vector database without extra infrastructure to manage
- **OpenAI embeddings** — industry standard, cheap, no reason to complicate this choice
- **LangGraph** — chosen over CrewAI because it forces explicit state-graph definition instead of hiding the agent's reasoning behind heavy abstraction; more honest about what's actually happening
- **RAGAS** — the standard framework for RAG evaluation, ties directly to identifying which part of the pipeline is failing (retrieval vs. generation)

## What "done" looks like

A system usable via chat or API that answers questions about specific aircraft (Cessna, Boeing, F-22, MiG-29...), always citing its source, and honest enough to say "I don't have that information" instead of inventing an answer when the data isn't there.
