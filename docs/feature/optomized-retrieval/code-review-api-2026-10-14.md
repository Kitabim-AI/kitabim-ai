# API Code Review — 2026-10-14

**Branch:** feature/optomized-retrieval
**Scope:** LLM spell-correction feature (already merged; reviewed retroactively) — migrations 090/091, `llm_spell_check_service.py`, `batch_llm_spell_check_service.py`, `llm_spell_check_job.py`, `batch_llm_spell_check_poller_scanner.py`, the two trigger endpoints in `books_router.py`.
**Verdict:** Request changes

## Issues

### `services/backend/api/endpoints/books_router.py` and `services/worker/jobs/llm_spell_check_job.py` — pages stuck in `in_progress`

- **[blocking]** Lines 2353-2357, 2426-2430 — `enqueue_job(..., _job_id="llm_spell_check:book:{id}" / "llm_spell_check:page:{id}")` uses a fixed job id. arq returns `None` (no exception) when a job **or its kept result** with that id exists, and results are kept for 3600 s by default (`worker.py` doesn't override `keep_result`). Re-running the same book or page within an hour of the last run marks the pages `in_progress`, the enqueue is silently dropped, and they stay `in_progress` permanently. Nothing resets them (by design, `stale_watchdog_scanner` doesn't cover this status), so after that the per-page endpoint returns 409 and the per-book endpoint skips them. Fix: treat a `None` return as failure (reset to idle and return 409), or make the id unique per trigger (`...:{int(time.time())}`, as `ocr_scanner.py:90` does).
- **[blocking]** Same root cause, other triggers: a worker restart or deploy during a live per-book job, a `queue_job_timeout` cancellation, or an exception that escapes `process_page` (see below) also leaves the remaining pages `in_progress` with no recovery except manual SQL. Fix: add a small reset path, either an admin "reset stuck" action or treating `in_progress` with `last_updated` older than N hours as eligible in `reprocess_llm_spell_check`.
- **[suggestion]** Lines 2305-2311 — the per-book trigger re-sends every non-in-progress page, including ones already `succeeded`. Each re-run pays for the whole book again and runs a second LLM pass over text that was already corrected. Consider limiting it to `idle`/`failed` by default and adding a `force` flag.
- **[suggestion]** Lines 2305, 2336-2343, 2376-2383 — the endpoint calls `session.execute(select/update(Page))` directly. Move these into `PagesRepository` (e.g. `list_ids_for_llm_spell_check`, `bulk_set_llm_spell_check_status`).

### `packages/backend-core/app/services/llm_spell_check_service.py` / both apply paths — data integrity

- **[blocking]** Neither the live path (`llm_spell_check_job.py:58`) nor the batch path (`batch_llm_spell_check_service.py:199`) clears `PageSpellIssue` rows when it rewrites `page.text`. Those rows store `char_offset`/`char_end` into the old text. The manual-edit endpoint (`books_router.py:2631-2639`) deletes them for exactly this reason ("offsets are now invalid"). After an LLM correction changes a word's length, applying any still-open dictionary issue (`spell_check_router.py:419-423`, `auto_correct_service.py:142-144`) splices at the wrong offsets and corrupts the page text, and neither splice checks that `text[start:end] == issue.word`. Fix: when `corrected != original`, delete the page's `PageSpellIssue` rows and set `spell_check_milestone = idle` in the same commit, as manual edit does. Add the `text[start:end]` guard to both splice sites as well.
- **[suggestion]** The LLM output is written without `normalize_uyghur_chars` / `normalize_markdown`, which the manual-edit path applies (`books_router.py:2615-2616`). Gemini can emit Arabic-script lookalikes (e.g. ي vs ى), which would then hurt dictionary lookups and retrieval. Normalize in `correct_page_text` and in the batch ingest before `_validate_correction`.
- **[suggestion]** The original text isn't kept, so a bad correction can't be undone and there's no way to measure what the LLM changed. The only guardrail is a ±30% length check (lines 31-48), so a same-length rephrase passes. Consider storing the pre-correction text or a word-level diff (a `page_text_revisions` row or a `llm_spell_check_diff` JSONB). This would also let you add the dictionary-based per-word check the design deferred.
- **[suggestion]** Pages with empty or `None` text are still sent to Gemini and always fail validation, which wastes calls. Filter `text IS NOT NULL AND text <> ''` when selecting `page_ids`.

