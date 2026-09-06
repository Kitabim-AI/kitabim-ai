# Design Document: LLM-Based Spell Correction (Gemini)

## Overview
Add an on-demand, admin-triggered spell-correction pass powered by Gemini, runnable per-page or per-book from the existing book-management UI. It runs independently of, and in addition to, the existing dictionary-based spell-check pipeline (`spell_check_scanner`/`spell_check_job`/`auto_correct_service`), and auto-applies its corrections directly to `pages.text`. The per-book (bulk) path can run either as live concurrent calls or as a Gemini Batch API job (feature-flag gated), mirroring the existing `batch_history_extraction_service`/`batch_ocr_service`/`batch_embedding_service` dual-path pattern already used elsewhere in this codebase.

## Problem & Motivation
The existing spell-check pipeline (`packages/backend-core/app/services/spell_check_service.py`) tokenizes page text, generates OCR-confusion/vowel-insertion variants, and flags any token not found in the `words` table (`find_unknown_words`, `spell_check_service.py:256`). This only catches **unknown-word errors** — a token that isn't a real word at all.

It structurally cannot catch **context-dependent real-word errors**: an OCR or typing mistake that happens to produce a different, valid dictionary word (e.g. one Uyghur word substituted for another that looks similar but changes the sentence's meaning). Detecting this requires reading the surrounding sentence and judging whether the word fits semantically — exactly the kind of judgment a dictionary lookup cannot make, but an LLM can.

## Non-Goals (v1)
- **Not replacing** `spell_check_scanner`/`spell_check_job`/`auto_correct_service`. Both stages keep running; this is additive, not a migration off the existing pipeline.
- **Not a pipeline stage.** It does not gate `chunking_milestone`, `pipeline_step`, or any other pipeline field — it is a manual, admin-invoked action, not part of automatic book processing.
- **No live agentic tool-calling.** Per project convention (single-shot structured LLM calls use raw `generate_content`, not an ADK `Agent`/`Runner`), this is one Gemini call per page with the full page text as input — no dictionary-lookup tool invoked mid-reasoning. This applies equally to the batch path (one request per page inside the batch job).
- **No dictionary-based validation of the model's output.** Changed words are not checked against the `words` table before being applied. Deferred to Future Enhancements.
- **No review/approve UI.** Corrections write directly to `pages.text`; there's no diff/approve-reject screen like the existing `SpellCheckPanel`/`ReviewPanel`.
- **Does not re-trigger chunking/embedding.** See Known Limitations.
- **Per-page trigger never uses batch.** Only the per-book (bulk) path is batch-eligible — a single-page trigger always uses the live path, matching how the embedding pipeline's reactive per-chunk dispatch always stays interactive regardless of `embed_batch_enabled` (`docs/main/EMBEDDING_DESIGN.md:13-14`).

## Proposed Changes

### 1. Migration — `packages/backend-core/migrations/090_add_llm_spell_check_status_to_pages.sql` (+ `090_rollback_...sql`)
```sql
ALTER TABLE pages ADD COLUMN llm_spell_check_status VARCHAR(20) NOT NULL DEFAULT 'idle';
ALTER TABLE pages ADD COLUMN llm_spell_check_at TIMESTAMPTZ NULL;
```
Plain string column, no CHECK constraint, no DB-level enum — matches every other status/milestone column on `Page` (e.g. `spell_check_milestone`, `models.py:196-198`), validated only at the application layer. Values reuse the existing generic constants already defined in `packages/backend-core/app/core/pipeline.py` — `PAGE_MILESTONE_IDLE` / `PAGE_MILESTONE_IN_PROGRESS` / `PAGE_MILESTONE_SUCCEEDED` / `PAGE_MILESTONE_FAILED` — no new constants needed. `llm_spell_check_at` records when the last run completed (success or failure), for display in the UI.

### 2. Migration — `packages/backend-core/migrations/091_add_batch_llm_spell_check_jobs.sql` (+ `091_rollback_...sql`)
Tracking table for the batch path, mirroring `batch_history_extraction_jobs`/`batch_ocr_jobs`/`batch_embedding_jobs`:
```sql
CREATE TABLE batch_llm_spell_check_jobs (
    id SERIAL PRIMARY KEY,
    gemini_batch_id VARCHAR(255) NOT NULL UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_ids INTEGER[] NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_batches INTEGER NOT NULL DEFAULT 1,
    model_name VARCHAR(100),
    error TEXT,
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_batch_llm_spell_check_jobs_book_id ON batch_llm_spell_check_jobs(book_id);

INSERT INTO system_configs (key, value, description) VALUES
    ('llm_spell_check_batch_enabled', 'false',
     'When true, the per-book LLM spell-check trigger submits a Gemini Batch API job instead of live concurrent calls');
```
`page_ids` scopes exactly which pages this batch job covers, following the same convention as `batch_ocr_jobs`/`batch_embedding_jobs` (`docs/main/OCR_DESIGN.md:47-55`). `llm_spell_check_batch_enabled` defaults to `false` (opt-in), matching `ocr_batch_enabled`/`embed_batch_enabled`.

### 3. ORM models — `packages/backend-core/app/db/models.py`
Add to `Page`, next to `spell_check_milestone` (L196-198):
```python
llm_spell_check_status: Mapped[str] = mapped_column(
    String(20), default="idle", server_default="idle", nullable=False
)
llm_spell_check_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```
Add a new `BatchLlmSpellCheckJob` model, mirroring `BatchHistoryExtractionJob` (`models.py:370-421`) column-for-column, plus `page_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)`.

### 4. Repository — `packages/backend-core/app/db/repositories/pages_repository.py`
Add `set_llm_spell_check_status`, following the exact shape of `set_is_toc` (L252):
```python
async def set_llm_spell_check_status(
    self, book_id: str, page_number: int, status: str, updated_by: Optional[str] = None
) -> bool:
    values = {"llm_spell_check_status": status, "last_updated": func.now()}
    if status in (PAGE_MILESTONE_SUCCEEDED, PAGE_MILESTONE_FAILED):
        values["llm_spell_check_at"] = func.now()
    if updated_by:
        values["updated_by"] = updated_by
    result = await self.session.execute(
        update(Page).where(Page.book_id == book_id, Page.page_number == page_number).values(**values)
    )
    return result.rowcount > 0
```
`find_one(book_id, page_number)` (L185) is reused as-is to fetch a page plus its prev/next neighbors (`page_number - 1` / `page_number + 1`) for context.

### 5. Service — `packages/backend-core/app/services/llm_spell_check_service.py` (new)
Two exports, shared by both the live and batch paths:
```python
def build_correction_prompt(page_text: str, prev_page_text: Optional[str], next_page_text: Optional[str]) -> str:
    return LLM_SPELL_CHECK_PROMPT.format(
        prev_context=prev_page_text or "", page_text=page_text, next_context=next_page_text or "",
    )

async def correct_page_text(
    page_text: str,
    prev_page_text: Optional[str],
    next_page_text: Optional[str],
    config_repo: SystemConfigsRepository,
) -> str:
    """Live path — one synchronous generate_content call. Used for every per-page
    trigger, and for per-book triggers when llm_spell_check_batch_enabled is false."""
    model = await config_repo.get_value("gemini_llm_spell_check_model", "gemini-3.1-flash-lite")
    prompt = build_correction_prompt(page_text, prev_page_text, next_page_text)
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    corrected = response.text.strip()
    _validate_correction(page_text, corrected)  # raises on suspicious output — see Error Handling
    return corrected
```
- Model id is fetched via `SystemConfigsRepository.get_value` (DB-backed, runtime-overridable), not hardcoded — matching `entity_resolution_service.py:348-350`. The same `gemini_llm_spell_check_model` config key is reused by the batch path (single source of truth for which model runs this feature).
- `prev_page_text`/`next_page_text` are passed as read-only context in the prompt (clearly delimited, e.g. `--- previous page (context only, do not correct) ---`); only `page_text`'s corrected form is returned/used.
- `LLM_SPELL_CHECK_PROMPT` instructs the model to preserve all formatting/line breaks and return the full corrected page text only — no commentary, no JSON wrapper. Written per project prompt conventions (`/prompt-engineer` skill) since this is a new LLM prompt for Uyghur text — must be reviewed against that skill's checklist when implemented.
- `_validate_correction` (empty-output / length-deviation guardrail) is also shared — the batch poller (§8) calls it on each parsed result, same as the live path.

### 6. Worker job — `services/worker/jobs/llm_spell_check_job.py` (new)
Mirrors `spell_check_job.py`'s per-page-session and error-handling shape, but simpler — no scanner-driven claiming, since `page_ids` are passed in explicitly by the triggering endpoint. This is the **live path**: always used for per-page triggers, and used for per-book triggers when `llm_spell_check_batch_enabled` is `false`.
```python
async def llm_spell_check_job(ctx, page_ids: List[int]) -> None:
    semaphore = asyncio.Semaphore(settings.max_parallel_llm_spell_check)

    async def process_page(page_id: int):
        async with semaphore:
            async with db_session.async_session_factory() as session:
                pages_repo = PagesRepository(session)
                page = await session.get(Page, page_id)  # raw id lookup, same as spell_check_job.py:61-65
                prev_page = await pages_repo.find_one(page.book_id, page.page_number - 1)
                next_page = await pages_repo.find_one(page.book_id, page.page_number + 1)
                try:
                    corrected = await correct_page_text(
                        page.text, prev_page.text if prev_page else None,
                        next_page.text if next_page else None,
                        SystemConfigsRepository(session),
                    )
                    page.text = corrected
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_SUCCEEDED
                    )
                    await session.commit()
                except Exception as exc:
                    await pages_repo.set_llm_spell_check_status(
                        page.book_id, page.page_number, PAGE_MILESTONE_FAILED
                    )
                    await session.commit()
                    log_json(logger, logging.WARNING, "llm spell check page failed",
                              book_id=page.book_id, page=page.page_number, error=repr(exc))

    await asyncio.gather(*(process_page(pid) for pid in page_ids))
```
- New setting `max_parallel_llm_spell_check` in `packages/backend-core/app/core/config.py` (per the no-`os.environ.get` rule, read via `settings.*`), bounding concurrent Gemini calls the same way `settings.max_parallel_spell_check` bounds the existing job.
- No `PipelineEvent` rows are written — this isn't a pipeline stage, and nothing downstream listens for its completion.
- No `retry_count` increment on failure — this isn't part of the pipeline's retry/watchdog machinery; a failed page simply sits at `llm_spell_check_status='failed'` until the admin re-triggers it manually.

### 7. Batch submission service — `packages/backend-core/app/services/batch_llm_spell_check_service.py` (new)
Mirrors `batch_history_extraction_service.py:53-178`. `submit_batch_llm_spell_check(book_id: str, page_ids: List[int], session: AsyncSession) -> BatchLlmSpellCheckJob`:
1. For each page id, load the page + prev/next neighbors, build one JSONL line via `build_correction_prompt` (§5): `{"custom_id": str(page_id), "request": {"contents": [...], "generationConfig": {"temperature": 0.0}}}`.
2. Upload the JSONL to GCS (audit copy, `storage.upload_bytes`) and to the Gemini Files API (`client.files.upload`) — same two-write pattern as `batch_history_extraction_service.py:135-145`.
3. `client.batches.create(model=model_name, src=uploaded_file.name)`.
4. Create the `BatchLlmSpellCheckJob` row (`gemini_batch_id`, `book_id`, `page_ids`, `status="submitting"`, `model_name`, `submitted_at`).
5. Bulk-set all `page_ids`' `llm_spell_check_status = 'running'` (same status value the UI already renders for the live path — the admin table icon doesn't need to know which path is running underneath).

