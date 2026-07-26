# Worker Code Review — 2026-07-22 (Batch Embedding)

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Request changes

## Issues

### `services/worker/scanners/embedding_scanner.py`

- **[blocking]** Lines 75-94 — The new `if batch_enabled: ... else: ...` block, including `await submit_batch_embedding_job(session, page_ids)` and (in the `else` branch) `await redis.enqueue_job(...)`, is nested **inside** the `async with db_session.async_session_factory() as session:` block. Before this change, `redis.enqueue_job(...)` ran after the block exited (dedented, session already closed and committed) — see the git diff, which shows it moving from column 0 to column 8. This violates the scanner-correctness rule that dispatch happens after the session is closed. Now the claiming session's DB connection is held open for the duration of `submit_batch_embedding_job`'s synchronous Gemini file-upload + `batches.create` network calls, unnecessarily tying up a pooled connection (worker pool is only 5-10 connections) for the length of an external API round trip. Fix: dedent the `if batch_enabled: / else:` block to after the `async with` block, matching the original pattern.

### `services/worker/scanners/stale_watchdog_scanner.py`

- No issues found. `active_batch_page_ids` now unions page IDs from both `BatchOCRJob` and `BatchEmbeddingJob` (`status.in_(["submitting", "submitted", "running"])`), so batch-embedding pages are correctly exempted from the 30-minute `STALE_THRESHOLD_MINUTES` reset — this is exactly the fix the plan called for, and it mirrors the existing `BatchOCRJob` exemption rather than replacing it.

### `services/worker/tests/scanners/stale_watchdog_scanner_test.py`

- No issues found. Existing tests updated for the extra `execute()` call, plus a new dedicated `test_stale_watchdog_exempts_active_batch_embedding_pages` asserting a page locked by an active `BatchEmbeddingJob` is skipped by the reset even when its `claimed_at` is well past the 30-minute threshold.

### `services/worker/scanners/batch_embedding_poller_scanner.py`

- No issues found. Single session for the whole poll cycle, top-level `try/except` that logs and does not re-raise (matching the "a scanner failure must not crash the worker" rule), consistent with `batch_ocr_poller_scanner.py`.

### `services/worker/worker.py`

- No issues found. `run_batch_embedding_poller_scanner` is imported as a new, additive line and registered as a new `cron(...)` entry alongside the existing ones — this specifically avoids the historical bug where a prior diff replaced (rather than added to) an import line and crashed the entire worker process at startup (`NameError` on `run_auto_correct_scanner`). The unrelated `import functools`/`logging`/`track_request_id` hoist from the bottom of the file to the top is a harmless style cleanup.

### `packages/backend-core/app/services/batch_embedding_service.py` (worker-consumed logic)

- **[blocking]** `poll_and_process_batch_embedding_jobs`, lines 323-328 — `output_file_name = batch_job_info.dest` assumes `dest` is itself a file-name string. `batch_ocr_service.py`'s already-working `_ingest_batch_ocr_results` treats `dest` as an object (`getattr(dest, "file_name", None)`, `getattr(dest, "gcs_uri", None)`), which is the correct shape for this same Gemini client. As written, downloading the output of a real `SUCCEEDED` batch embedding job will fail. See companion API review for the full fix.
- **[blocking]** Same function, lines 120-136 / 420-450 — chunks are sliced into sub-batches by `Chunk.id` order only, with no grouping by page, so a page's chunks can end up split across two `BatchEmbeddingJob` rows. Ingestion determines a page's succeeded/failed status only from the chunks present in the job currently being polled, so a page can be marked `embedding_milestone="succeeded"` while chunks belonging to a sibling job are still `NULL` and will never be retried. See companion API review for detail and fix options.
- **[suggestion]** Lines 471-481 — no `PipelineEvent("embedding_failed")` is emitted when a page's chunks fail within an otherwise-`SUCCEEDED` batch, unlike the `succeeded_pages` branch and unlike `batch_ocr_service.py`'s equivalent failure path. Retries still function via the milestone/`retry_count` write, so this is an observability gap, not a stuck-pipeline bug.

## Summary

The two changes this feature specifically needed to get right on the worker side — exempting batch-embedding pages from the stale watchdog, and registering the new poller in `worker.py` without repeating the OCR feature's import-replacement crash — are both done correctly, with good test coverage for the watchdog exemption. The regression is in `embedding_scanner.py`: batch submission (and the online-mode `redis.enqueue_job`) now runs inside the claiming session's `async with` block instead of after it, and the shared `batch_embedding_service.py` has the same `dest`-attribute and cross-job page-splitting bugs flagged in the companion API review.
