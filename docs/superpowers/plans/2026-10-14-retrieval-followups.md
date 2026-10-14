# Retrieval Follow-ups (after direct chunk search shipped)

Context: `rag_summary_narrowing_enabled = false` (direct whole-library chunk search) has been live on prod since 2026-10-14. Original plan: [2026-10-13-direct-chunk-retrieval.md](2026-10-13-direct-chunk-retrieval.md).

## 1. Decide the default (do first)

- [ ] Build a fixed eval set of 20–30 questions, with the expected book + page written down before running. Cover: topics mentioned on only a few pages, "who is X" questions, cross-book topics, named book + detail, rare inflected names, persona category filters.
- [ ] Store it as a reusable suite in `packages/backend-core/tests/adk_eval/` (currently empty).
- [ ] Run the set with `rag_summary_narrowing_enabled = true`, then `false` (switch it on the admin System Configs page; that clears the 10-min config cache).
- [ ] Record per question: expected page cited? `latency_ms`, judge scores, `tools_called` (from `rag_evaluations`).
- [ ] Write results to `docs/poc/direct-chunk-retrieval/REPORT.md`.
- [ ] If direct wins: delete the legacy prompt variant (`build_agent_system_prompt(summary_narrowing=True)` branch), the `search_books_by_summary` tool, `settings.summary_threshold`, and the flag itself. Keep `book_summaries` (`get_book_summary` still uses it).
- [ ] If direct loses: set the flag back to `true`; all other fixes stay.

## 2. Small PR: search correctness

- [x] Check prod pgvector version: `SELECT extversion FROM pg_extension WHERE extname='vector';` → **0.8.1**
- [ ] Persona category filters on library-wide search. **Reverted 2026-10-14:** iterative scan (filter inside the HNSW CTE + `hnsw.iterative_scan = relaxed_order`) took 24.9 s on prod — it pulled 20,477 index rows (~1.2 ms each, heap reads) to find 200 in the history categories. Back to filtering the 200 HNSW candidates afterwards (fast, but few results for narrow personas). Needs a different design — see options in the conversation: cap `hnsw.max_scan_tuples`, route narrow categories to an exact scan over their books, or partial HNSW indexes per persona.
- [x] Fallback grader (`_grade_context`, `services/chat/context_grading.py`): stop the final cut to 25 from dropping keyword hits. Same fix as the reranker.
- [x] `keyword_search`: run on its own DB session so its `SET LOCAL statement_timeout = '5000'` doesn't leak into later vector searches in the same turn.

## 3. After the A/B result

- [ ] Suffix-tolerant keyword matching (`ھوزۇرۇم` → `ھوزۇرۇمنى`) for `search_keyword_phrase`. Code is in Task 6 of the original plan. Ship and measure it separately.

## 4. Lower priority

- [ ] Exact-phrase leg (`exact_phrase_chunk_search`): multiple quoted phrases run `keyword_search` concurrently via `asyncio.gather` on ONE session, which asyncpg doesn't allow; give each phrase its own session (the agent's keyword tool already does).
- [ ] Per-book quota: "what does [author] say about X" for prolific authors gives each book ≥3 slots and can exceed 25 chunks. Allocate by relevance instead.
- [ ] Reranker dedup by (book, page) keeps the first chunk seen; keep the highest-scoring one instead.
- [ ] Legacy prompt step 6b refers to "the relationship query modifier above", which doesn't exist. Remove it (moot if the legacy prompt is deleted).
- [ ] Fix the 6 already-failing tests: 3 in `tests/app/db/bookmarks_repository_test.py`, 3 in `tests/app/llm/models_test.py`.

## Not now

- Hybrid vector + keyword fusion (RRF): removed on purpose in the keyword-search rework; revisit only if the A/B shows keyword misses.
- Query/document embedding task prefixes: needs a full corpus re-embed.
