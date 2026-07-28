# RAG Answer Quality: LLM Reranking + Postgres Hybrid Search

**Date:** 2026-07-27
**Status:** Draft (pending review)

## Problem

Today's retrieval has no real relevance reranking and no keyword search. `_grade_context` (`packages/backend-core/app/services/rag/agent/llm_routed_handler.py:120-222`) is the closest thing to a rerank step, but it's a cheap heuristic: pool chunks from every `search_chunks` tool call in the turn, dedupe by `(book_id, page)`, keep chunks within `GRADE_RELATIVE_THRESHOLD` (0.85) of the top *vector similarity score* per search call, and cap at `AGENT_MAX_CONTEXT_CHUNKS` (25). It never re-judges relevance against the actual question semantics beyond the original embedding distance, and retrieval is vector-only — there's no keyword/BM25 path in production (the only keyword fallback in `retrieval.py` is explicitly dev-only).

This is the follow-on to [`2026-07-27-rag-eval-scoring-design.md`](2026-07-27-rag-eval-scoring-design.md), which wires up `faithfulness`/`answer_relevance`/`context_precision` scoring so these changes can be measured against a real before/after baseline instead of spot-checking transcripts.

## Existing state

- `ChatOrchestrator.stream_response` calls `_grade_context(observations)` at `orchestrator.py:266` (imported at line 31) to turn pooled tool-call observations into `graded_context`. This is the sole call site on the live path (the deterministic/LLM-routed handlers have their own call at `llm_routed_handler.py:386`, part of the legacy fallback path established as dead in production in the prior eval-scoring spec).
- Relevant constants, all in `packages/backend-core/app/services/rag/agent/config.py`: `AGENT_MAX_CONTEXT_CHUNKS = 25`, `GRADE_RELATIVE_THRESHOLD = 0.85`, `MIN_CHUNKS_AFTER_GRADING = 3`. `RAG_SCORE_THRESHOLD` (0.50) and `RAG_TOP_K` (25) live separately in `core/config.py:68-69`.
- `ChunksRepository.similarity_search` (`db/repositories/chunks_repository.py:73-220`) takes `(query_embedding, book_ids, categories, limit, threshold)`, runs pgvector cosine distance (`1 - (embedding <=> ...)`), with a `book_ids`-scoped branch and an unscoped branch (over-fetches `limit * 3` for HNSW). Category filter (`b.categories && ...`) applies to both branches.
- `Chunk` model (`db/models.py:346-383`): `id`, `book_id`, `page_number`, `chunk_index`, `text` (`Text`), `embedding` (`Vector(3072)`). **No tsvector/GIN/trigram column or index exists on `chunks` anywhere in `migrations/`** — the only FTS-adjacent index in the whole migrations folder is an unrelated `gin_trgm_ops` index on `words.word` (`066_add_trgm_index_on_words.sql`). `text` is a plain column, FTS-ready via `to_tsvector()` but nothing has been built yet.
- `vector_search` (`services/rag/retrieval.py:82-383`) wraps `similarity_search` with: embedding cache, per-book `top_k` splitting when multiple `book_ids` are scoped (`rag_top_k // len(book_ids)`, min 3), a zero-result retry at `threshold=0.0`, the dev-only keyword fallback, and a separate Quran-table merge for Islamic queries. Direct `similarity_search` calls happen at 4 sites (140, 157, 173, 190) — hybrid search needs to slot in at each of these without disturbing the surrounding branches.
- For a lightweight single-shot Gemini call with structured JSON output (what the reranker needs), the established pattern is `client.aio.models.generate_content(..., config=types.GenerateContentConfig(response_mime_type="application/json"))`, used today in `deterministic_handler.py:257-279` and `:594-601` (via the `build_text_llm()`/`ProtectedLLM.ainvoke()` helper at `llm/models.py:515,384,394`). **No need to spin up a full ADK `Agent`/`Runner`** (that machinery, used by `build_answer_agent`, is for multi-turn tool-using agents, not a single scoring call).

## Design

### Reranker: approach and placement

