# Kitabim.AI Root Diagrams Directory

This directory contains system architecture, workflow, data-flow, lifecycle, and sequence diagrams for Kitabim.AI, generated using **[Archify](https://github.com/tt-a1i/archify)**.

## Interactive HTML Diagrams

1. **[System Architecture Map](file:///Users/Omarjan/Projects/kitabim-ai/diagrams/system-architecture.html)** (`system-architecture.html` — *Architecture*)
   - **Infrastructure**: Web Frontend (React), Nginx Proxy, FastAPI, ARQ Worker, PostgreSQL (PGVector), Redis, GCS Storage, Gemini Vision OCR Engine, and Gemini 3.6 API.
   - **Preset Views**: *Full System Architecture*, *Book Ingestion & OCR Pipeline*, *RAG Chat & Knowledge Query*.

2. **[Book Ingestion & RAG Chat Sequence](file:///Users/Omarjan/Projects/kitabim-ai/diagrams/sequence-pipelines.html)** (`sequence-pipelines.html` — *Sequence*)
   - **Sequence Flows**: PDF Upload & OCR Processing, Hybrid Search & RAG Streaming Response.

3. **[OCR & Document Processing Workflow](file:///Users/Omarjan/Projects/kitabim-ai/diagrams/workflow-ocr-pipeline.html)** (`workflow-ocr-pipeline.html` — *Workflow*)
   - **End-to-End Pipeline**: User PDF Upload → FastAPI Validation → Redis Queue → Page Splitter → Gemini Vision OCR → Gemini Embedder → PGVector Commit.

4. **[Hybrid Search & RAG Data Flow](file:///Users/Omarjan/Projects/kitabim-ai/diagrams/dataflow-rag-hybrid-search.html)** (`dataflow-rag-hybrid-search.html` — *Data Flow*)
   - **Data Movement**: User Query → Vector Embedding & Keyword Tokenizer → PGVector Search + Knowledge Graph Lookup → Context Reranking → Gemini 3.6 Synthesis → SSE Stream.

5. **[Book Ingestion Processing Lifecycle](file:///Users/Omarjan/Projects/kitabim-ai/diagrams/lifecycle-book-processing.html)** (`lifecycle-book-processing.html` — *Lifecycle*)
   - **State Machine**: `Uploaded` → `Queued` → `OCR Scanning` → `Chunking & Embedding` → `Indexed Ready` (with transient `Retrying` & `Processing Failed` exits).

6. **[Uyghur Spellcheck & Lexicon Sequence](file:///Users/Omarjan/Projects/kitabim-ai/diagrams/sequence-spellcheck.html)** (`sequence-spellcheck.html` — *Sequence*)
   - **Spellcheck Engine**: Exact Dictionary Lookup, Phonetic Sound-Alike Matching, Edit Distance Candidate Ranking.

---

## Re-generating Diagrams

Run the following commands from the repository root to regenerate HTML artifacts after modifying JSON specifications:

```bash
# 1. System Architecture Map
node ~/.agents/skills/archify/bin/archify.mjs deliver architecture \
  diagrams/kitabim-ai-system.architecture.json \
  diagrams/system-architecture.html \
  --quality standard --json

# 2. Book Ingestion & RAG Chat Sequence
node ~/.agents/skills/archify/bin/archify.mjs deliver sequence \
  diagrams/kitabim-ai-pipelines.sequence.json \
  diagrams/sequence-pipelines.html \
  --quality standard --json

# 3. OCR Processing Workflow
node ~/.agents/skills/archify/bin/archify.mjs deliver workflow \
  diagrams/workflow-ocr-pipeline.json \
  diagrams/workflow-ocr-pipeline.html \
  --quality standard --json

# 4. Hybrid Search & RAG Data Flow
node ~/.agents/skills/archify/bin/archify.mjs deliver dataflow \
  diagrams/dataflow-rag-hybrid-search.json \
  diagrams/dataflow-rag-hybrid-search.html \
  --quality standard --json

# 5. Book Processing Lifecycle
node ~/.agents/skills/archify/bin/archify.mjs deliver lifecycle \
  diagrams/lifecycle-book-processing.json \
  diagrams/lifecycle-book-processing.html \
  --quality standard --json

# 6. Uyghur Spellcheck Sequence
node ~/.agents/skills/archify/bin/archify.mjs deliver sequence \
  diagrams/sequence-spellcheck.json \
  diagrams/sequence-spellcheck.html \
  --quality standard --json
```
