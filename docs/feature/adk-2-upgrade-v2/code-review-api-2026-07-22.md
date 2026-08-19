# API Code Review — 2026-07-22

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Request changes

## Issues

### `packages/backend-core/app/db/models.py`

- No blocking issues. `BatchOCRJob` has a sequential migration, a `CheckConstraint` on `status`, `ondelete="CASCADE"` on the `book_id` FK, and correct `Mapped[Optional[...]]` nullability. `updated_at` has `onupdate=func.now()` matching the "mutable models" convention.
- **[suggestion]** Lines ~278–280 (post-diff) — Double blank line left before the `Chunk` class after the new `BatchOCRJob` block; minor formatting cleanup.

### `packages/backend-core/migrations/070_add_batch_ocr_jobs.sql` / `070_rollback_add_batch_ocr_jobs.sql`

- No issues found. Sequential numbering is correct (last existing migration was `069_...`), indexes are present on `book_id` and `status`, rollback drops the table with `CASCADE`.

### `packages/backend-core/app/db/seeds.py`

- **[suggestion]** Lines 37, 42 — `ocr_batch_size_per_job` and `gemini_batch_ocr_poll_interval` are seeded but never read anywhere in the new code (confirmed: no references outside `seeds.py`). `submit_batch_ocr_job` batches whatever page list `ocr_job` hands it (sized by the scanner's own grouping, unrelated to this key), and the poller's cron cadence is a fixed `cron(run_batch_ocr_poller_scanner)` in `worker.py` with no schedule argument — `gemini_batch_ocr_poll_interval` is dead configuration. Either wire these into `batch_ocr_service.py`/the cron registration, or drop them until implemented so admins aren't misled into thinking they control behavior.

### `packages/backend-core/app/services/batch_ocr_service.py`

- **[blocking]** `submit_batch_ocr_job` (lines 128–161) — On submission failure, pages are marked failed but `BookMilestoneService.update_book_milestone_for_step` is never called, so the book-level milestone never reflects the failure (see companion worker review for the full call-path explanation — `ocr_job.py` returns immediately after this call with no further milestone recompute on the batch path). Fix here: call and commit the book milestone update inside the `status == "failed"` branch.
- **[suggestion]** Lines 129, 279–280, 307–309, 316–319, 397–398 — Multiple `logger.error(f"...")` / `logger.warning(f"...")` calls bypass the project's `log_json(logger, level, "message", key=value)` convention used elsewhere in this same file (e.g. lines 119–127, 195–201). Convert to `log_json` for structured, greppable logs.
- **[suggestion]** Line 131 — `err_msg = str(exc)` is not truncated to `[:500]` before landing in `Page.error` (line 155), unlike the per-page ingest path (line 344) which correctly truncates.
- **[suggestion]** Lines 364–395 — A Gemini response with no `candidates` is treated as a silent success (blank text, `ocr_milestone="succeeded"`, no error/warning), unlike the online OCR path which only writes blank text after exhausting retries and logs a `WARNING` with a `"skipped"` flag. Recommend treating an empty-candidates response as a failure (increment retry, mark `failed`) rather than a silent blank success.
- **[suggestion]** `model = ocr_gemini_model.replace("models/", "", 1) if ...` (lines 102–106) — Minor duplication risk: verify this normalization matches whatever `ocr_page_with_gemini` (the online path) does with the same `ocr_gemini_model` value, so behavior doesn't diverge between the two modes for the same configured model string.

### `packages/backend-core/tests/app/services/batch_ocr_service_test.py`

- **[suggestion]** Only two happy-path tests exist (`submit_batch_ocr_job` success, `poll_and_process_batch_ocr_jobs` success/succeeded-state ingestion). Missing per the testing checklist:
  - Submission failure path (`client.batches.create` raises) — should assert `Page.ocr_milestone` update to `"failed"` with `retry_count` incremented, not just that no exception propagates.
  - Timeout path (`created_at` older than `ocr_batch_timeout_hours`).
  - `FAILED` / `CANCELLED` Gemini batch state handling.
  - No-active-jobs early return (`active_jobs` empty → `processed_count == 0`, no Gemini API calls made).
  - `_ingest_batch_ocr_results` per-line error branch (`item.get("error")` truthy) and the empty-candidates edge case.

### `docs/feature/adk-2-upgrade-v2/gemini_batch_ocr_plan.md`

- **[suggestion]** References migration `067_add_batch_ocr_jobs.sql` (line 51) but the actual migration landed as `070_add_batch_ocr_jobs.sql` — doc is stale relative to the final numbering; update for future readers.

## Summary

Schema, migrations, and model definitions are clean and follow project conventions. The service layer has one correctness gap (book milestone never updates on submission failure, stalling the pipeline silently) plus several logging/consistency nits and thin test coverage limited to happy paths — see the companion worker review for a related, more severe integration bug (stale watchdog vs. batch timeout, and a worker.py import bug that will crash the process on startup).
