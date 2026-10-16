# Per-Page LLM Spell Check in Edit Mode — Design

**Date:** 2026-10-15
**Branch:** feature/llm-spell-correction-v2
**Status:** Approved in brainstorming, pending spec review

## Problem

The per-page LLM spell check (Sparkles button in reader view mode) enqueues
`llm_spell_check_job`, which overwrites `page.text` directly. The editor never
sees what changed and has no chance to reject a bad correction.

## Goal

Per-page LLM spell check runs only inside page edit mode. The corrected text is
loaded into the editor's textarea with the changed words highlighted. Nothing
is persisted until the editor clicks Save; Cancel discards everything.

## Scope

**In scope**
- New synchronous, non-persisting preview endpoint.
- Edit-mode "AI check" button, diff highlighting, change count.
- Saving after an AI check marks the page as LLM-checked.
- Removing the old per-page enqueue endpoint and the view-mode Sparkles button.

**Out of scope (unchanged)**
- Book-level LLM spell check (`POST /books/{id}/reprocess/llm-spell-check`,
  live and Gemini Batch paths) keeps auto-applying corrections.
- `llm_spell_check_job` and the batch poller stay — the book-level live path
  still uses the job.
- The prompt (`LLM_SPELL_CHECK_PROMPT`) and its correction scope (real-word
  substitutions only).
- Per-word accept/revert — the editor accepts or rejects the page as a whole,
  and can still hand-edit any word in the textarea.

## Design

### Backend

**New endpoint:** `POST /api/books/{book_id}/pages/{page_num}/llm-spell-check/preview`

- Auth: `require_editor` — the same dependency as `POST .../update`, since the
  button lives in edit mode. Note: this widens Gemini-call access from admins
  (old per-page trigger used `require_admin`) to editors.
- Request body: `{ "text": str }` — the textarea's current content, so unsaved
  manual edits are included in what the LLM corrects.
- Loads the previous and next pages' text from the DB as context (same as the
  worker job does today).
- Calls the existing `llm_spell_check_service.correct_page_text(...)` with
  `SystemConfigsRepository` for model selection. It already normalizes
  markdown and Uyghur characters and runs `_validate_correction`.
- Response: `{ "corrected_text": str }`.
- **Writes nothing** — no page text, no `llm_spell_check_status`, no
  `prev_text`, no spell-issue invalidation.
- Errors:
  - 404 `errors.page_not_found` if the page doesn't exist.
  - 400 with a new i18n key if `text` is empty or whitespace.
  - 422 with a new i18n key when `_validate_correction` raises `ValueError`
    (empty output or >30% length deviation).
  - 502 with a new i18n key when the LLM call itself fails (circuit breaker
    open, rate limit, upstream error).
  - All failures are logged via `log_json`.

**Removed:** `POST /api/books/{book_id}/pages/{page_num}/llm-spell-check`
(`trigger_llm_spell_check_page`) and its tests. Remove any i18n keys used only
by it (e.g. `errors.llm_spell_check_already_running`, if unused elsewhere).

**Save path change:** `POST .../update` accepts an optional
`llm_spell_checked: bool` in its payload. When true, it sets
`page.llm_spell_check_status = succeeded` and `page.llm_spell_check_at = now`,
so a later non-forced book-level run skips this manually reviewed page. All
existing save behavior (normalization, spell-issue invalidation, re-chunking)
is unchanged.

### Frontend

**PageItem view mode:** remove the Sparkles button and the `onLlmSpellCheck`
prop chain (`PageItem` → `VirtualScrollReader` → `ReaderView` →
`bookActions.handleLlmSpellCheckPage`).

**PageItem edit mode:**
- Add an "AI check" button beside Save/Cancel. While the request is in flight,
  it shows a spinner, and the textarea, Save, and AI check are disabled
  (Cancel stays enabled and aborts the in-flight request).
- On success:
  1. Snapshot the pre-check text as `baselineText`.
  2. Replace `tempText` with `corrected_text`.
  3. Show a summary: "N words changed", or "No changes" when the text is
     identical.
- On error: show the translated error message; `tempText` is untouched.
- Running AI check a second time replaces the snapshot with the then-current
  text.

**Highlighting:**
- A new pure helper `diffChangedWordRanges(baseline, current)` does a
  word-level diff (LCS over whitespace-separated tokens) and returns character
  ranges in `current` of inserted or changed words.
- Ranges are rendered in a highlight layer positioned behind the transparent-
  background textarea, following the existing `HighlightedText` `isLayer`
  pattern in `components/spell-check/`. The layer must match the textarea's
  font, size, padding, line height, direction (`rtl`), and scroll position.
- Highlights recompute on every edit (memoized on `baselineText` and
  `tempText`), so they always mean "differs from the text before the AI
  check". Words the editor types after the check are therefore highlighted
  too. This is intentional — it is the simplest rule that never highlights
  the wrong word.
- No highlights are shown until an AI check has run in the current edit
  session. Save and Cancel both clear `baselineText`.

**Save:** sends `llm_spell_checked: true` in the payload if an AI check ran in
this edit session (whether or not the editor changed anything afterwards).

## Data Flow

```
Editor clicks "AI check"
  → POST .../llm-spell-check/preview { text: tempText }
  → backend: load prev/next page text → correct_page_text() → validate
  → { corrected_text }
  → frontend: baselineText = tempText; tempText = corrected_text
  → highlight layer renders diffChangedWordRanges(baselineText, tempText)
Editor clicks Save  → POST .../update { text, llm_spell_checked: true }
Editor clicks Cancel → discard tempText and baselineText; nothing was persisted
```

## Testing

**Backend (`/api-unit-tester`)**
- Preview returns corrected text and performs no DB writes (page row,
  `PageSpellIssue`, and status unchanged).
- Prev/next page context is passed to `correct_page_text`.
- 404 missing page; 400 empty text; 422 on validation failure; 502 on LLM
  failure.
- Unauthenticated → 401; non-editor → 403.
- `update` with `llm_spell_checked: true` sets status and timestamp; without
  it, both stay unchanged.
- Old per-page enqueue endpoint tests are removed.

**Frontend (`/ui-unit-tester`)**
- `diffChangedWordRanges`: identical text → no ranges; single-word
  substitution; multiple changes; inserted words; RTL Uyghur text; changes
  next to line breaks and punctuation.
- PageItem: the AI check button only appears in edit mode; success replaces
  textarea text and shows the count; error leaves text untouched; Cancel
  restores the original; Save sends `llm_spell_checked`.
- The view-mode Sparkles button no longer renders.

## Docs to update

- `docs/main/SPELLCHECK_DESIGN.md` — the per-page flow is now review-in-edit-
  mode, and book-level stays auto-apply.
- API reference / `openapi.json` (run `scripts/check_openapi.py`).
