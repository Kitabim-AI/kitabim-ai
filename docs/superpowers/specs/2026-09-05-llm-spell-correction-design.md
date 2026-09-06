# Design Document: LLM-Based Spell Correction (Gemini)

## Overview
Add an on-demand, admin-triggered spell-correction pass powered by Gemini, runnable per-page or per-book from the existing book-management UI. It runs independently of, and in addition to, the existing dictionary-based spell-check pipeline (`spell_check_scanner`/`spell_check_job`/`auto_correct_service`), and auto-applies its corrections directly to `pages.text`.

## Problem & Motivation
The existing spell-check pipeline (`packages/backend-core/app/services/spell_check_service.py`) tokenizes page text, generates OCR-confusion/vowel-insertion variants, and flags any token not found in the `words` table (`find_unknown_words`, `spell_check_service.py:256`). This only catches **unknown-word errors** — a token that isn't a real word at all.

It structurally cannot catch **context-dependent real-word errors**: an OCR or typing mistake that happens to produce a different, valid dictionary word (e.g. one Uyghur word substituted for another that looks similar but changes the sentence's meaning). Detecting this requires reading the surrounding sentence and judging whether the word fits semantically — exactly the kind of judgment a dictionary lookup cannot make, but an LLM can.

## Non-Goals (v1)
- **Not replacing** `spell_check_scanner`/`spell_check_job`/`auto_correct_service`. Both stages keep running; this is additive, not a migration off the existing pipeline.
- **Not a pipeline stage.** It does not gate `chunking_milestone`, `pipeline_step`, or any other pipeline field — it is a manual, admin-invoked action, not part of automatic book processing.
- **No live agentic tool-calling.** Per project convention (single-shot structured LLM calls use raw `generate_content`, not an ADK `Agent`/`Runner`), this is one Gemini call per page with the full page text as input — no dictionary-lookup tool invoked mid-reasoning.
- **No dictionary-based validation of the model's output.** Changed words are not checked against the `words` table before being applied. Deferred to Future Enhancements.
- **No review/approve UI.** Corrections write directly to `pages.text`; there's no diff/approve-reject screen like the existing `SpellCheckPanel`/`ReviewPanel`.
- **Does not re-trigger chunking/embedding.** See Known Limitations.

## Proposed Changes

### 1. Migration — `packages/backend-core/migrations/090_add_llm_spell_check_status_to_pages.sql` (+ `090_rollback_...sql`)
```sql
ALTER TABLE pages ADD COLUMN llm_spell_check_status VARCHAR(20) NOT NULL DEFAULT 'idle';
ALTER TABLE pages ADD COLUMN llm_spell_check_at TIMESTAMPTZ NULL;
```
Plain string column, no CHECK constraint, no DB-level enum — matches every other status/milestone column on `Page` (e.g. `spell_check_milestone`, `models.py:196-198`), validated only at the application layer. Values reuse the existing generic constants already defined in `packages/backend-core/app/core/pipeline.py` — `PAGE_MILESTONE_IDLE` / `PAGE_MILESTONE_IN_PROGRESS` / `PAGE_MILESTONE_SUCCEEDED` / `PAGE_MILESTONE_FAILED` — no new constants needed. `llm_spell_check_at` records when the last run completed (success or failure), for display in the UI.

### 2. ORM model — `packages/backend-core/app/db/models.py`
Add to `Page`, next to `spell_check_milestone` (L196-198):
```python
llm_spell_check_status: Mapped[str] = mapped_column(
    String(20), default="idle", server_default="idle", nullable=False
)
llm_spell_check_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

### 3. Repository — `packages/backend-core/app/db/repositories/pages_repository.py`
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

### 4. Service — `packages/backend-core/app/services/llm_spell_check_service.py` (new)
Single function, following the raw-`generate_content` convention (`entity_resolution_service.py:336-380`, `app/services/rag/judge.py`):
```python
async def correct_page_text(
    page_text: str,
    prev_page_text: Optional[str],
    next_page_text: Optional[str],
    config_repo: SystemConfigsRepository,
) -> str:
    model = await config_repo.get_value("gemini_llm_spell_check_model", "gemini-3.1-flash-lite")
    prompt = LLM_SPELL_CHECK_PROMPT.format(
        prev_context=prev_page_text or "", page_text=page_text, next_context=next_page_text or "",
    )
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=model, contents=prompt,
        config=types.GenerateContentConfig(temperature=0.0),
    )
    corrected = response.text.strip()
    _validate_correction(page_text, corrected)  # raises on suspicious output — see Error Handling
    return corrected
