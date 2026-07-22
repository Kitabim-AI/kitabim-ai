# Worker Code Review — 2026-07-22

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Request changes

## Issues

### `services/worker/worker.py`

- **[blocking]** Line 36/61 — The diff replaced `from scanners.auto_correct_scanner import run_auto_correct_scanner` with `from scanners.batch_ocr_poller_scanner import run_batch_ocr_poller_scanner` instead of adding the new import alongside the old one. `run_auto_correct_scanner` is still referenced in `cron_jobs` at line 61, so the module now raises `NameError: name 'run_auto_correct_scanner' is not defined` at import time — the entire worker process fails to start, taking down every pipeline (not just batch OCR). Fix: restore `from scanners.auto_correct_scanner import run_auto_correct_scanner` as its own import line.

### `services/worker/jobs/ocr_job.py`

- **[blocking]** Lines 178–193 — The batch-mode branch only wraps `doc.close()` in a `finally`; there is no `except` around `submit_batch_ocr_job(...)`. If that call raises for any reason other than the Gemini `batches.create` call itself (e.g. `storage.upload_bytes` GCS failure, `_build_ocr_prompt` DB error, a `fitz` rendering error while building the JSONL), the exception propagates out of `ocr_job` entirely. The claimed pages are left at `ocr_milestone="in_progress"` with no error recorded, no `PipelineEvent`, and no `retry_count` increment — violating the project rule that job functions catch exceptions per-batch and never propagate an exception that aborts the whole job. Compare to the existing "failed to obtain PDF" handling a few lines above (lines 133–169) which correctly marks pages failed on any exception. Fix: wrap the batch submission call in `try/except`, and on any exception mark `locked_page_ids` `ocr_milestone="failed"`, increment `retry_count`, emit `ocr_failed` `PipelineEvent`s, and update the book milestone — mirroring the PDF-download failure path.

### `services/worker/scanners/stale_watchdog_scanner.py` (interaction with new batch flow)

- **[blocking]** Lines 23, 83–85 — `STALE_THRESHOLD_MINUTES = 30` resets any page stuck at `ocr_milestone == "in_progress"` back to `idle` after 30 minutes, **even when the claiming worker's heartbeat is still active** (the `else` branch at lines 83–85 applies the same 30-minute ceiling to live workers). Gemini Batch API jobs are expected to run up to `gemini_batch_ocr_timeout_hours` (default 24 hours; see `batch_ocr_service.py:170-172`), but nothing in this PR exempts pages that belong to an in-flight `BatchOCRJob` from the watchdog. 30 minutes after a batch is submitted, the watchdog will reset those pages to `idle`, `ocr_scanner` will re-claim and re-dispatch a second OCR job for the same pages, and when the original batch later completes, `_ingest_batch_ocr_results` will race with (or silently clobber/be clobbered by) the second job's writes to `Page.text`. Fix: exempt pages with an active `batch_ocr_jobs` row (`status IN ('submitting','submitted','running')`) from the 30-minute threshold, or track batch-mode on the `Page` row so the watchdog can apply a longer/independent threshold.

### `services/worker/scanners/batch_ocr_poller_scanner.py`

- No issues found. Session isolation, error handling (catches and logs, does not re-raise, matching the "scanner must not crash the worker" rule), and early-return-when-nothing-to-do are all correct.

### `packages/backend-core/app/services/batch_ocr_service.py` (worker-consumed logic)

- **[blocking]** `submit_batch_ocr_job` (lines 128–161) — When `client.batches.create()` fails, pages are correctly marked `ocr_milestone="failed"` (lines 147–158), but the function never calls `BookMilestoneService.update_book_milestone_for_step`. Since `ocr_job.py`'s batch branch `return`s immediately after calling this function (no further book-milestone recompute happens on that code path), a submission failure leaves `Book.ocr_milestone` stuck at `"in_progress"` (set earlier by `ocr_scanner`) indefinitely, silently stalling the book's pipeline. Fix: call `await BookMilestoneService.update_book_milestone_for_step(session, book_id, "ocr")` + commit whenever `status == "failed"`.
- **[suggestion]** Lines 129, 279–280, 307–309, 316–319, 397–398 — Five call sites use `logger.error(f"...")` / `logger.warning(f"...")` with string interpolation instead of the project's `log_json(logger, level, "message", key=value)` pattern used everywhere else in this same file. Convert each to `log_json` with structured fields (`job_id=`, `error=str(exc)`, etc.) for consistent, parseable logs.
- **[suggestion]** Line 131 — `err_msg = str(exc)` is not truncated to `[:500]` before being written into `Page.error` at line 155, unlike the per-page ingest path (line 344) and the existing online OCR path, both of which truncate. `Text` columns have no length cap so this isn't a DB error, but it's inconsistent with the established convention.
- **[suggestion]** Lines 364–395 (`_ingest_batch_ocr_results`) — When a Gemini response has no `candidates` (e.g. blocked/empty content), the page is unconditionally marked `ocr_milestone="succeeded"` with blank text and no error signal. The online path only ever writes blank text after `ocr_max_retry_count` retries, with an explicit `WARNING` log and a `"skipped": True` event flag. As written, a single empty batch response permanently and silently blanks a page with no way to detect or retry it.

## Summary

The batch OCR poller scanner itself is solid, but the feature has one immediate showstopper — `worker.py` will crash on startup due to the dropped `auto_correct_scanner` import — plus two integration gaps with existing infra (stale watchdog will fight the new 24-hour batch timeout, and a batch submission failure never surfaces at the book level) that need to be fixed before this is safe to deploy.
