# Synonyms Admin Component (`admin/synonyms`)

## Overview
Provides the Uyghur synonym dictionary browsing and management panel, supporting keyword search, Uyghur alphabet letter-group filtering, infinite scrolling, and administrator entry deletion.

## Interface
- `[SynonymsPanel.tsx:SynonymsPanel]` — Exported React functional component (`React.FC`) rendering the Uyghur synonym dictionary browsing, search, letter-group filtering, infinite scrolling, and admin deletion UI.

## Invariants
- `[SynonymsPanel.tsx:PAGE_SIZE]` — Pagination batch size is fixed at `20` (`limit=20` for `/api/synonyms` and `/api/synonyms/search`); `hasMore` is true only when `data.length === PAGE_SIZE` (`[SynonymsPanel.tsx:fetchAllEntries]`).
- `[SynonymsPanel.tsx:SynonymsPanel]` — Delete button is only rendered when `isAdmin` (`useIsAdmin()`) is truthy (`[SynonymsPanel.tsx:handleDeleteEntry]`).
- `[SynonymsPanel.tsx:SynonymsPanel]` — Infinite scroll observer (`IntersectionObserver`) is disabled when `!hasMore`, `isLoadingMore`, or `searchQuery.trim()` is non-empty; letter-group filter pills are hidden when `searchQuery.trim()` is non-empty.

## Side Effects
- `[SynonymsPanel.tsx:fetchStats]` — Calls `authFetch('/api/synonyms/stats?...')` with optional `letter_group` query parameter.
- `[SynonymsPanel.tsx:fetchAllEntries]` — Calls `authFetch('/api/synonyms?skip=...&limit=20...')` with optional `letter_group` query parameter.
- `[SynonymsPanel.tsx:searchEntries]` — Calls `authFetch('/api/synonyms/search?q=...&limit=20')` with 300ms debounce and `AbortController` cancellation (`[SynonymsPanel.tsx:activeSearchRef]`).
- `[SynonymsPanel.tsx:handleDeleteEntry]` — Opens confirmation modal via `setModal`, calls `authFetch('/api/synonyms/${entry.id}', { method: 'DELETE' })`, refreshes stats, and dispatches toast notifications via `addNotification`.
- `[SynonymsPanel.tsx:SynonymsPanel]` — Focuses search input after 50ms timeout on mount (`[SynonymsPanel.tsx:inputRef]`) and registers an `IntersectionObserver` on `loaderRef` for infinite scrolling.

## Verification
- Run: `npm test`
