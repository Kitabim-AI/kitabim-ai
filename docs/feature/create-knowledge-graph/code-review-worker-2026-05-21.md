# Worker Code Review — 2026-05-21

**Branch:** feature/create-knowledge-graph
**Verdict:** Request changes

## Issues

---

### `services/worker/jobs/knowledge_graph_job.py`

- **[blocking]** Lines 178–180 — `graph_repo` is not closed in a `finally` block. `await graph_repo.close()` is called at line 180 after `await asyncio.gather(*tasks)`, but if `asyncio.gather` raises an exception, execution jumps to the outer `except` at line 183 and `graph_repo.close()` is never called — the Neo4j driver connection pool leaks. Wrap the graph operations in a `try/finally`:
  ```python
  graph_repo = GraphRepository()
  try:
      await graph_repo.init_constraints()
      ...
      await asyncio.gather(*tasks)
  finally:
      await graph_repo.close()
  ```

- **[blocking]** Line 110 — `semaphore = asyncio.Semaphore(5)` is hardcoded. Per convention, all tuneable concurrency limits must come from `SystemConfigsRepository`. The config session is already open at line 60; read the value there:
  ```python
  max_parallel = int(await config_repo.get_value("kg_max_parallel_chunks", "5"))
  ...
  semaphore = asyncio.Semaphore(max_parallel)
  ```

- **[blocking]** Line 62 — `"gemini-3.1-flash-lite"` is used as a fallback model name. The established pattern in the project is `"gemini-2.0-flash-lite"` (confirmed by `summary_job` which uses `gemini_chat_model`). This default will cause a silent model-not-found failure if the config key is missing. At minimum verify the correct model name; at maximum, raise a `RuntimeError` if the config key is unset rather than silently falling back to a potentially wrong value.

- **[suggestion]** Lines 28–53 — `EntityType`, `ExtractedEntity`, `ExtractedRelation`, and `KnowledgeExtraction` Pydantic models are duplicated in `summary_job.py` (with slightly different field names: `GlobalRelation`, `GlobalMetadataExtraction`). Extract these to a shared module, e.g. `packages/backend-core/app/services/knowledge_graph_service.py`, and import from there in both jobs. This removes a maintenance footprint: if the schema evolves, it needs to be updated in only one place.

- **[suggestion]** Line 173 — Per-chunk exceptions are caught and logged with `logging.ERROR`. Per the logging conventions, expected retryable failures (a single chunk failing LLM extraction) should be `logging.WARNING`. Reserve `ERROR` for unrecoverable job-level failures. Change to `logging.WARNING` for per-chunk extraction failures.

- **[suggestion]** Line 56 — Job start log is present. ✓ Job completion log at line 181 is present. ✓

- **[suggestion]** Line 25 — Logger name `"app.worker.knowledge_graph_job"` — correct convention. ✓

---

### `services/worker/jobs/summary_job.py`

- **[blocking]** Lines 195–236 — `graph_repo = GraphRepository()` is used with a `try/finally` block (`finally: await graph_repo.close()`). This is correct. ✓

- **[suggestion]** Lines 42–72 — `EntityType`, `ExtractedEntity`, `GlobalRelation`, `GlobalMetadataExtraction` Pydantic models are defined inline in this file, duplicating similar definitions in `knowledge_graph_job.py`. See suggestion above about extracting to a shared module.

- **[suggestion]** Lines 212–213 — `global_llm = ChatGoogleGenerativeAI(...)` instantiates the LLM directly instead of going through `build_text_llm()` / `ProtectedLLM`. This bypasses the circuit breaker and rate limiter that protect the rest of the system from Gemini API failures. The summary LLM call should be wrapped in the same circuit breaker infrastructure.

---

### `services/worker/scanners/pipeline_driver.py`

- **[suggestion]** Lines 252–257 — `knowledge_graph_job` is enqueued with `_job_id=f"knowledge_graph:{book_id}"` — correct deduplication. ✓

- **[suggestion]** Comment update at line 248 is accurate. ✓

---

### `services/worker/worker.py`

- **[suggestion]** `knowledge_graph_job` is registered in `WorkerSettings.functions`. ✓ No scanner/cron registration is needed since it's triggered by `pipeline_driver`. ✓

---

### `packages/backend-core/app/db/repositories/graph.py`

- **[blocking]** Lines 46, 232, 246 — Raw `logger.debug(...)` and `logger.warning(...)` calls use string interpolation instead of `log_json`. Must use `log_json(logger, logging.WARNING, "message", error=str(exc))`.
  ```python
  # Line 46 fix:
  log_json(logger, logging.DEBUG, "constraint already exists or warning", detail=str(exc))
  # Line 232 fix:
  log_json(logger, logging.WARNING, "failed to check book existence in Memgraph", error=str(exc))
  # Line 246 fix:
  log_json(logger, logging.WARNING, "failed to check batch book existence in Memgraph", error=str(exc))
  ```

- **[suggestion]** `GraphRepository` creates a new driver (connection pool) on each instantiation. For the RAG agent tool path — where a fresh `GraphRepository()` is created per user request — this creates a new driver per query. Consider making the driver a module-level singleton (similar to how the SQLAlchemy `engine` is a singleton) and having `GraphRepository` accept it as a dependency. For now this is functionally correct but may create connection overhead at scale.

---

## Summary

Two blocking issues stand out: (1) `graph_repo` is not closed in a `finally` block in `knowledge_graph_job.py`, which will leak Neo4j driver connections on any job failure; (2) the concurrency semaphore limit is hardcoded `5` instead of being read from `SystemConfigsRepository`. Additionally, three `log_json` violations exist in `graph.py`. The Pydantic model duplication between the two jobs and the direct Gemini client instantiation bypassing the circuit breaker in `summary_job.py` are the most impactful suggestions. Fix the two blocking issues and the three `log_json` violations before merging.
