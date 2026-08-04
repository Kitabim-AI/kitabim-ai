# UI Code Review — 2026-08-02

**Branch:** claude/graph-rag-gds-branch-wjqwe0
**Verdict:** Request changes

## Issues

### `apps/frontend/src/components/admin/dictionary/HistoryStagingQueuePanel.tsx`

- **[blocking]** Lines 50, 70, 87, 104 — All four API calls target `/api/v1/admin/history-dictionary/staging...`, but the backend router (`services/backend/api/endpoints/admin_history_dictionary_router.py`) is mounted in `services/backend/main.py` at `prefix="/api/admin"` with route paths `/history-dictionary/staging`, `/history-dictionary/staging/{id}/approve`, `/history-dictionary/staging/bulk-approve`, `/history-dictionary/staging/{id}` (DELETE) — i.e. the real paths are `/api/admin/history-dictionary/staging...`, with **no `/v1/` segment**. Every request from this panel will 404. The whole staging queue is non-functional as written. Fix: drop `/v1` from all four URLs (or better, add a shared `API_BASE` constant like `persistenceService.ts` does, instead of hand-rolled path strings). Note there is also an orphaned, never-mounted file `services/backend/app/routes/admin/history_dictionary.py` that *does* use `/api/v1/admin` — don't be misled by it; it isn't wired into `main.py`.
- **[blocking]** Lines 50, 70, 87, 104 — None of the `authFetch` calls use `if (!res.ok) throw new Error(...)`; when `res.ok` is false the code just silently does nothing (no notification, no thrown error). Combined with the path bug above, every action in this panel will fail with zero user-visible feedback — the queue will just look permanently empty, and approve/reject/bulk-approve buttons will appear to succeed doing nothing since failure is indistinguishable from a no-op. Fix: throw on `!res.ok` and surface the error to the admin (e.g. via `addNotification` from `useAppContext`, consistent with `useBookActions.ts`'s error handling pattern) instead of swallowing it in `console.error` only inside the `catch` block.
- **[suggestion]** Line 209 — `className="text-xs text-slate-400 dir-ltr font-mono"` — `dir-ltr` is not a Tailwind utility and is not defined anywhere in `tailwind.config.js`; it has no effect. The Latin-script transliteration text will inherit `dir="rtl"` from the panel's root `<div dir="rtl">` (line 125), which can visually scramble parentheses/punctuation. Use the `dir="ltr"` HTML attribute on the `<span>` instead of a CSS class.
- **[suggestion]** Line 37 (`minScore`) / Line 65 (effect dependency) — `minScore`/`setMinScore` is sent as `minSignificance` in the query and included in the `useEffect` dependency array, but there is no UI control anywhere in the component to change it. It's permanently `5` — dead state. Either add a filter control (slider/select) or remove the unused state and simplify the effect/query.
- **[suggestion]** Lines 44-49 — `page: '1'` and `pageSize: '50'` are hardcoded with no pagination UI. If `total` (shown in the header) exceeds 50, there is no way to review the remaining items. Add pagination controls or a "load more" affordance.
- **[suggestion]** Lines 41-65 — `fetchQueue`'s `useEffect` has no unmount guard (cancelled flag / `AbortController`). If the panel unmounts mid-request (e.g. admin switches tabs quickly), `setLoading`/`setItems`/`setTotal` will still fire on an unmounted component.
- **[suggestion]** Throughout — Colors/surfaces diverge from the sibling admin dictionary panels in the same directory (e.g. `HistoryDictionaryPanel.tsx` uses `glass-panel`, `border-[#0369a1]/10`, `bg-[#0369a1]` for the brand primary). This panel instead uses plain `bg-white`/`border-slate-200` cards and Tailwind `sky-*`/`blue-*`/`purple-*` accents, which don't match the design system's `#0369a1` primary convention used elsewhere in the same feature area. Consider aligning for visual consistency.

### `apps/frontend/src/components/admin/AdminView.tsx`

- **[blocking]** Lines 58, 93/96, 513, 541 — `book.hasHistory || book.has_history` (and `stats.has_history || stats.hasHistory`) will never be true. Traced the data path: `has_history: bool = False` is declared on the Pydantic `Book` schema (`packages/backend-core/app/models/schemas.py:82`) and the repository layer does compute it (`books_repository.py` `get_batch_stats`/`get_with_page_stats`), but **neither backend endpoint the frontend actually calls forwards it**: the books-list endpoint (`services/backend/api/endpoints/books_router.py`, `get_books`) only copies `has_summary`/`has_graph` off `batch_stats` and drops `has_history`; the per-book `GET /{book_id}/pipeline-stats` endpoint (same file, `get_book_pipeline_stats`) returns a dict with `has_summary`/`has_graph`/`total_pages` only — `has_history` is likewise dropped. Net effect: the new "History" pipeline icon added in this file will always render grey/incomplete, even for books that have completed extraction. This is rooted in the backend (out of this diff's file scope) but makes the frontend feature dead-on-arrival — flagging here since it's the visible symptom. Needs a backend fix (thread `has_history` through both response payloads) before this icon is meaningful.
- **[suggestion]** Lines 422-437 vs. 497-504 — The mobile pipeline-icon row (lines 422-437) was not updated to include the new `HISTORY` step, while the desktop version (lines 497-504, `ADMIN_PIPELINE_STEPS[6]`) was. Confirm this omission is intentional (space constraints) rather than an oversight.

### `apps/frontend/src/components/admin/ActionMenu.tsx`

- **[suggestion]** Line 159 — The "Extract Historical Terms" button's `disabled` condition is only `reprocessingStep === REPROCESS_STEP.HISTORY`, unlike the sibling OCR/GRAPH/SUMMARY reprocess buttons which also disable on `book.pipelineStep === null` (i.e. before any processing has started). This lets an admin trigger history extraction on a book that hasn't even completed OCR, which is inconsistent with the other admin-only reprocess actions and likely to hit a backend error with no pre-emptive UI guard.
- **[suggestion]** Line 7 — `import { authFetch } from '../../services/authService';` is unused now that the extract-history action was moved into `bookActions.handleReprocessStep` / `PersistenceService.reprocessHistory`. Dead import left over from the previous inline-`fetch` implementation; remove it.

### `apps/frontend/src/hooks/useBookActions.ts`

- **[suggestion]** Line 479 — `[REPROCESS_STEP.HISTORY]: t('admin.table.extractHistory') || ...` reuses the action-menu label for the confirmation modal's title, whereas every sibling step (`GRAPH`, `SUMMARY`, etc., lines 477-478) uses a dedicated `modal.reprocess<Step>.title` key. This diff itself adds `modal.reprocessHistory.title` to both `en.json`/`ug.json` (see below) but never references it — it's dead. For consistency, change this line to `t('modal.reprocessHistory.title') || ...` and use the key that was actually added.

### `apps/frontend/src/components/admin/AdminTabs.tsx`

- **[suggestion]** Line 66 — `onClick={() => setActiveTab(tab.id as any)}`. `setActiveTab` is typed `(tab: string, updateHistory?: boolean) => void` in `AppContext`, and `tab.id` (a `TabId` string-literal union) is already assignable to `string` without a cast. The `as any` appears to be leftover from when `'history-staging'` was briefly a member of `TabId` in this file (now reverted — the tab was moved to `DictionaryView.tsx` instead). Remove the unnecessary cast.

### `apps/frontend/src/locales/en.json` / `apps/frontend/src/locales/ug.json`

- **[suggestion]** `admin.reprocessHistory.title` (en.json ~L790, ug.json ~L809) — added but unused; see the `useBookActions.ts` finding above. Either wire it up or drop it.
- No missing-key parity issues for this feature: all new `admin.historyStaging*`, `admin.bulkApprove`, `admin.statusPending/Approved/Rejected`, `admin.typeEnrichment/typeNew`, `admin.approve/reject`, `admin.originalDefinition/enrichedDefinition/sources`, `admin.pipeline.history`, `admin.table.extractHistory`, and `modal.reprocess.history.message` keys exist in both files with matching values in each language.

### `apps/frontend/src/components/pages/DictionaryView.tsx`

No issues. `DictionaryView` itself is reachable by any authenticated/unauthenticated end user (it is not in `App.tsx`'s `protectedViews` list), but the new `history-staging` tab is correctly gated both in the tab list construction (`isAdmin ? [...] : []`, line 31) and in the render guard (`activeTab === 'history-staging' && isAdmin`, line 74), and the underlying endpoints are separately enforced server-side via `require_admin`. This view doesn't render individual dictionary entries itself (that's `HistoryDictionaryPanel`, unchanged in this diff), so there's nothing here surfacing `is_ai_generated`/review status incorrectly.

### `apps/frontend/src/services/persistenceService.ts`

No issues. `reprocessHistory` correctly uses `authFetch`, checks `response.ok`, and throws descriptive errors (including a distinct 403 message), matching the pattern of its sibling `reprocess*` methods.

### `apps/frontend/src/constants/milestones.ts`

No issues. `HISTORY` was added consistently to `PIPELINE_STEP`, `MILESTONE_FIELD_BY_STEP`, `ADMIN_PIPELINE_STEPS`, and `REPROCESS_STEP`.

## Summary

The staging-queue panel is currently non-functional end-to-end: its four API calls hit a `/api/v1/...` path the backend never mounts (the real routes are `/api/admin/...`), and because none of the fetches check `res.ok` before proceeding, every failure is silent — admins will see an empty queue with no error indication. Separately, the new "History" pipeline-status icon in `AdminView.tsx` can never turn green because the backend drops `has_history` from both response payloads the frontend consumes, even though the repository layer computes it. These two issues make the feature look complete in code review but non-functional at runtime; both need fixing (one frontend URL fix + error handling, one backend response-shape fix) before merge. The remaining findings are consistency/cleanup suggestions (unused import, unused locale key, dead `minScore` state, no pagination, `dir-ltr` class typo, design-system color drift, an unnecessary `as any` cast) that don't block functionality but are worth addressing.
