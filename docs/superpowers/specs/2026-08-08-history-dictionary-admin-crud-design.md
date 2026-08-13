# Design Document: Admin Add/Edit for History Dictionary

## Overview
Give admins the ability to create and edit `history_dictionary` entries directly from the History Dictionary panel in the frontend, via a modal form, instead of only through the AI extraction → staging → approval pipeline.

## Problem & Motivation
`HistoryDictionaryPanel.tsx` is currently read-only plus admin-only delete. The only way a `history_dictionary` row gets created today is via `POST /books/{book_id}/extract-history` (AI extraction into `history_dictionary_staging`) followed by staging approval. There is no way for an admin to manually add a term the AI pipeline hasn't covered, or to correct a live entry's transliteration/definition without going through staging.

The ORM model (`HistoryDictionary`), and repository methods `create_history_dictionary_entry`, `update_history_dictionary_entry`, `find_matching_history_term`, `get_history_dictionary_by_term` already exist in `dictionary_repository.py` and require no changes — this feature is additive at the router and frontend layers only.

## Proposed Changes

### 1. `services/backend/api/endpoints/history_dictionary_router.py`

Add two new admin-gated endpoints alongside the existing `DELETE /history-dictionary/{entry_id}` (same `require_admin` dependency pattern):

**`POST /history-dictionary`** — create a live entry.
- Request body (new Pydantic model `HistoryEntryCreate`): `term: str` (required, `min_length=1`, stripped), `transliteration: Optional[str]`, `definition: Optional[str]`.
- Server derives `letter_group = term[0].upper()` — the same one-liner already used in `history_extraction_service.py:459`; no shared helper exists today so this stays a local one-liner (introducing a shared `get_letter_group()` utility is out of scope — YAGNI until a third call site needs it).
- Leaves `category`, `significance_score`, `is_ai_generated`, `facts` unset on insert so the `HistoryDictionary` ORM column defaults apply (`"general"`, `5`, `False`, `[]`).
- Dedup: call `find_matching_history_term(term)` (the strict/fuzzy matcher the extraction pipeline already trusts, not the plain exact-match `get_history_dictionary_by_term`) before inserting. If it returns a match, respond **409** with `{"detail": "duplicate_term", "existing_id": <id>, "existing_term": <term>}` instead of letting a DB `IntegrityError` surface from the unique constraint on `term`.
- On success: `create_history_dictionary_entry(term=..., transliteration=..., definition=..., letter_group=...)`, `session.commit()`, return `HistoryEntryOut` with `201`.

**`PATCH /history-dictionary/{entry_id}`** — edit an existing entry.
- Request body (new Pydantic model `HistoryEntryUpdate`): `transliteration: Optional[str]`, `definition: Optional[str]`. `term` is intentionally not accepted — it's the key used for RAG lookups (`lookup_history_term`) and staging dedup (`find_matching_history_term`), and changing it post-creation risks silently breaking those; an admin who needs a different term deletes and recreates instead.
- 404 (`HTTPException`) if `get_history_dictionary_by_id` finds nothing.
- Calls `update_history_dictionary_entry(entry, **{k: v for k, v in body if v is not None})`, `session.commit()`, returns updated `HistoryEntryOut`.

Both endpoints use `current_admin: User = Depends(require_admin)`, matching the existing `DELETE` route.

### 2. `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`

Bring this panel up to the same create/edit modal pattern already proven in `apps/frontend/src/components/admin/rules/AutoCorrectRulesPanel.tsx`:

- **"+ Add" button**, admin-only (`isAdmin &&`), placed next to the search bar — opens the modal in create mode with empty fields.
- **Edit button**, admin-only, added next to the existing `Trash2` delete button on each entry row — opens the modal pre-filled from that entry (create/edit mode tracked via `editingEntry: HistoryEntry | null`, same convention as `AutoCorrectRulesPanel`'s `editingRule`).
- **Modal**: new `createPortal`-based form matching the existing modal chrome (overlay, card, header with icon + title, footer with Cancel/Save) already used in `AutoCorrectRulesPanel.tsx`.
  - Fields: `term` (RTL Uyghur text input, required, `autoFocus`, **disabled when `editingEntry` is set** — same disabled-on-edit treatment used for the locked key field in `AutoCorrectRulesPanel`), `transliteration` (optional, LTR text input), `definition` (optional, RTL textarea).
  - `handleSubmit` branches `POST /api/history-dictionary` (create) vs `PATCH /api/history-dictionary/{id}` (edit) based on `editingEntry`, mirroring `AutoCorrectRulesPanel.handleSubmit`.
  - On `409` from the create call: show the duplicate-term error inline in the modal (not a toast) — it's an expected, actionable case, not a failure.
  - On success: close the modal and refresh the current view — `fetchStats()` plus either `fetchEntries(0, true, activeGroup)` (browse mode) or `searchEntries(searchQuery)` (search mode is active), so the new/edited row appears without a full reload.
- No changes to the existing delete flow.

### 3. i18n — `apps/frontend/src/locales/en.json` and `ug.json`

Add new keys under the existing `admin.historyDictionary` namespace (same structure as the sibling `namesDictionary`/`englishUyghurDictionary`/`proverbs` blocks): `addEntry`, `editEntry`, `term`, `createSuccess`, `createError`, `updateSuccess`, `updateError`, `duplicateTerm`. (`transliteration` and `definition`-adjacent labels already partially exist — reuse `transliteration` key already present at line 628 of `en.json`.)

### 4. Tests

- Backend: extend `services/backend/tests/api/endpoints/` (wherever `history_dictionary_router` is currently tested, or add a new test file if none exists) to cover: successful create, duplicate-term 409, create/patch require admin (403 for non-admin), patch 404 for missing id, patch ignores/rejects a `term` field in the body.
- Repository layer needs no new tests — `create_history_dictionary_entry`/`update_history_dictionary_entry`/`find_matching_history_term` are pre-existing and already covered.
- Frontend: extend or add a test for `HistoryDictionaryPanel.tsx` covering: Add button hidden for non-admin, modal opens/submits POST, edit modal pre-fills and submits PATCH with `term` excluded, duplicate-term 409 renders inline error.

## Verification Plan
1. Backend: `pytest packages/backend-core/tests/app/services/` and the new/updated router test file.
2. Frontend: `npm test` inside `apps/frontend/` for the updated `HistoryDictionaryPanel` test.
3. Manual: rebuild backend + frontend via `./deploy/local/rebuild-and-restart.sh all`, log in as an admin user, open the History Dictionary tab, add a new term, confirm it appears in the list and via `/api/history-dictionary/search`; edit its definition; attempt to add a duplicate term and confirm the inline 409 error; confirm the Add/Edit buttons are absent for a non-admin user.
