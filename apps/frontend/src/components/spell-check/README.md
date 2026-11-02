# Spell Check Component (`spell-check`)

## Overview
Provides the full book-level and page-level Uyghur spell-checking interface, error highlighting, candidate suggestion selection, custom replacement forms, and batch review queue workflows for editors.

## Interface
- `[index.ts:ReviewPanel]` — Re-exported batch review panel.
- `[index.ts:SpellCheckPanel]` — Re-exported page-level spell checking sidebar.
- `[index.ts:SpellCheckView]` — Re-exported book-level spell checking workspace.
- `[HighlightedText.tsx:HighlightedText]` — Tokenized text view highlighting orthographic errors, auto-corrections, and pending review marks.
- `[ReviewPanel.tsx:ReviewPanel]` — Editor review drawer displaying batch proposed spelling corrections with approve/reject actions.
- `[SpellCheckPanel.tsx:SpellCheckPanel]` — Sidebar controller presenting page issue lists, suggestion pills, and ignore/accept actions.
- `[SpellCheckView.tsx:SpellCheckView]` — Complete book spell-checking dashboard navigating between pages containing detected spelling errors.

## Invariants
- `[SpellCheckView.tsx:isEditor]` — Editor-level operations (batch review, rule creation, saving corrections) are restricted via `useIsEditor()`.
- `[SpellCheckView.tsx:isFetchingRef]` — Prevents duplicate or concurrent requests during rapid page navigation.

## Side Effects
- `[SpellCheckView.tsx:authFetch]` — Fetches book metadata, page issues, and posts approved or rejected batch corrections to backend `/api/spell-check/...` endpoints.

## Verification
- Run: `npm test`
