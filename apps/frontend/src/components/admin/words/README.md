# Words Admin Component (`admin/words`)

## Overview
Provides the spell-check dictionary words viewer and management panel with keyword search, Uyghur alphabet letter-group filtering, infinite scroll pagination, and admin-only word deletion.

## Interface
- `[WordsPanel.tsx:WordsPanel]` — Exported `React.FC` component providing a spell-check words viewer with search, Uyghur alphabet letter-group filtering, infinite scroll pagination, and admin-only word deletion.

## Invariants
- `[WordsPanel.tsx:PAGE_SIZE]` — Paginates word list fetches in increments of `20` (`skip: String(pageNum * PAGE_SIZE), limit: String(PAGE_SIZE)`), setting `hasMore` to `data.length === PAGE_SIZE`.
- `[WordsPanel.tsx:searchWords]` — Search requests are debounced by 300ms (`useEffect` on `searchQuery`), trim whitespace, limit results to `limit=10`, and abort any previous in-flight `AbortController` (`activeSearchRef`).
- `[WordsPanel.tsx:useEffect]` — Infinite scroll `IntersectionObserver` (`threshold: 0.1`) is inactive when `!hasMore`, `isLoadingMore`, or `searchQuery.trim()` is non-empty.
- `[WordsPanel.tsx:isAdmin]` — Word deletion button (`handleDeleteWord`) is only rendered when `useIsAdmin()` returns `true`.

## Side Effects
- `[WordsPanel.tsx:fetchStats]` — Performs authenticated HTTP `GET` to `/api/spell-check/words/stats` (with optional `letter_group` query param).
- `[WordsPanel.tsx:fetchAllWords]` — Performs authenticated HTTP `GET` to `/api/spell-check/words` with `skip`, `limit`, and optional `letter_group` query params.
- `[WordsPanel.tsx:searchWords]` — Performs authenticated HTTP `GET` to `/api/spell-check/words/search?q=<query>&limit=10` with an `AbortSignal`.
- `[WordsPanel.tsx:handleDeleteWord]` — Opens confirmation modal via `AppContext.setModal`, performs authenticated HTTP `DELETE` to `/api/spell-check/words/${entry.id}`, refreshes stats, and dispatches toast notifications via `NotificationContext.addNotification`.
- `[WordsPanel.tsx:useEffect]` — Focuses `inputRef.current` 50ms after initial mount and registers an `IntersectionObserver` on `loaderRef.current`.

## Verification
- Run: `npm test`
