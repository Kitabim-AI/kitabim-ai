# Dictionary Admin Component (`admin/dictionary`)

## Overview
Provides administrative dictionary browsing and management tools across Uyghur definition dictionaries, proverbs, historical terminology, names, and English-Uyghur bilingual dictionaries.

## Interface
- `[DictionaryPanel.tsx:DictionaryPanel]` — Exported `React.FC` rendering Uyghur definition dictionary browser with letter-group filter, search, infinite scroll pagination, and admin deletion.
- `[EnglishUyghurPanel.tsx:EnglishUyghurPanel]` — Exported `React.FC` rendering English-Uyghur bilingual dictionary management table with letter-group filter, search, infinite scroll pagination, and admin deletion.
- `[HistoryDictionaryPanel.tsx:HistoryDictionaryPanel]` — Exported `React.FC` rendering Uyghur historical vocabulary viewer and editor with letter-group filtering, search, infinite scroll pagination, and admin creation/deletion/editing.
- `[NamesDictionaryPanel.tsx:NamesDictionaryPanel]` — Exported `React.FC` rendering Uyghur names dictionary management table with letter-group filter, search, infinite scroll pagination, and admin deletion.
- `[ProverbsPanel.tsx:ProverbsPanel]` — Exported `React.FC` rendering Uyghur proverbs dictionary viewer and editor with letter-group filter, search, infinite scroll pagination, and admin creation/deletion/editing.

## Invariants
- `[DictionaryPanel.tsx:PAGE_SIZE]`, `[EnglishUyghurPanel.tsx:PAGE_SIZE]`, `[NamesDictionaryPanel.tsx:PAGE_SIZE]`, `[ProverbsPanel.tsx:PAGE_SIZE]`, `[HistoryDictionaryPanel.tsx:PAGE_SIZE]` — Paginates entries in batches of `20`, disabling infinite scroll observers when searching or when `!hasMore`.
- `[DictionaryPanel.tsx:isAdmin]`, `[EnglishUyghurPanel.tsx:isAdmin]`, `[NamesDictionaryPanel.tsx:isAdmin]`, `[ProverbsPanel.tsx:isAdmin]`, `[HistoryDictionaryPanel.tsx:isAdmin]` — Administrative actions (deleting and editing dictionary entries) are conditionally displayed and guarded by `useIsAdmin()`.

## Side Effects
- `[DictionaryPanel.tsx:fetchAllEntries]` — Calls `authFetch('/api/dictionary?skip=...&limit=20...')` and `/api/dictionary/stats`.
- `[EnglishUyghurPanel.tsx:fetchEntries]` — Calls `authFetch('/api/english-uyghur-dictionary?skip=...&limit=20...')` and `/api/english-uyghur-dictionary/stats`.
- `[HistoryDictionaryPanel.tsx:fetchEntries]` — Calls `authFetch('/api/history-dictionary?skip=...&limit=20...')` and `/api/history-dictionary/stats`.
- `[NamesDictionaryPanel.tsx:fetchEntries]` — Calls `authFetch('/api/names-dictionary?skip=...&limit=20...')` and `/api/names-dictionary/stats`.
- `[ProverbsPanel.tsx:fetchAllEntries]` — Calls `authFetch('/api/proverbs?skip=...&limit=20...')` and `/api/proverbs/stats`.

## Verification
- Run: `npm test`
