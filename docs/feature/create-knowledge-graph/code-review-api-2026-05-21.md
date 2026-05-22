# API Code Review — 2026-05-21

**Branch:** feature/create-knowledge-graph
**Verdict:** Request changes

## Issues

---

### `services/backend/api/endpoints/books.py`

- **[blocking]** Line 1443 — `logger.info(...)` uses an f-string-style raw logger call instead of `log_json`. All structured logging must go through `log_json(logger, logging.INFO, "message", key=value)`.
  ```python
  # Fix:
  log_json(logger, logging.INFO, "manually enqueued knowledge_graph_job", book_id=book_id, user=current_user.email)
  ```

- **[blocking]** Line 1445 — `logger.exception(...)` is used; must be `log_json(logger, logging.ERROR, ...)`. The exception itself should be captured as a structured field.
  ```python
  # Fix:
  log_json(logger, logging.ERROR, "failed to enqueue knowledge_graph_job", book_id=book_id, error=str(exc))
  ```

- **[blocking]** Line 1446 — `HTTPException(status_code=500, detail="Failed to enqueue Knowledge Graph job")` is a hardcoded English string visible to the client. All `HTTPException.detail` values must use `t("errors.key")`.
  Add a new error key (e.g. `errors.graph_enqueue_failed`) to both locale files and replace the literal string.

- **[suggestion]** Lines 1438–1442 — `arq` is imported inside the function body and a fresh Redis pool is created and destroyed on every request. This mirrors the pattern in similar reprocess endpoints in this file (which has the same issue), but it means no connection reuse. Consider injecting the Redis pool via `Depends()` as the shared pool the app already holds.

- **[suggestion]** Lines 963–975 — Two bare `logger.info(f"DEBUG: ...")` f-string calls exist in the existing file. Not introduced by this branch but worth noting for a follow-up cleanup.

---

### `packages/backend-core/app/db/repositories/books.py`

- **[blocking]** Lines 163–170, 276–284, 431–439 — `GraphRepository` is imported inline inside repository method bodies three times (`from app.db.repositories.graph import GraphRepository`). Inline imports inside methods are a code smell and violate the architecture convention. Move the import to the top of the file alongside other imports.

- **[suggestion]** Lines 163–170, 276–284, 431–439 — A PostgreSQL repository instantiating and calling a Memgraph repository crosses the repository layer. The preferred pattern is to do this cross-store assembly in a service layer or the endpoint. For now this works because both calls are resilient (wrapped in `try/finally` and the graph methods catch exceptions internally), but future code should avoid deepening this coupling.

---

### `packages/backend-core/app/services/rag/agent/tools.py`

- **[blocking]** Line ~472 — `llm_response = await llm.ainvoke(prompt)` where `llm` is a `ProtectedLLM`. `ProtectedLLM.ainvoke` already returns a `str` (it calls `_extract_message_text` internally), so `re.split(r"...", llm_response)` is safe. ✓ No issue here — confirmed via `models.py:314`.

- **[suggestion]** The `query_knowledge_graph` `@tool` stub at line ~172 returns `""`. This is consistent with every other tool stub in this file, so it follows the established pattern. ✓

---

### `packages/backend-core/app/models/schemas.py`

- **[suggestion]** Line ~77 — `has_graph: bool = False` — no issues. Consistent with `has_summary`.

---

### `packages/backend-core/app/core/config.py`

- **[suggestion]** Line ~90 — `memgraph_url: str = os.getenv("MEMGRAPH_URL", "bolt://localhost:37687")` — consistent with the existing pattern in this file (all other settings also use `os.getenv`). ✓ Not a violation.

---

## Summary

The core implementation is structurally sound — the new endpoint is auth-guarded, 404 is handled, the `GraphRepository` is consumed with `try/finally` in all but one place (see worker review). Three blocking issues are present: two logging calls use the raw `logger.*` API instead of `log_json`, and one `HTTPException` detail contains a hardcoded English string. Additionally, three inline imports of `GraphRepository` inside `BooksRepository` methods should be moved to the module top. Fix the three blockers before merging.