### 8. Batch poller scanner — `services/worker/scanners/batch_llm_spell_check_poller_scanner.py` (new)
Mirrors `batch_history_poller_scanner.py` exactly. `run_batch_llm_spell_check_poller_scanner`, registered via `cron(...)` in `worker.py` at the same ~1-minute cadence as the OCR/embedding/history pollers:
1. Skip entirely if `llm_spell_check_batch_enabled` is `false` (same flag-check-first pattern as `batch_history_poller_scanner.py:20-49`).
2. For each `BatchLlmSpellCheckJob` with status in `submitting`/`running`: `client.batches.get(name=job.gemini_batch_id)`, inspect `state`.
3. **On `SUCCEEDED`**: download the output JSONL, and for each line — parse `custom_id` back to a `page_id`, extract the response text, run it through the same `_validate_correction` guardrail the live path uses (§5). Valid → write `pages.text`, `set_llm_spell_check_status(..., PAGE_MILESTONE_SUCCEEDED)`; invalid/errored line → `PAGE_MILESTONE_FAILED`. **Commit per page**, not once at the end (same rationale as `batch_history_extraction_service.py:261-270` — a scanner-tick eviction mid-loop shouldn't roll back already-applied corrections). Update the job row to `status="succeeded"`, `completed_at`, `gcs_output_uri`.
4. **On `FAILED`/`CANCELLED`/`EXPIRED`**: set the job row's `status="failed"`, `error=<state>`, `completed_at`; set every page in `job.page_ids` back to `llm_spell_check_status='failed'` (so the admin sees the failure and can re-trigger, either path).
5. Any exception while polling one job is caught, logged, and does not stop the scanner from processing other jobs in the same tick (matches `batch_history_extraction_service.py:315-323`).
6. No local timeout/max-wait is enforced — relies on Gemini's own terminal batch states, same as the existing batch features. Unlike OCR/embedding, `llm_spell_check` pages don't need a `stale_watchdog_scanner` exemption for long-running batches (`stale_watchdog_scanner.py:35-38`'s exemption is specific to `pipeline_step`-driven timeouts) — `llm_spell_check_status` isn't part of the pipeline's watchdog-tracked milestones at all, so nothing will prematurely time it out regardless of how long the batch takes.

### 9. Worker registration — `services/worker/worker.py`
- Import `llm_spell_check_job`, add to `WorkerSettings.functions` (mirroring `spell_check_job`'s registration at L53/L69). This job is only ever enqueued directly by the trigger endpoints (§10), never picked up by polling.
- Import `run_batch_llm_spell_check_poller_scanner`, register via `cron(...)` alongside the other batch pollers (`cron(run_batch_history_poller_scanner)` at L91).

### 10. Backend endpoints — `services/backend/api/endpoints/books_router.py`
Two new endpoints, both `Depends(require_admin)` (matching the other LLM-driven reprocess actions — `reprocess_graph`, `reprocess_summary` — since each trigger costs real Gemini API calls):

**Per-book**: `POST /{book_id}/reprocess/llm-spell-check`:
1. 404 if book not found.
2. Select all page ids for the book where `llm_spell_check_status != 'running'` (pages already running are skipped, not re-enqueued).
3. Read `llm_spell_check_batch_enabled` via `SystemConfigsRepository`.
   - **If `true`**: call `submit_batch_llm_spell_check(book_id, page_ids, session)` (§7). Return `{"status": "llm_spell_check_batch_submitted", "queued": len(page_ids)}`.
   - **If `false`** (default): bulk-set those pages' `llm_spell_check_status = 'running'`, commit, `redis_pool.enqueue_job("llm_spell_check_job", page_ids=[...], _job_id=f"llm_spell_check:book:{book_id}")` — same direct-enqueue shape as `reprocess_graph` (L2096-2173). Return `{"status": "llm_spell_check_started", "queued": len(page_ids)}`.
4. On enqueue/submit failure (either path): roll the affected pages' status back to `idle`, `raise HTTPException(500, t("errors.llm_spell_check_enqueue_failed"))`.

**Per-page** (always live, batch flag ignored): `POST /{book_id}/pages/{page_num}/llm-spell-check`:
1. 404 if page not found (`pages_repo.find_one`).
2. 409 (`t("errors.llm_spell_check_already_running")`) if `page.llm_spell_check_status == 'running'`.
3. Set status to `running`, commit, enqueue `llm_spell_check_job` with `page_ids=[page.id]`, `_job_id=f"llm_spell_check:page:{page.id}"`.
4. Same enqueue-failure rollback as above.
5. Return `{"status": "llm_spell_check_started"}`.

### 11. Frontend
- **`apps/frontend/src/constants/milestones.ts`**: add `LLM_SPELL_CHECK: 'llm-spell-check'` to `REPROCESS_STEP` (L42-50), following the existing hyphenated-URL-segment convention.
- **`apps/frontend/src/services/persistenceService.ts`**: add `reprocessLlmSpellCheck(bookId)` (`POST .../reprocess/llm-spell-check`, mirroring `reprocessSpellCheck` at L250-259) and `triggerLlmSpellCheckPage(bookId, pageNum)` (`POST .../pages/{pageNum}/llm-spell-check`). The frontend doesn't need to know or care which path (live/batch) served the request — the response shape and subsequent polling are identical either way.
- **`apps/frontend/src/hooks/useBookActions.ts`**:
  - Extend `handleReprocessStep`'s `titles` map (L514-522) and `switch` dispatch (L537-545) with a `LLM_SPELL_CHECK` case calling `PersistenceService.reprocessLlmSpellCheck`.
  - Add `handleLlmSpellCheckPage(bookId, pageNum)`, structurally similar to `handleReProcessPage` (L63-119) — confirm modal, then call — but **must not** blank the page's text or set it to a "pending" empty state the way OCR reset does (L75-103 clears `text: ''`). The page keeps showing its current (pre-correction) text with a spinner/badge indicating the check is in progress, since the existing text is still valid content while the correction runs.
- **`apps/frontend/src/components/admin/ActionMenu.tsx`**: add one more `isAdmin`-gated button (alongside the graph/summary/history buttons) dispatching `handleReprocessStep(book.id, REPROCESS_STEP.LLM_SPELL_CHECK)`, disabled while `reprocessingStep === REPROCESS_STEP.LLM_SPELL_CHECK`, same spinner pattern as the existing buttons.
- **`apps/frontend/src/components/reader/PageItem.tsx` / `ReaderView.tsx`**: add an `onLlmSpellCheck` prop next to `onReprocess`/`onToggleToc`, admin-gated (not merely `isEditor`, for the same cost-control reason as the endpoint auth), wired at both `PageItem` render sites the way `onToggleToc` is (L672, `ReaderView.tsx`).
- **Status display**: extend the page schema/serialization wherever `spellCheckMilestone` is already exposed to also expose `llmSpellCheckStatus`/`llmSpellCheckAt`, so `PageItem` can show a spinner while `running` and the corrected text appears once the existing refresh mechanism re-fetches the book after `running` state is observed. A page corrected via the batch path may stay `running` for much longer than the live path — the UI doesn't distinguish between the two, it just keeps showing the same spinner until the status flips.
- **i18n** (`en.json`/`ug.json`): new keys for the button label, confirm-modal copy, and success/error notifications, under the existing `admin.table.reprocess.*` / `reader.*` / `common.*` namespaces used by the sibling actions.

### 12. Book-level status icon (admin book management table)
The admin book management table (`AdminView.tsx`) already shows one icon per pipeline step (OCR, chunking, embedding, dictionary spell-check, graph) in each book's row, colored by an aggregate computed from page counts — not a single book-level flag. Extend the same mechanism for the LLM pass:

**Backend — `packages/backend-core/app/db/repositories/books_repository.py`**: extend the existing per-step aggregation (`get_with_page_stats` L203-226, `get_batch_stats` L510+) with one more triple, following the exact `func.count(case(...))` shape already used for `spell_check`/`ocr`/`chunking`/`embedding`:
```python
func.count(case((Page.llm_spell_check_status == PAGE_MILESTONE_SUCCEEDED, 1))).label("llm_spell_check"),
func.count(case((Page.llm_spell_check_status.in_(FAILED_PAGE_MILESTONES), 1))).label("llm_spell_check_failed"),
func.count(case((Page.llm_spell_check_status == PAGE_MILESTONE_IN_PROGRESS, 1))).label("llm_spell_check_active"),
```
Exposed under `pipeline_stats.llm_spell_check` as `{done, failed, active}`, same shape as every other step, relative to `total_pages`. This aggregate is agnostic to which path (live/batch) produced the counts.

Important divergence from the other steps: the "book is `ready` → assume 100% and skip scanning pages" shortcut (`get_with_page_stats` L184-226) must **not** apply to `llm_spell_check`. `book.status == 'ready'` only reflects the automatic pipeline; it says nothing about whether the on-demand LLM pass has ever been run. `llm_spell_check` counts are always computed by scanning `pages`, for both ready and in-progress books.

**Frontend — `AdminView.tsx`**: add one more icon to the existing per-book icon row (alongside `BookOpenCheck`/`Network`, near L435-436/509-510) — e.g. `Sparkles` — driven by `pipeline_stats.llm_spell_check` against `total_pages`, with three visual states (not the two-state emerald/gray the other icons use, since this step is triggered per-page and a book can legitimately sit half-checked):
- `done === total_pages && total_pages > 0` → emerald (`text-emerald-500`) — done, hover text `t('common.done')`.
- `done + active > 0` and not fully done → amber (`text-amber-500`) — partial, hover text a new `t('common.partial', { done, total: total_pages })` key (e.g. "N/total pages corrected").
- otherwise → gray (`text-slate-300`) — not started, hover text `t('common.pending')`.

## Error Handling
- **Gemini call failure** (timeout, rate limit, API error): caught in the live job, page's `llm_spell_check_status` set to `failed`, logged via `log_json` (WARNING) with `book_id`/`page`/`error`. No automatic retry — the admin re-triggers manually, same as any other failed on-demand action.
- **Suspicious output guardrail**: before accepting a correction (live or batch), `_validate_correction` rejects (treats as a failure, does not write to `pages.text`) if the model returns an empty string, or if the corrected text's length deviates by more than ~30% from the original page's length. This is a cheap sanity check against catastrophic model failures (e.g. truncated or garbled output) — distinct from, and much lighter than, the dictionary-based per-word validation that was explicitly deferred to Future Enhancements.
- **Enqueue/submit failure**: if `redis_pool.enqueue_job` (live) or the batch submission call (`client.batches.create`/file upload) raises, the endpoint rolls the affected pages' status back to `idle` and returns a 500 — mirroring `reprocess_graph`'s rollback (`books_router.py:2160-2168`).
- **Batch job terminal failure** (`FAILED`/`CANCELLED`/`EXPIRED`): handled entirely by the poller scanner (§8) — job row marked `failed`, all its pages reset to `llm_spell_check_status='failed'`. No local timeout is enforced; the scanner simply waits on Gemini's own terminal states, same as the existing batch features.
- **Concurrent-trigger guard**: a page already `running` is skipped (per-book) or rejected with 409 (per-page) rather than double-enqueued/double-submitted.
- **Auth**: both endpoints require `require_admin` — never skipped, per the project's non-negotiable auth rule.

## Known Limitations
- **No downstream propagation.** If a book has already been chunked/embedded, correcting `pages.text` afterward does not retrigger `chunking_milestone`/`embedding_milestone`. Existing chunks/embeddings keep reflecting the pre-correction text until the admin separately uses the existing "Reprocess Chunking" action. This is intentional for v1 scope, not an oversight — automatically cascading re-chunking is listed under Future Enhancements.
- **No coordination with the dictionary-based spell-check stage.** If both stages run against the same page around the same time, whichever finishes last wins; there's no locking between `spell_check_job` and `llm_spell_check_job` on the same page. Given both are triggered manually/independently and write the same `pages.text` column, this is an accepted, low-probability race for v1.
- **Batch completion time is unpredictable.** Gemini's Batch API carries no fast-turnaround guarantee; a per-book trigger with `llm_spell_check_batch_enabled=true` may sit at `llm_spell_check_status='running'` far longer than the live path would take for the same book. This was an explicit, accepted trade-off for the ~50% API cost discount (see the design-decision framing in `docs/main/OCR_DESIGN.md:16` for the identical trade-off already made for OCR).

## Future Enhancements (explicitly out of scope for v1)
- Validate the model's changed words against the `words` table before applying (rejecting corrections that introduce out-of-dictionary tokens).
- Live agentic tool-calling (ADK `Agent` with a dictionary-lookup tool) if single-shot full-page correction proves insufficient in practice.
- Auto re-trigger chunking/embedding for pages whose text changed.
- Return a discrete edit list (`{original, corrected, reason}`) with a diff/approve-reject UI instead of full-page auto-apply.
- Splitting a single book's batch submission across multiple Gemini Batch files if a very large book ever exceeds a single-file size limit (the `total_batches` column exists for this, but v1's expected page-text volume fits comfortably in one file/one batch).

## Testing
- **Service** (`packages/backend-core/tests/app/services/llm_spell_check_service_test.py`): mocks `genai.Client`; asserts prompt includes prev/next context correctly delimited; asserts `_validate_correction` rejects empty and wildly-different-length outputs; asserts the model id is read from `SystemConfigsRepository`, not hardcoded.
- **Worker job** (`services/worker/tests/jobs/llm_spell_check_job_test.py`): per-page session isolation; status transitions `running` → `succeeded`/`failed`; a failing page doesn't block other pages in the same batch (`asyncio.gather` isolation); concurrency bounded by `settings.max_parallel_llm_spell_check`.
- **Batch submission service** (`packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py`): JSONL lines built with the correct `custom_id`-to-`page_id` mapping and shared prompt; `BatchLlmSpellCheckJob` row created with the right `page_ids`/`status`; pages bulk-set to `running`.
- **Batch poller scanner** (`services/worker/tests/scanners/batch_llm_spell_check_poller_scanner_test.py`): no-op when the flag is off; `SUCCEEDED` state parses each JSONL result, applies `_validate_correction`, commits per page, and updates the job row; `FAILED`/`EXPIRED` resets all of the job's pages to `failed`; one job's exception doesn't stop others in the same tick.
- **Endpoints** (`services/backend/tests/api/endpoints/books_router_test.py` or sibling): per-book trigger branches correctly on `llm_spell_check_batch_enabled` (calls the batch submission vs. the live enqueue); per-page trigger always uses the live path regardless of the flag; per-page trigger 409s when already running; both 403 for a non-admin user; enqueue/submit failure rolls status back to `idle`.
- **Repository stats** (`packages/backend-core/tests/app/db/books_repository_test.py`): `get_with_page_stats`/`get_batch_stats` return correct `llm_spell_check` `{done, failed, active}` counts; a `ready` book with zero/partial `llm_spell_check_status='succeeded'` pages is **not** short-circuited to 100% the way the other steps are.
- **Frontend**: `ActionMenu` new button hidden for non-admin, disabled while running; `useBookActions` new handlers call the right `PersistenceService` methods and don't blank page text; `PageItem` renders the in-progress indicator when `llmSpellCheckStatus === 'running'`; `AdminView` book-row icon renders emerald/amber/gray for done/partial/not-started `pipeline_stats.llm_spell_check`.

## Verification Plan
1. `pytest packages/backend-core/tests/app/services/llm_spell_check_service_test.py packages/backend-core/tests/app/services/batch_llm_spell_check_service_test.py services/worker/tests/jobs/llm_spell_check_job_test.py services/worker/tests/scanners/batch_llm_spell_check_poller_scanner_test.py` and the updated `books_router` endpoint tests.
2. `npm test` inside `apps/frontend/` for the updated `ActionMenu`/`useBookActions`/`PageItem`/`AdminView` tests.
3. Manual (live path, default flag state): rebuild via `./deploy/local/rebuild-and-restart.sh all`, log in as admin, open a book with a known context-dependent spelling error (a valid word substituted for the wrong one), trigger per-page LLM spell check from the reader, confirm the page text updates and `llm_spell_check_status` shows `succeeded`; confirm the book's row in the admin table now shows the new icon amber (partial); trigger per-book on the same multi-page book and confirm all pages process, the button re-enables once complete, and the row's icon turns emerald; confirm both trigger buttons are absent for a non-admin user.
4. Manual (batch path): flip `llm_spell_check_batch_enabled` to `true` via the system-configs admin panel, trigger per-book on a different multi-page book, confirm a `batch_llm_spell_check_jobs` row appears with `status='submitting'`/`'running'`, confirm pages sit at `llm_spell_check_status='running'` until the poller scanner picks up the completed batch (watch worker logs for the ~1-minute poll cadence), and confirm pages flip to `succeeded` with corrected text once the batch completes. Confirm a per-page trigger on the same book still completes quickly (live path) even with the flag on.