A single Gemini call, using the existing lightweight single-shot helper (not an ADK agent), replaces the relevance-*selection* portion of `_grade_context` — but **`_grade_context` itself is not deleted**. It becomes the fallback path (see Error handling), since it's already-tested, cheap, and requires no new dependency.

**Why not an ADK `Agent`, explicitly:** `answer_agent.py`'s no-tool `Agent(tools=[])` pattern was considered, since it's the closest existing "single-purpose agent" shape in this codebase, and the installed SDK (`google-adk==2.5.0`) genuinely supports `output_schema` for structured Pydantic output on `Agent`. Rejected anyway: `output_schema` has zero precedent anywhere in this codebase today, and going through `Agent`/`Runner` requires session-service creation and async event-loop parsing (see `orchestrator.py:270-313`) — machinery built for multi-turn, tool-calling conversations that a single non-conversational scoring call doesn't need. Instead, this uses the same raw `client.aio.models.generate_content(..., config=types.GenerateContentConfig(response_mime_type="application/json"))` pattern already established in `deterministic_handler.py:257-279`/`:594-601` for exactly this class of problem (single-shot structured judgment). The eval-scoring spec's judge module makes the identical choice, for the same reasons.

New function `rerank_context(question: str, candidates: list[GradedDoc]) -> list[GradedDoc]` in a new file `packages/backend-core/app/services/rag/agent/reranker.py`:

