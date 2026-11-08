# Dictionary Admin Component (`admin/dictionary`)

## Overview
Provides administrative dictionary browsing, management, and review tools across Uyghur definition dictionaries, proverbs, historical terminology, names, English-Uyghur bilingual dictionaries, and an AI-generated historical facts staging queue.

## Interface
- `[DictionaryPanel.tsx:DictionaryPanel]` — Exported `React.FC` rendering Uyghur definition dictionary browser with letter-group filter, search, infinite scroll pagination, and admin deletion.
- `[EnglishUyghurPanel.tsx:EnglishUyghurPanel]` — Exported `React.FC` rendering English-Uyghur bilingual dictionary management table with letter-group filter, search, infinite scroll pagination, and admin deletion.
- `[HistoryDictionaryPanel.tsx:HistoryDictionaryPanel]` — Exported `React.FC` rendering Uyghur historical vocabulary viewer and editor with letter-group filtering, search, infinite scroll pagination, and admin creation/deletion/editing.
- `[HistoryStagingQueuePanel.tsx:HistoryStagingQueuePanel]` — Exported `React.FC` providing an administrative review and staging queue interface for AI-generated historical terms and facts, supporting batch and individual approvals, rejections, and conflict resolution.
- `[NamesDictionaryPanel.tsx:NamesDictionaryPanel]` — Exported `React.FC` rendering Uyghur names dictionary management table with letter-group filter, search, infinite scroll pagination, and admin deletion.
- `[ProverbsPanel.tsx:ProverbsPanel]` — Exported `React.FC` rendering Uyghur proverbs dictionary viewer and editor with letter-group filter, search, infinite scroll pagination, and admin creation/deletion/editing.

## Invariants
- `[DictionaryPanel.tsx:PAGE_SIZE]`, `[EnglishUyghurPanel.tsx:PAGE_SIZE]`, `[NamesDictionaryPanel.tsx:PAGE_SIZE]`, `[ProverbsPanel.tsx:PAGE_SIZE]`, `[HistoryDictionaryPanel.tsx:PAGE_SIZE]` — Paginates entries in batches of `20`, disabling infinite scroll observers when searching or when `!hasMore`.
- `[DictionaryPanel.tsx:isAdmin]`, `[EnglishUyghurPanel.tsx:isAdmin]`, `[NamesDictionaryPanel.tsx:isAdmin]`, `[ProverbsPanel.tsx:isAdmin]`, `[HistoryDictionaryPanel.tsx:isAdmin]` — Administrative actions (deleting and editing dictionary entries) are conditionally displayed and guarded by `useIsAdmin()`.
- `[HistoryStagingQueuePanel.tsx:minScore]` — Defaults to `minSignificance: 5` and `pageSize: 50` when querying staging queue items.

## Side Effects
- `[DictionaryPanel.tsx:fetchAllEntries]` — Calls `authFetch('/api/dictionary?skip=...&limit=20...')` and `/api/dictionary/stats`.
- `[EnglishUyghurPanel.tsx:fetchEntries]` — Calls `authFetch('/api/english-uyghur-dictionary?skip=...&limit=20...')` and `/api/english-uyghur-dictionary/stats`.
- `[HistoryDictionaryPanel.tsx:fetchEntries]` — Calls `authFetch('/api/history-dictionary?skip=...&limit=20...')` and `/api/history-dictionary/stats`.
- `[HistoryStagingQueuePanel.tsx:fetchQueue]` — Calls `authFetch('/api/admin/history-dictionary/staging?...')`, `/approve`, `/bulk-approve`, and `DELETE`.
- `[NamesDictionaryPanel.tsx:fetchEntries]` — Calls `authFetch('/api/names-dictionary?skip=...&limit=20...')` and `/api/names-dictionary/stats`.
- `[ProverbsPanel.tsx:fetchAllEntries]` — Calls `authFetch('/api/proverbs?skip=...&limit=20...')` and `/api/proverbs/stats`.

## Verification
- Run: `npm test`