```
- Model id is fetched via `SystemConfigsRepository.get_value` (DB-backed, runtime-overridable), not hardcoded — matching `entity_resolution_service.py:348-350`.
- `prev_page_text`/`next_page_text` are passed as read-only context in the prompt (clearly delimited, e.g. `--- previous page (context only, do not correct) ---`); only `page_text`'s corrected form is returned/used.
- The prompt (`LLM_SPELL_CHECK_PROMPT`, defined in the same module or a sibling `prompts.py`) instructs the model to preserve all formatting/line breaks and to return the full corrected page text only — no commentary, no JSON wrapper (a plain corrected-text response, not a structured schema, since the user chose "full rewritten page text" as the output format).
- Written per project prompt conventions (`/prompt-engineer` skill) since this is a new LLM prompt for Uyghur text — must be reviewed against that skill's checklist when implemented.

### 5. Worker job — `services/worker/jobs/llm_spell_check_job.py` (new)
Mirrors `spell_check_job.py`'s per-page-session and error-handling shape, but simpler — no scanner-driven claiming, since `page_ids` are passed in explicitly by the triggering endpoint:
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

### 6. Worker registration — `services/worker/worker.py`
Import `llm_spell_check_job` and add it to the `WorkerSettings.functions` list (mirroring `spell_check_job`'s registration at L53/L69). **No scanner and no cron entry** — this job is only ever enqueued directly by the trigger endpoints below, never picked up by polling.

### 7. Backend endpoints — `services/backend/api/endpoints/books_router.py`
Two new endpoints, both `Depends(require_admin)` (matching the other LLM-driven reprocess actions — `reprocess_graph`, `reprocess_summary` — since each trigger costs real Gemini API calls):

**Per-book**: `POST /{book_id}/reprocess/llm-spell-check`, mirroring `reprocess_graph`'s direct-enqueue shape (L2096-2173):
1. 404 if book not found.
2. Select all page ids for the book where `llm_spell_check_status != 'running'` (pages already running are skipped, not re-enqueued).
3. Bulk-set those pages' `llm_spell_check_status = 'running'`, commit.
4. `redis_pool.enqueue_job("llm_spell_check_job", page_ids=[...], _job_id=f"llm_spell_check:book:{book_id}")`.
5. On enqueue failure: roll the skipped pages' status back to `idle`, `raise HTTPException(500, t("errors.llm_spell_check_enqueue_failed"))`.
6. Return `{"status": "llm_spell_check_started", "queued": len(page_ids)}` — same `queued`-count shape the frontend's `handleTriggerSpellCheck` already expects (`useBookActions.ts:161-184`).

**Per-page**: `POST /{book_id}/pages/{page_num}/llm-spell-check`:
1. 404 if page not found (`pages_repo.find_one`).
2. 409 (`t("errors.llm_spell_check_already_running")`) if `page.llm_spell_check_status == 'running'`.
3. Set status to `running`, commit, enqueue with `_job_id=f"llm_spell_check:page:{page.id}"`.
4. Same enqueue-failure rollback as above.
5. Return `{"status": "llm_spell_check_started"}`.

### 8. Frontend
- **`apps/frontend/src/constants/milestones.ts`**: add `LLM_SPELL_CHECK: 'llm-spell-check'` to `REPROCESS_STEP` (L42-50), following the existing hyphenated-URL-segment convention.
- **`apps/frontend/src/services/persistenceService.ts`**: add `reprocessLlmSpellCheck(bookId)` (`POST .../reprocess/llm-spell-check`, mirroring `reprocessSpellCheck` at L250-259) and `triggerLlmSpellCheckPage(bookId, pageNum)` (`POST .../pages/{pageNum}/llm-spell-check`).
- **`apps/frontend/src/hooks/useBookActions.ts`**:
  - Extend `handleReprocessStep`'s `titles` map (L514-522) and `switch` dispatch (L537-545) with a `LLM_SPELL_CHECK` case calling `PersistenceService.reprocessLlmSpellCheck`.
  - Add `handleLlmSpellCheckPage(bookId, pageNum)`, structurally similar to `handleReProcessPage` (L63-119) — confirm modal, then call — but **must not** blank the page's text or set it to a "pending" empty state the way OCR reset does (L75-103 clears `text: ''`). The page keeps showing its current (pre-correction) text with a spinner/badge indicating the check is in progress, since the existing text is still valid content while the correction runs.
- **`apps/frontend/src/components/admin/ActionMenu.tsx`**: add one more `isAdmin`-gated button (alongside the graph/summary/history buttons) dispatching `handleReprocessStep(book.id, REPROCESS_STEP.LLM_SPELL_CHECK)`, disabled while `reprocessingStep === REPROCESS_STEP.LLM_SPELL_CHECK`, same spinner pattern as the existing buttons.
- **`apps/frontend/src/components/reader/PageItem.tsx` / `ReaderView.tsx`**: add an `onLlmSpellCheck` prop next to `onReprocess`/`onToggleToc`, admin-gated (not merely `isEditor`, for the same cost-control reason as the endpoint auth), wired at both `PageItem` render sites the way `onToggleToc` is (L672, `ReaderView.tsx`).
- **Status display**: extend the page schema/serialization wherever `spellCheckMilestone` is already exposed to also expose `llmSpellCheckStatus`/`llmSpellCheckAt`, so `PageItem` can show a spinner while `running` and the corrected text appears once the existing refresh mechanism re-fetches the book after `running` state is observed.
- **i18n** (`en.json`/`ug.json`): new keys for the button label, confirm-modal copy, and success/error notifications, under the existing `admin.table.reprocess.*` / `reader.*` / `common.*` namespaces used by the sibling actions.

### 9. Book-level status icon (admin book management table)
The admin book management table (`AdminView.tsx`) already shows one icon per pipeline step (OCR, chunking, embedding, dictionary spell-check, graph) in each book's row, colored by an aggregate computed from page counts — not a single book-level flag. Extend the same mechanism for the LLM pass:

**Backend — `packages/backend-core/app/db/repositories/books_repository.py`**: extend the existing per-step aggregation (`get_with_page_stats` L203-226, `get_batch_stats` L510+) with one more triple, following the exact `func.count(case(...))` shape already used for `spell_check`/`ocr`/`chunking`/`embedding`:
```python
func.count(case((Page.llm_spell_check_status == PAGE_MILESTONE_SUCCEEDED, 1))).label("llm_spell_check"),
func.count(case((Page.llm_spell_check_status.in_(FAILED_PAGE_MILESTONES), 1))).label("llm_spell_check_failed"),
func.count(case((Page.llm_spell_check_status == PAGE_MILESTONE_IN_PROGRESS, 1))).label("llm_spell_check_active"),
```
Exposed under `pipeline_stats.llm_spell_check` as `{done, failed, active}`, same shape as every other step, relative to `total_pages`.

Important divergence from the other steps: the "book is `ready` → assume 100% and skip scanning pages" shortcut (`get_with_page_stats` L184-226) must **not** apply to `llm_spell_check`. `book.status == 'ready'` only reflects the automatic pipeline; it says nothing about whether the on-demand LLM pass has ever been run. `llm_spell_check` counts are always computed by scanning `pages`, for both ready and in-progress books.

**Frontend — `AdminView.tsx`**: add one more icon to the existing per-book icon row (alongside `BookOpenCheck`/`Network`, near L435-436/509-510) — e.g. `Sparkles` — driven by `pipeline_stats.llm_spell_check` against `total_pages`, with three visual states (not the two-state emerald/gray the other icons use, since this step is triggered per-page and a book can legitimately sit half-checked):
- `done === total_pages && total_pages > 0` → emerald (`text-emerald-500`) — done, hover text `t('common.done')`.
- `done + active > 0` and not fully done → amber (`text-amber-500`) — partial, hover text a new `t('common.partial', { done, total: total_pages })` key (e.g. "N/total pages corrected").
- otherwise → gray (`text-slate-300`) — not started, hover text `t('common.pending')`.

## Error Handling
- **Gemini call failure** (timeout, rate limit, API error): caught in the job, page's `llm_spell_check_status` set to `failed`, logged via `log_json` (WARNING) with `book_id`/`page`/`error`. No automatic retry — the admin re-triggers manually, same as any other failed on-demand action.
- **Suspicious output guardrail**: before accepting a correction, `_validate_correction` rejects (treats as a failure, does not write to `pages.text`) if the model returns an empty string, or if the corrected text's length deviates by more than ~30% from the original page's length. This is a cheap sanity check against catastrophic model failures (e.g. truncated or garbled output) — distinct from, and much lighter than, the dictionary-based per-word validation that was explicitly deferred to Future Enhancements.
- **Enqueue failure**: if `redis_pool.enqueue_job` raises, the endpoint rolls the affected pages' status back to `idle` and returns a 500 — mirroring `reprocess_graph`'s rollback (`books_router.py:2160-2168`).
- **Concurrent-trigger guard**: a page already `running` is skipped (per-book) or rejected with 409 (per-page) rather than double-enqueued.
- **Auth**: both endpoints require `require_admin` — never skipped, per the project's non-negotiable auth rule.

## Known Limitations
- **No downstream propagation.** If a book has already been chunked/embedded, correcting `pages.text` afterward does not retrigger `chunking_milestone`/`embedding_milestone`. Existing chunks/embeddings keep reflecting the pre-correction text until the admin separately uses the existing "Reprocess Chunking" action. This is intentional for v1 scope, not an oversight — automatically cascading re-chunking is listed under Future Enhancements.
- **No coordination with the dictionary-based spell-check stage.** If both stages run against the same page around the same time, whichever finishes last wins; there's no locking between `spell_check_job` and `llm_spell_check_job` on the same page. Given both are triggered manually/independently and write the same `pages.text` column, this is an accepted, low-probability race for v1.

## Future Enhancements (explicitly out of scope for v1)
- Validate the model's changed words against the `words` table before applying (rejecting corrections that introduce out-of-dictionary tokens).
- Live agentic tool-calling (ADK `Agent` with a dictionary-lookup tool) if single-shot full-page correction proves insufficient in practice.
- Auto re-trigger chunking/embedding for pages whose text changed.
- Return a discrete edit list (`{original, corrected, reason}`) with a diff/approve-reject UI instead of full-page auto-apply.
- A feature-flag / system-config gate (like `kg_enabled` for knowledge-graph reprocessing) if usage needs throttling or a kill switch.

## Testing
- **Service** (`packages/backend-core/tests/app/services/llm_spell_check_service_test.py`): mocks `genai.Client`; asserts prompt includes prev/next context correctly delimited; asserts `_validate_correction` rejects empty and wildly-different-length outputs; asserts the model id is read from `SystemConfigsRepository`, not hardcoded.
- **Worker job** (`services/worker/tests/jobs/llm_spell_check_job_test.py`): per-page session isolation; status transitions `running` → `succeeded`/`failed`; a failing page doesn't block other pages in the same batch (`asyncio.gather` isolation); concurrency bounded by `settings.max_parallel_llm_spell_check`.
- **Endpoints** (`services/backend/tests/api/endpoints/books_router_test.py` or sibling): per-book trigger enqueues with the correct skipped/queued page set; per-page trigger 409s when already running; both 403 for a non-admin user; enqueue failure rolls status back to `idle`.
- **Repository stats** (`packages/backend-core/tests/app/db/books_repository_test.py`): `get_with_page_stats`/`get_batch_stats` return correct `llm_spell_check` `{done, failed, active}` counts; a `ready` book with zero/partial `llm_spell_check_status='succeeded'` pages is **not** short-circuited to 100% the way the other steps are.
- **Frontend**: `ActionMenu` new button hidden for non-admin, disabled while running; `useBookActions` new handlers call the right `PersistenceService` methods and don't blank page text; `PageItem` renders the in-progress indicator when `llmSpellCheckStatus === 'running'`; `AdminView` book-row icon renders emerald/amber/gray for done/partial/not-started `pipeline_stats.llm_spell_check`.

## Verification Plan
1. `pytest packages/backend-core/tests/app/services/llm_spell_check_service_test.py services/worker/tests/jobs/llm_spell_check_job_test.py` and the updated `books_router` endpoint tests.
2. `npm test` inside `apps/frontend/` for the updated `ActionMenu`/`useBookActions`/`PageItem`/`AdminView` tests.
3. Manual: rebuild via `./deploy/local/rebuild-and-restart.sh all`, log in as admin, open a book with a known context-dependent spelling error (a valid word substituted for the wrong one), trigger per-page LLM spell check from the reader, confirm the page text updates and `llm_spell_check_status` shows `succeeded`; confirm the book's row in the admin table now shows the new icon amber (partial) since only one page is done; trigger per-book from the book management menu on the same multi-page book and confirm all pages process, the button re-enables once complete, and the row's icon turns emerald; confirm both trigger buttons are absent for a non-admin user.