1. **Dedup first, same as today.** Pool observations across all `search_chunks` tool calls in the turn and dedupe by `(book_id, page)` — this is data hygiene (avoid sending the same chunk to the reranker twice because two tool calls both surfaced it), not a relevance judgment, so it's kept regardless of reranking.
2. **Bound the reranker's input size.** A new constant `RERANK_MAX_INPUT_CHUNKS` (proposed: 50) caps how many deduped candidates get sent to the LLM. If the deduped set exceeds this, pre-trim to the top `RERANK_MAX_INPUT_CHUNKS` by original vector/fusion score before reranking — protects prompt size/cost against a pathological turn where the agent calls `search_chunks` many times.
3. **One Gemini call.** Candidates are numbered `1..N` in the prompt (question + each candidate's text + book/page metadata for citation). The model returns a JSON array of chunk indices in relevance order. No re-derivation of book_id/page from model output — indices map straight back to the original candidate objects, so citation metadata can't be corrupted by the LLM.
4. **Final cap unchanged.** Take the reranked list's first `AGENT_MAX_CONTEXT_CHUNKS` (25) — same constant as today, so the answer agent's context size doesn't change, only its relevance ordering/selection.

This was a deliberate choice (over layering the reranker only on `_grade_context`'s survivors): the relative-score threshold heuristic is replaced outright by real semantic reranking, accepting the larger candidate set/cost as the trade-off for better selection quality.

### Feature flags

Two independent system_configs keys, following the `rag_judge_scoring_enabled` pattern from the eval-scoring spec:

- **`rag_reranker_enabled`** — checked in the orchestrator before calling `rerank_context`. If disabled (or the call fails/times out — see Error handling), falls straight to today's `_grade_context`. Zero behavior change when off.
- **`rag_hybrid_search_enabled`** — checked inside `vector_search` before adding the keyword leg. If disabled, retrieval is exactly what it is today (vector-only via `similarity_search`).

Both read via `SystemConfigsRepository.get_value(key, "true")`, `.lower() == "true"` parsing — same convention as `rag_judge_scoring_enabled`. **Proposed default: `'true'` for both**, consistent with the eval-scoring flag's default — call this out explicitly for review, since unlike the async eval job, both of these sit in the live chat request path and add real latency; if a more cautious `'false'`-by-default rollout is wanted here, that's a one-line change to the seed migration.

### Hybrid search: schema

New migration adds a generated tsvector column + GIN index to `chunks`:

```sql
ALTER TABLE chunks ADD COLUMN text_search tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED;
CREATE INDEX idx_chunks_text_search ON chunks USING GIN (text_search);
```

**Text search config is `'simple'`, deliberately not `'english'`.** Book content is substantially Uyghur-language (per project context — Uyghur/Arabic-script text); Postgres's `'english'` config applies English-specific stemming rules that don't meaningfully apply here, whereas `'simple'` just tokenizes/lowercases without language-specific stemming assumptions — the correct choice for keyword matching across mixed/non-English content.

### Hybrid search: fusion

New `ChunksRepository.keyword_search(query_text, book_ids, categories, limit)` mirrors `similarity_search`'s two-branch (scoped/unscoped) shape, using `plainto_tsquery('simple', query_text)` ranked by `ts_rank`, sharing the same category-filter clause.

New `hybrid_search(...)` in `retrieval.py`, slotted in alongside the existing 4 `similarity_search` call sites (each per-book split, the unscoped call, and the zero-result retry all get a parallel keyword call): runs `similarity_search` and `keyword_search` with the same effective limit, then fuses via standard **Reciprocal Rank Fusion**: `score(chunk) = Σ 1/(k + rank_i)` across the two rankers, `k = 60`, summed only over rankers where the chunk appears at all (a chunk in just one ranker's results still gets a score from that one term). Truncate the fused list to the target limit before returning.

`RAG_SCORE_THRESHOLD` continues to filter the vector leg's weak matches *before* fusion (as it does today for vector-only search) — `ts_rank` scores aren't on a comparable scale, so the keyword leg contributes purely by rank, not by an analogous threshold. Category filtering, the Quran-table merge, and the dev-only fallback are untouched — hybrid search only augments the core vector leg with a parallel keyword leg at the same call sites.

### Data model

One new migration: `chunks.text_search` generated tsvector column + GIN index (above), plus seeding `rag_reranker_enabled` and `rag_hybrid_search_enabled` into `system_configs`. No changes to `RAGEvaluation` or any other table.

### Error handling

- **Reranker call fails or times out** (malformed JSON, rate limit, or exceeds an explicit `asyncio.wait_for` timeout) → caught, logged, fall back to the existing `_grade_context` result for that turn. The chat response is never blocked or degraded to an error — worst case, a turn silently gets today's heuristic selection instead of the improved one.
- **Reranker returns indices out of range or a malformed list** → treated the same as a call failure (fallback to `_grade_context`), not a partial/best-effort application of whatever indices did parse — avoids subtly-wrong citation ordering from a half-parsed response.
- **Hybrid search's keyword leg errors** (e.g. malformed tsquery from unusual input) → caught per-call, keyword leg contributes nothing for that call, fusion proceeds on the vector leg alone — equivalent to today's vector-only behavior for that one call, not a whole-turn failure.

### Testing

- `reranker.py` unit tests: mock the LLM call, verify dedup runs before rerank, verify `RERANK_MAX_INPUT_CHUNKS` trimming, verify index-to-candidate mapping, verify fallback to `_grade_context` on exception/timeout/malformed output.
- `ChunksRepository.keyword_search` tests: seeded chunks, verify `ts_rank` ordering and category/book_id filtering, using `'simple'` config behavior (no English stemming assumptions).
- Fusion unit test: given known per-ranker rank lists, assert RRF-combined ordering matches the expected formula output (pure function, no DB needed).
- Orchestrator tests: `rag_reranker_enabled="false"` → `_grade_context` used directly, `rerank_context` never called; `"true"` → `rerank_context` called and its result used.
- `retrieval.py` tests: `rag_hybrid_search_enabled="false"` → identical behavior to current vector-only tests; `"true"` → both legs queried and fused.

## Explicitly out of scope

- Migrating the legacy `llm_routed_handler.py:386` call site to the new reranker — that path is dead in production (per the eval-scoring spec's findings) and not worth touching.
- A cross-encoder or hosted rerank API (Cohere Rerank, etc.) — LLM-based reranking was chosen specifically to avoid new infra/vendor dependencies.
- A dedicated search engine (Elasticsearch/OpenSearch) for keyword search — Postgres FTS was chosen to stay inside existing infrastructure.
- Tuning `RERANK_MAX_INPUT_CHUNKS`, RRF's `k=60`, or the GRADE_* constants beyond their proposed initial values — left as tunable knobs to adjust once real data comes in via the eval-scoring pipeline.
- Any change to the Quran-table merge or the dev-only keyword fallback — both untouched.
