# API Code Review — 2026-07-21

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Request changes

## Issues

### `packages/backend-core/app/services/rag/agent/deterministic_handler.py`

- **[blocking]** Line 300 — `contents.append(types.Content(role="tool", parts=parts))` sends function-response turns with `role="tool"`. The installed `google-genai` SDK's own `Content.role` docstring states the value "Must be either 'user' or 'model'" — there is no `"tool"` role in the Gemini API. Since `role` is a plain `Optional[str]` field, this won't raise client-side, but the Gemini API is expected to reject or silently mishandle the second `generate_content` call in the loop whenever a tool is actually invoked. The new unit test (`test_llm_analyze_query_tool_calling`) mocks `generate_content` directly, so it can't catch this — it never exercises real API validation. Change to `role="user"` (the standard pattern: model turn with `functionCall` parts, followed by a user turn with `functionResponse` parts) and verify against the live API or a recorded fixture, not a bare mock.
- **[blocking]** Lines 134–330 — `_llm_analyze_query` replaced a single deterministic DB lookup + one LLM call with an agentic loop of up to 8 sequential Gemini round-trips per query, gated only by prompt text ("do NOT call the tools again") rather than deterministic control flow. This is a real latency/cost regression on the hot path for every chat message (Stage 1.5 of every query), and the `for _ in range(8): ... else: raise ValueError(...)` guard implies this was already observed to loop past a single turn in testing. Worth confirming the cost/latency tradeoff was an intentional, discussed decision — if not, consider keeping the fast deterministic DB checks (as before) and only using the LLM to decide intent/signals, rather than making title/author resolution depend on model tool-call compliance.
- **[suggestion]** Lines 963–990 (`_path_named_title`) — when `matched_book_ids` is already populated from `signals`, the branch skips emitting a `find_books_by_title` tool-call observation. `observations` feeds `_populate_ctx_from_observations` (`agent_tools_called`, `agent_steps` eval metadata), so eval/observability counts will now under-report actual work done for this path. Likely an acceptable tradeoff but worth a one-line note if intentional.

### `packages/backend-core/app/services/rag/retrieval.py`

- **[blocking]** Lines 141–219 — the new fuzzy-keyword fallback in `vector_search` is commented as being "for local dev dumps" but has no environment guard (`settings.environment` exists and is used elsewhere in `core/config.py`, but not checked here). In production, any legitimate zero-hit vector search (a real "no relevant passage" case) now falls through to a full unbounded scan of every chunk for the given `book_ids`, scored with `difflib.SequenceMatcher` per query word per chunk word, and assigned a fabricated similarity score (`0.8 + 0.05 * match_count`, i.e. 0.8–1.0+) that reads as high-confidence to downstream consumers.
- **[blocking]** Line 277 (`if top_results is not None: await cache_service.set(search_cache_key, top_results, ...)`) — the fuzzy fallback's fabricated results get written to the **same** cache key used for real vector-search results, for the full `cache_ttl_rag_query` TTL. Once a query hits this path, keyword-matched (possibly irrelevant) chunks are served and cached as if they were genuine semantic matches, degrading answer quality with no way to distinguish real vs. fallback results downstream. At minimum, gate this block behind `settings.environment` (or a dedicated feature flag), and if kept for production use, use a distinct cache key/shorter TTL and a lower score band that doesn't overlap with genuine vector-search scores.
- **[suggestion]** Same block — no cap on the number of chunks scanned before ranking (only the final `top_results` list is capped to `settings.rag_top_k`). For a book with many chunks this is an uncapped `SequenceMatcher` pass over the full text on every fallback trigger; consider an upper bound on rows fetched/scored.

### `packages/backend-core/app/services/rag/agent/tools.py`

- **[suggestion]** Lines 749–812 — the fuzzy title/author matching added to `_run_find_books_by_title` (normalize → prefix/`SequenceMatcher` word matching) duplicates the same pattern just added in `retrieval.py`. Consider extracting a shared `fuzzy_word_match(query_words, candidate_text)` helper into `app/services/rag/utils.py` so both call sites (and future ones) share one tuned implementation instead of two independently-tunable copies of the same heuristic (thresholds `0.85` vs `0.8`, same Uyghur suffix hack duplicated).
- **[suggestion]** Line 754 — the single-word false-positive filter (`len(result) == 1 and len(result[0]["title"].split()) == 1` combined with `len(q_words) >= 3`) is a fairly specific heuristic with magic numbers and no dedicated test. Worth at least one unit test locking in the intended behavior (e.g. a one-word title incorrectly matching a long multi-word query gets dropped).

### `packages/backend-core/app/services/rag/agent/graph_router.py`

- **[blocking]** Lines 146–152 — `_select_route` now checks `has_title` **before** `intent == "catalog"`, reversing the prior precedence. This changes routing for any query that both matches a book title/keyword and is classified as a catalog query (e.g. "do you have book X?", "who wrote «X»?") from `_path_catalog` to `_path_named_title` — different retrieval behavior (passage/summary on a resolved book vs. catalog existence/listing flow). No test was added or updated for this reordering (existing catalog tests in `deterministic_router_test.py` exercise `execute_path` directly with a fixed intent, not `_select_route`'s precedence), so there's no regression coverage confirming this is the intended new behavior for catalog-shaped questions that also resolve a title.

### `packages/backend-core/tests/app/services/deterministic_router_test.py`

- **[suggestion]** Only one new test (`test_llm_analyze_query_tool_calling`) was added, covering solely the `find_books_by_title` happy-path (one tool call → match → final JSON). Given the size of the new logic, none of the following are covered:
  - `get_books_by_author` tool-call path
  - the `for _ in range(8): ... else: raise ValueError(...)` exhaustion path and its fallback in `extract_signals`'s `except` block
  - the DB-fallback branch when `_llm_analyze_query` raises
  - the reordered `_select_route` precedence (has_title vs. catalog)
  - the new fuzzy fallbacks in `tools.py` and `retrieval.py`

## Summary

The core intent (letting the query-analysis LLM call DB tools directly instead of always running deterministic DB checks upfront) is reasonable, but this diff has one likely-broken piece (`role="tool"` is not a valid Gemini `Content` role, per the SDK's own docstring, and would only surface once tools are actually invoked against the real API — not caught by the fully-mocked test) and one significant behavior risk (the new fuzzy-match fallbacks in `retrieval.py`/`tools.py` are un-gated for production and get cached alongside genuine results, undermining answer relevance whenever vector search legitimately returns nothing). The `graph_router.py` precedence swap also changes catalog-vs-title routing with no accompanying test. Recommend fixing the `Content` role, gating or removing the production fuzzy fallback in `retrieval.py`, and adding coverage for the reordered routing and the untested code paths before merging.