### `services/worker/jobs/llm_spell_check_job.py`

- **[suggestion]** Lines 63-67 — the `except` block doesn't `await session.rollback()`. If the failure was in the success-path `commit()`, the failed-status update and commit run on a broken transaction and raise again. That escapes `process_page`, and because `gather` (line 77) has no `return_exceptions=True`, the error propagates and leaves this page `in_progress` (see the blocking issue above). Fix: roll back first, and use `asyncio.gather(..., return_exceptions=True)`.
- **[suggestion]** Lines 36-57 — the session's connection is checked out at `session.get` and held for the whole Gemini call. With `max_parallel_llm_spell_check=6`, that's 6 pooled connections idle for seconds each. Load the text, close the session, call the LLM, then open a fresh session to write. That also narrows the window in which a concurrent manual edit gets overwritten.

### `packages/backend-core/app/services/batch_llm_spell_check_service.py`

- **[blocking]** Paired with `batch_llm_spell_check_poller_scanner.py:26-35`: the poller returns early when `llm_spell_check_batch_enabled` is false. If an admin turns the flag off while a batch is in flight, that batch is never ingested and its pages stay `in_progress` permanently. The flag should only choose the submit path. The poller should always drain existing `submitting`/`running` rows (it's a cheap no-op query when there are none).
- **[suggestion]** Lines 188-199 — the correction is validated against and written over the **current** `page.text`, but it was generated from the text at submit time. If the page was edited in between (manual edit, dictionary apply), the edit is silently lost. Store a hash of the submitted text per page (or compare `last_updated` to `submitted_at`) and skip, marking failed, if it changed.
- **[suggestion]** Lines 95-103, 157, 175 — the sync `genai.Client` calls (`files.upload`, `batches.create`, `batches.get`, `files.download`) block the event loop. In `submit_batch_llm_spell_check` this happens inside an API request handler while it uploads a whole book's JSONL. Wrap them in `asyncio.to_thread`, or use `client.aio`.
- **[suggestion]** Lines 103-124 — the Gemini batch is created before the DB commit. If the commit fails, a paid batch is left untracked. Insert the tracking row first (or log `batch_job.name` before committing).
- **[suggestion]** Lines 64, 69, 142 — `session.execute(select(...))` is used inside a service. Move it to repository methods. This mirrors `batch_history_extraction_service.py`, so it's consistent with existing code but still a layering violation.
- **[suggestion]** Lines 172, 177, 211 — `logger.warning(f"...")` / `logger.error(f"...")` should use `log_json(..., job_id=..., page_id=..., error=str(e))`.
- **[suggestion]** Lines 179-229 — if the output can't be read (`result_bytes is None`), every page is marked failed but the job is still recorded as `status="succeeded"`. Set `job.status="failed"` and `job.error` in that case.

### `packages/backend-core/app/db/models.py` / migrations 090, 091

- **[suggestion]** `Page.llm_spell_check_status` (models.py:212) and `BatchLlmSpellCheckJob.status` have no `CheckConstraint`, even though they hold enum-like values. Add one, e.g. `CHECK (llm_spell_check_status IN ('idle','in_progress','succeeded','failed'))`, in a new migration.

## Summary

The overall design (one shared prompt and validator for both paths, a separate status column, admin-only triggers, a flag-gated batch path mirroring the existing batch services) is sound. It needs two fixes before more books go through it. First, an LLM rewrite leaves stale-offset `PageSpellIssue` rows behind, so applying a later dictionary correction can corrupt page text. Second, several ordinary sequences (re-running within an hour, a worker restart, turning the batch flag off mid-flight) leave pages permanently `in_progress` with no recovery path. The rest is hardening and layering cleanup.
