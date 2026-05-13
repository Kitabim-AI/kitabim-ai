# API Code Review — 2026-05-12

**Branch:** feature/optomize-chunking
**Verdict:** Approve with suggestions

## Issues

### `services/backend/api/endpoints/chat.py`

- **[blocking]** Line 152 — `except Exception: pass` silently swallows failures from `record_book_error` with no logging. The skill requires every caught exception to be logged at minimum. Fix:
  ```python
  except Exception as e:
      log_json(logger, logging.WARNING, "record_book_error failed", error=str(e))
  ```

### `packages/backend-core/app/services/rag/retrieval.py`

- **[suggestion]** Lines 148–149 — `sa_text("categories && :cats").bindparams(cats=categories)` uses a different binding pattern from the rest of the codebase, which consistently uses `CAST(:categories AS text[])` (see `chunks.py`, `book_summaries.py`, `books.py`). Both work with asyncpg, but aligning to the established pattern reduces the risk of type-coercion surprises in edge cases.

### `packages/backend-core/app/services/rag/context.py`

- **[suggestion]** Line 40 — `is_follow_up` is set by `FollowUpHandler` (both `handle` and `handle_stream`) but is not consumed anywhere in the codebase. The inline comment says "guards context_book_ids usage," but no guard actually reads this field. Either wire it into the agent loop (e.g., to allow `context_book_ids` usage only when `is_follow_up` is True) or remove it to avoid dead state accumulating on `QueryContext`.

### `apps/frontend/src/components/library/HomeView.tsx`

- **[suggestion]** Lines 26–28 — Three separate calls to `useAppContext()` in the same component (`setView`/`chat` in the main destructure, `loadMoreShelf` in a second call, `fontSize` in a third). These should all be destructured from one call at the top of the component.

### `apps/frontend/src/components/chat/ChatInterface.tsx`

- **[suggestion]** Line 130 — Empty dep array `[]` in the auto-submit `useEffect` references `isGlobal`, `chatInput`, `chatMessages`, and `onSendMessage` from the closure without listing them as deps. The intent is deliberate (fire once on mount), but `react-hooks/exhaustive-deps` will warn. Add `// eslint-disable-next-line react-hooks/exhaustive-deps` directly above the dep array, and keep the existing comment explaining why the empty array is intentional.

## Summary

The chunking job upsert rewrite is the most significant change and is correct — the unique constraint on `(book_id, page_number, chunk_index)` backs the `index_elements`, the partial-delete + upsert cleanly replaces the delete-all + re-insert pattern, and `embedding` / `embedding_v1` are reset to `null` so the embedding scanner picks them up. The RAG changes are a clean extension: the new `get_book_summary` tool, `is_fast_handler` gating, and category-filter propagation all follow established patterns. One blocking issue: the silent `except Exception: pass` in `chat.py` must log before merging.
