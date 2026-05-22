# UI Code Review — 2026-05-21

**Branch:** feature/create-knowledge-graph
**Verdict:** Approve with suggestions

## Issues

---

### `apps/frontend/src/components/admin/AdminView.tsx`

- **[suggestion]** Line ~487 — `hasGraph: stats.has_graph || stats.hasGraph` mixes snake_case and camelCase key lookups on the same object. The `get_book_pipeline_stats` endpoint returns `has_graph` (snake_case), so `stats.hasGraph` will always be `undefined`. The double check is defensive but misleading. Remove `|| stats.hasGraph` and rely only on `stats.has_graph`.

- **[suggestion]** Line ~487 — Same double-check pattern exists for `hasSummary` (`stats.has_summary`) elsewhere in this file. Once the snake_case-only path is confirmed, remove the camelCase guard here too for consistency.

---

### `apps/frontend/src/components/admin/ActionMenu.tsx`

- **[suggestion]** Line 134 — `{t('admin.table.reprocess.graph') || 'قايتا گىراف تۈزۈش'}`. The fallback Uyghur string is hardcoded. The translation key is correctly defined in both locale files so the fallback will never fire in practice. This `|| 'fallback'` pattern is used throughout the existing codebase; note for future cleanup but not a blocking issue here.

---

### `apps/frontend/src/services/persistenceService.ts`

- **[suggestion]** Lines 264–266 — The 403 error message `"Permission denied: Editor access required"` is a hardcoded English string thrown as a JS `Error`. The existing `reprocessSpellCheck`, `reprocessEmbedding`, etc. methods follow the same pattern, so this is consistent. Ideally these would use i18n keys via the caller's `t()` context, but that's a pre-existing pattern issue, not something introduced here.

---

### `packages/shared/src/types.ts`

- **[suggestion]** Line ~42 — `hasGraph?: boolean` is optional (`?`). Given that the API always returns this field (defaulting to `false`), it could be non-optional like `hasSummary?: boolean` is — both are optional in the shared type. This is consistent with `hasSummary` so it's fine as-is.

---

### `apps/frontend/src/tests/components/admin/AdminView.test.tsx`

- **[suggestion]** The `@ts-expect-error` suppressor was removed from the `global.fetch` mock. Good cleanup. ✓

- **[suggestion]** `hasGraph: true` was added to the mock book fixture. ✓ Tests cover the new field.

- **[blocking]** No new test was added for the Graph pipeline step icon rendering or the "Reprocess Knowledge Graph" action menu entry. The existing test suite only checks rendering does not crash. Add at minimum one test that verifies the Graph icon appears in the pipeline step row and one that asserts the reprocess action is dispatched.

---

### `apps/frontend/src/constants/milestones.ts`

- No issues. `PIPELINE_STEP.GRAPH`, `REPROCESS_STEP.GRAPH`, `MILESTONE_FIELD_BY_STEP`, and `ADMIN_PIPELINE_STEPS` are all consistently extended. ✓

---

### `apps/frontend/src/hooks/useBookActions.ts`

- No issues. The new `REPROCESS_STEP.GRAPH` case is handled correctly in the switch statement, and the modal title mapping is complete. ✓

---

### `apps/frontend/src/locales/en.json` and `ug.json`

- All new keys are present in both locale files:
  - `admin.pipeline.graph` ✓
  - `admin.table.reprocess.graph` ✓
  - `modal.reprocessGraph.title` ✓
  - `modal.reprocess.graph.message` ✓
- No issues. ✓

---

## Summary

The frontend changes are clean and well-integrated — the Graph step follows the exact same pattern as the Summary step, locale keys are in both files, and the reprocess action is fully wired. The one blocking issue is a missing test for the new UI behaviour. The main suggestion is removing the `|| stats.hasGraph` camelCase fallback in `AdminView.tsx` since the API returns only snake_case for that response shape.
