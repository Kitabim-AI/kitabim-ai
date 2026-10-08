# EmbeddingGemma 2 Local Embedding PoC — Design

**Date:** 2026-10-07
**Status:** Approved design, pending implementation plan
**Follow-up (separate spec):** semantic chunking, reusing this PoC's pool and test set

## Goal

Decide whether Google's open **EmbeddingGemma 2** (text encoder only, ~270M params, Apache 2.0), running **CPU-only** as it would in prod, can replace `gemini-embedding-2` (3072 dims, paid API) for Uyghur book retrieval. A GO also unlocks semantic chunking, since local embedding removes per-chunk API cost.

## Non-goals

- No production code, schema, or config change. Nothing in `packages/`, `services/`, or `packages/backend-core/migrations/` is modified.
- No keyword/hybrid search, reranking, or ADK agent in the evaluation — dense retrieval only, because the embedding model is the only variable.
- No full-corpus re-chunk (see the standing rule against bulk re-chunking). Only the 10 test volumes are ever re-chunked, and only in the semantic-chunking follow-up.
- EmbeddingGemma v1 is excluded (no evidence of Uyghur support).

## Models under test

| Model | Dims evaluated | How |
|---|---|---|
| `gemini-embedding-2` (baseline) | 3072 | Gemini Batch API, no `task_type` — identical to prod today |
| EmbeddingGemma 2, text encoder only | 768, 512, 256 | Official `google/embeddinggemma-2` checkpoint, text path only; 512/256 by Matryoshka truncation + re-normalization of the 768 vector (no re-embedding) |

Community text-only exports (e.g. `jayyun98/embeddinggemma-2-text-270m`) may be used only if their vectors match the official checkpoint's text path (cosine ≥ 0.999) on 200 Uyghur chunks.

EmbeddingGemma's recommended query/document prompt prefixes are used as the model card specifies; the exact strings are recorded in the report.

## Runtime

- **CPU only, everywhere** — no MPS/GPU, to match prod.
- Runs in a Docker container (`linux/arm64`, CPU PyTorch + `sentence-transformers`) with `--cpus` / `--memory` pinned to the prod worker VM's spec.
- **Prod worker spec is an input the user confirms before Stage 3.** Until confirmed, the container uses 4 CPUs / 8 GB.
- Code: `scripts/poc/embeddinggemma/`. Reads the local DB via `DATABASE_URL`. Report: `docs/poc/embeddinggemma/`.

## Stages

### Stage 0 — Uyghur sanity check (go/no-go, ~1 hour, no tables)

- ~50 hand-checked Uyghur pairs: 20 paraphrase, 15 question→answer-passage, 15 unrelated.
- **Pass:** mean cosine of paraphrase and Q→A pairs exceeds mean of unrelated pairs by a clear margin, and ≥ 90% of related pairs score above every unrelated pair's median.
- Tokenizer check: tokens per Uyghur word and share of byte-fallback tokens on 1,000 words of book text, reported alongside Gemini's figures for context. Heavy byte-fallback is a warning sign.
- **Fail → stop the PoC** and write up the result.

### Stage 1 — Build the pool (local DB, `poc` schema)

Created by a setup script (`CREATE SCHEMA poc`), not a numbered migration; `DROP SCHEMA poc CASCADE` removes everything.

**`poc.chunks`**

| Column | Type | Notes |
|---|---|---|
| `id` | serial PK | |
| `strategy` | text | `current` now; `semantic_v1`, … later |
| `book_id` | varchar(64) | |
| `page_number` | int | |
| `chunk_index` | int | |
| `text` | text | |
| `char_start`, `char_end` | int | Offsets within `clean_uyghur_text(page.text)` — the chunker's input |
| `emb_gemma` | vector(768) | |
| `emb_gemini` | vector(3072) | |

Unique on `(strategy, book_id, page_number, chunk_index)`. Offsets are found by sequential search of each chunk's text in the cleaned page text (overlap carry-over means chunks can share text, so search starts from the previous chunk's start). Chunks whose text cannot be located are counted and reported; if > 1%, stop and fix before continuing.

