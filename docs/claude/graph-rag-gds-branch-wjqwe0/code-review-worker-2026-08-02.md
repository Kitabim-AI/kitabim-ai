# Worker Code Review — 2026-08-02

**Branch:** claude/graph-rag-gds-branch-wjqwe0
**Verdict:** Request changes

## Issues

### `services/worker/worker.py`

- **[blocking]** Line 48 / `cron_jobs` (lines 79-102) — `run_batch_history_poller_scanner` is imported but **never added to `WorkerSettings.cron_jobs`**. Every sibling batch poller (`run_batch_ocr_poller_scanner` line 87, `run_batch_embedding_poller_scanner` line 90) is registered as a cron job; this one is not. As a result, once `submit_batch_history_extraction_job` creates a `BatchHistoryExtractionJob` row and calls the Gemini Batch API, nothing in the worker will ever poll it — the job sits in `submitted`/`running` forever and results are never ingested into `history_dictionary_staging`. This makes the entire batch extraction path (the main feature of this PR) non-functional in production. Fix: add `cron(run_batch_history_poller_scanner),` to the `cron_jobs` list, e.g. right after `cron(run_batch_ocr_poller_scanner)`.
- **[suggestion]** Lines 7-23 (module docstring) — the cron schedule table documents every other scanner but omits `batch_ocr_poller`, `batch_embedding_poller`, and now `batch_history_poller`. Pre-existing gap, but worth closing while touching this file.

### `services/worker/scanners/batch_history_poller_scanner.py`

- **[blocking]** No test file exists. `services/worker/tests/scanners/` has a `_test.py` for every other scanner (`ocr_scanner_test.py`, `embedding_scanner_test.py`, `graph_resolution_scanner_test.py`, `stale_watchdog_scanner_test.py`, etc.) but nothing for `batch_history_poller_scanner`. Add `services/worker/tests/scanners/batch_history_poller_scanner_test.py` covering: jobs found and processed (assert `poll_and_process_batch_history_jobs` invoked with a mocked session), no active jobs (early return, `processed_count == 0`, no log spam), and the scanner-level `except Exception` path (poll function raises → scanner logs the error via `log_json` and does not re-raise / does not crash the caller).
- **[suggestion]** Structurally this file is fine on its own (session opened, `poll_and_process_batch_history_jobs` awaited, session closed, top-level `try/except` that logs and does not re-raise, mirroring `batch_ocr_poller_scanner.py`/`batch_embedding_poller_scanner.py` exactly). The correctness problems below live in the service it delegates to.

### `services/worker/jobs/history_extraction_job.py`

- **[suggestion]** Lines 43, 63-65, 82, 94-96 — uses `logger.info(f"...")` / `logger.warning(f"...")` string interpolation instead of `log_json(logger, level, "message", key=value)`. This is the only job file in `services/worker/jobs/` that does this (`grep` across all other job files returns zero raw `logger.info/warning/error` calls — they all use `log_json`). Convert, e.g.:
  ```python
  log_json(logger, logging.INFO, "Starting history dictionary extraction task", book_id=book_id)
  ...
  log_json(logger, logging.INFO, "Extraction task completed", book_id=book_id, staged_count=len(staged_items))
  ```
- **[suggestion]** `_run_extraction` (lines 54-102) has no `try/except` around the extraction/batch-submit calls. ARQ will still catch an unhandled exception and mark the job failed, so this isn't a stuck-pipeline bug, but there's no job-specific structured log (`book_id`, `error`) emitted before that happens, making failures harder to trace in log search. Consider wrapping the body in `try/except Exception as exc: log_json(..., book_id=book_id, error=str(exc)[:500]); raise`.
- **[suggestion]** Good catch already fixed in this diff: `db_session.async_session_maker()` (a name that doesn't exist) was corrected to `db_session.async_session_factory()` — no action needed, noting for completeness since it's the kind of bug this checklist targets.

### `services/worker/tests/jobs/history_extraction_job_test.py`

- **[suggestion]** Only two cases are covered: realtime happy path and batch-queued happy path. Missing: the empty-pages case (`get_book_pages` → `[]`, expect `status == "warning"`, `stagedCount == 0`) and a failure case (e.g. `HistoryExtractionService.process_book_pages` or `submit_batch_history_extraction_job` raising, asserting the exception propagates rather than being silently swallowed). Add both to close the gap called out in the review checklist (happy path / failure path / empty input).

### `packages/backend-core/app/services/batch_history_extraction_service.py` (referenced for context — called directly by the scanner)

- **[suggestion]** `poll_and_process_batch_history_jobs` (lines 165-297) selects active jobs with a plain `select(...)`, no `.with_for_update(skip_locked=True)`. If more than one worker replica ever runs this cron concurrently, two instances can both observe the same `SUCCEEDED` batch, both download/parse the output, and both call `_stage_entity` for every entity before either commits `status="succeeded"` — duplicate staging rows (no unique constraint on `history_dictionary_staging.term`, see `packages/backend-core/app/db/models.py:965`). This exactly mirrors the existing pattern in `batch_ocr_service.py` and `batch_embedding_service.py` (not a new regression introduced by this PR), so it's a pre-existing risk rather than something this diff created — but since claiming semantics were explicitly in scope for this review, flagging it here too. If the deployment can ever run >1 worker replica, add `.with_for_update(skip_locked=True)` to the active-jobs query in all three batch pollers.
- **[suggestion]** The per-job loop (lines 183-295) runs entirely inside the single session opened by the scanner (`batch_history_poller_scanner.py:22`), doing Gemini API calls, GCS reads, and `session.commit()` per job, all in one shared session. The per-job `except Exception` (lines 288-295) logs but does not call `await session.rollback()`. If one job's flush/commit fails mid-loop (e.g. an `IntegrityError` while staging an entity), the shared session is left in a broken state and every subsequent job processed in that same scanner tick will spuriously fail too, since nothing resets the session before continuing. Again, this mirrors the identical existing pattern in `batch_ocr_service.py` (lines ~308-316), so it's a pre-existing pattern rather than new — but worth hardening across all three services: either roll back the session in the except block before `continue`, or move to a fresh `async with async_session_factory()` per job.

## Summary

The single-book realtime job (`history_extraction_job.py`) and its test are solid — session handling, config gating, and the `queued_batch` short-circuit are correct, and the previously-broken `async_session_maker` reference was fixed. The critical blocker is that `worker.py` imports `run_batch_history_poller_scanner` but never registers it in `WorkerSettings.cron_jobs`, so the newly-added batch extraction pipeline (the main feature of this PR) will submit Gemini Batch jobs that are never polled or ingested — this must be fixed before merge. The new scanner also ships with zero test coverage, unlike every other scanner in the codebase. Remaining findings (missing `skip_locked` claiming and no session rollback on per-job failure in the poller) are pre-existing patterns shared with `batch_ocr_service.py`/`batch_embedding_service.py`, worth hardening but not unique to this change.
