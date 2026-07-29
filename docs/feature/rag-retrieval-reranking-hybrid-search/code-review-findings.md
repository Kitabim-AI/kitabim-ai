# Code Review Findings – RAG Retrieval Reranking + Hybrid Search

**Branch:** `feature/rag-retrieval-reranking-hybrid-search`
**Base:** `feature/rag-chat-and-search-enhancements`
**Reviewed:** 2026-07-28
**Scope:** 3 commits, ~1,661 lines changed (no uncommitted work)

---

## Summary of changes

The branch adds three retrieval-quality features to the RAG pipeline, all gated behind `system_configs` flags with clean fallbacks:

1. **Hybrid search (RRF)** – new Postgres full-text `keyword_search` on a generated `text_search` tsvector column (migration `074`), fused with vector search via Reciprocal Rank Fusion in `retrieval.py`.
2. **LLM reranker** – new `reranker.py` replacing `_grade_context`'s relative-score heuristic, wired into the orchestrator with fallback to `_grade_context`.
3. **Configurable `rag_top_k`** – replaces hardcoded `settings.rag_top_k` reads throughout retrieval + grading, plus removal of the arbitrary 5-book cap in `deterministic_handler.py`.

Prompts were also narrowed from "Uyghur/Arabic/English" to Uyghur-only.

### Key files

| Area | File |
|------|------|
| Hybrid fusion | `packages/backend-core/app/services/rag/retrieval.py` |
| Keyword search | `packages/backend-core/app/db/repositories/chunks_repository.py` |
| Reranker | `packages/backend-core/app/services/rag/agent/reranker.py` |
| Orchestrator wiring | `packages/backend-core/app/services/chat/orchestrator.py` |
| Grading fallback | `packages/backend-core/app/services/rag/agent/llm_routed_handler.py` |
| Config constants | `packages/backend-core/app/services/rag/agent/config.py` |
| Prompts | `packages/backend-core/app/core/prompts.py` |
| Model column | `packages/backend-core/app/db/models.py` |
| Seeds | `packages/backend-core/app/db/seeds.py` |
| Migration | `packages/backend-core/migrations/074_add_chunks_text_search.sql` |

---

## Strengths

- **Excellent defensive design & documentation.** The reranker JSON parsing uses `raw_decode` (correctly avoids greedy-bracket over-capture), coerces observed numeric-string indices, validates ranges, and every non-obvious decision has a rationale comment. 14 reranker tests cover the tricky paths (trailing commentary, malformed JSON, out-of-range indices, zero-relevant floor).
- **Safe rollout.** Every feature has a `system_configs` kill-switch documented as "identical to pre-change behavior," and each fallback fails soft (keyword-leg error → vector-only; reranker error → `_grade_context`).
- **Correct field parity.** `_pool_and_dedup` mirrors `_grade_context`'s metadata keys and `(book_id, page)` dedup exactly; migration `074` is the correct next number and `CREATE INDEX CONCURRENTLY` follows the established precedent in migration `036`.
- **Strong test coverage** – 1,102 lines across 8 test files.

## Findings

### 1. Multi-book path re-sorts fused results by `similarity`, partially negating hybrid search – Medium

In `retrieval.py`, the multi-book branch flattens per-book RRF-fused results then does:

```python
similar_chunks.sort(key=lambda c: c.get("similarity", 0.0), reverse=True)
```

Keyword-only hits (which by design carry no `similarity` field – per the `_fuse_rrf` comment) default to `0.0` and sink to the bottom, so in the multi-book scoped path a pure-keyword match effectively can't outrank vector hits. The RRF ordering computed inside `_search_chunks` is discarded here. The single-book path preserves fusion order, so the inconsistency is only in the multi-book merge.

**Suggested fix:** preserve the RRF order across the merged multi-book set (e.g. carry an explicit fused-rank field and sort on it) instead of re-sorting by `similarity`.

### 2. Keyword-only hits get filtered when the reranker is disabled – Medium (related)

Those same keyword-only hits arrive at `_grade_context` with `score = 0.0`, so the relative-threshold filter (`>= top_score * 0.85`) drops them unless they land in the `MIN_CHUNKS_AFTER_GRADING` floor. So with `rag_reranker_enabled=false` but `rag_hybrid_search_enabled=true`, hybrid search delivers little. Fine if the reranker is always on (the default), but the two flags interact and this combination is a quiet no-op.

**Suggested fix:** document the flag interaction, or have `_grade_context` treat missing-`similarity` keyword hits as a distinct class rather than score `0.0`.

### 3. `rag_top_k` fallback divergence – Minor

`orchestrator.py` hardcodes the fallback `"25"` / `25`, while `retrieval.py` falls back to `settings.rag_top_k`. Both resolve to 25 today, but if the `RAG_TOP_K` env var is ever changed, the two layers would use a different top-k when the config row is missing.

**Suggested fix:** use `settings.rag_top_k` in the orchestrator fallback too, to keep the layers aligned.

### 4. Extra per-call config reads – Minor

`vector_search` now issues two `get_value` reads (`rag_hybrid_search_enabled`, `rag_top_k`) on every invocation, and the orchestrator reads several more. Low impact (small indexed SELECTs), just worth confirming `SystemConfigsRepository` reads are cached.

---

## Verdict

None of these are blockers – the feature is behind flags with sound fallbacks. Findings **1** and **2** are the ones to address before relying on hybrid search for multi-book queries.