**Pool contents (~50k chunks, all `strategy='current'`, copied from local `chunks`):**

- **Test volumes (10, ~10.3k chunks):**
  - ئانا يۇرت — زوردۇن سابىر: `631481d3a7e9`, `683238d33c15`, `f0a9bc581a27`
  - لېيىغان بۇلاق — جالالىدىن بەھرام: `dbd310c05e85`, `b3b122b72df7`, `f24b85bcf8a2`, `336119148ffb`, `9c88386eaae3`, `efb8b34926ba`, `b7e6e5b5bb19`
- **Distractors (~40k chunks):** ~50 complete `ready` books, sampled stratified by category, fixed random seed, book IDs recorded in the report.

Local `chunks.embedding` is almost entirely NULL (63 / 526k), so both models embed the full pool fresh.

### Stage 2 — Test set

**Synthetic (~300 questions)**
- Passages sampled across all 10 test volumes, proportional to chunk count, skipping passages under 200 chars.
- Gemini generates one natural Uyghur question per passage, instructed to avoid copying the passage's wording. Prompt authored via `/prompt-engineer`.
- Reject a question if > 40% of its word trigrams appear in the source passage.
- Gold label: `(book_id, page_number, char_start, char_end)` of the source passage.
- **User spot-checks ~30 questions** before Stage 3; questions flagged as unnatural or unanswerable are removed and the prompt adjusted if > 20% are flagged.

**Real (~200 questions)**
- Sampled from the 1,502 global (`is_global = true`) distinct questions in `rag_evaluations`, de-duplicated, fixed seed.
- Relevance via pooled blind judging: union of every variant's top-10 from the pool, judged by Gemini as relevant / not relevant without knowing the source model. Questions with zero relevant results anywhere are dropped.

### Stage 3 — Evaluation

- **Hit rule:** a retrieved chunk is a hit if its `[char_start, char_end)` overlaps the gold range on the same `(book_id, page_number)` — strategy-agnostic, so semantic chunks can be scored on the same test set later. For real questions, a hit is a judged-relevant chunk.
- **Metrics:** Recall@5/10/25 (25 = prod `RAG_TOP_K`), MRR@10, nDCG@10.
- **Scopes:** within-book (synthetic only) and full pool (both sets).
- **Search:** exact cosine (sequential scan) — no ANN index, so index approximation doesn't confound the comparison.
- **Performance (Gemma, CPU container):** chunks/sec for document embedding, single-query latency p50/p95, peak RAM, model load time, and projected time to embed a 500-page book.

## Go/no-go criteria

GO requires all of the following for a given Gemma dimension:

1. Pool-scope Recall@25 ≥ **95% of Gemini's**, on both synthetic and real sets.
2. Pool-scope nDCG@10 no more than **3 points** below Gemini's, on both sets.
3. Embedding a 500-page book on the prod CPU spec takes **≤ 30 minutes** (the user may revise this target), and query latency p95 is **< 150 ms**.

Recommend the smallest dimension that passes (256 is 12× smaller than 3072).

## Deliverable

`docs/poc/embeddinggemma/REPORT.md`:
- Stage 0 result and tokenizer stats.
- Metric tables (model × dim × scope × question set) and performance table.
- 20 questions with the largest disagreement between Gemini and the best Gemma variant, top-5 results side by side, for the user's review.
- Clear GO / NO-GO recommendation against the criteria above, with costs: Gemini Batch spend for the PoC and projected prod compute.

## Risks

- **Uyghur weakness in Gemma** — caught cheaply by Stage 0.
- **Synthetic questions flatter lexical overlap** — mitigated by the trigram filter, the user spot-check, and the real-question set.
- **Gemini judge bias** — judging is blind to the model, and the 20-question disagreement review lets the user sanity-check it.
- **Both test titles are literary prose** — genre breadth comes from the real-question set and the category-stratified distractors.
- **Mac arm64 CPU ≠ GCP CPU** — pinning CPU/RAM narrows the gap. If the prod VM is x86, a short throughput rerun on a matching GCP instance is recommended before production planning.
