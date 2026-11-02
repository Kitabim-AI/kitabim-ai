# Library Component (`library`)

## Overview
Provides the primary book discovery experience, catalog bookshelf with infinite scroll pagination, virtual on-screen Uyghur keyboard, multi-tab search (Ask AI, Books, Content, Lookup, Spell), personal reading history, and bookmark management.

## Interface
- `[BookCard.tsx:BookCard]` — Presentation card for a book showing cover image, author, publication year, total pages, and reading progress.
- `[BookmarksTab.tsx:BookmarksTab]` — Tab view rendering grouped user bookmarks by book, with search filter, name editing, quote jumping, and deletion.
- `[ReadingHistoryTab.tsx:ReadingHistoryTab]` — Tab view rendering books currently or recently read by the user, page progress percentage, and last read timestamps.
- `[HomeView.tsx:HomeView]` — Main application landing page containing hero section, virtual Uyghur on-screen keyboard, multi-tab search bar, proverbs display, and book recommendations.
- `[LibraryView.tsx:LibraryView]` — Bookshelf catalogue view with infinite scroll pagination, tab switching (`all-books`, `reading`, `bookmarks`), and book status filtering.
- `[SearchOverlay.tsx:SearchOverlay]` — Global overlay search modal for full-text search across books, titles, and authors with debounced querying.
- `[SearchTabBar.tsx:SearchTabBar]` — Tab selector bar for multi-domain search modes (`ask`, `books`, `content`, `lookup`, `spell`).
- `[searchTabsConfig.ts:SEARCH_TABS]` — Tab definition configurations, default search tab key, and localized placeholder key helpers.
- `[HomeSearchTabResults.tsx:HomeSearchTabResults]` — Dispatcher component rendering results based on active search mode.
- `[ContentResultsList.tsx:ContentResultsList]` — Book content chunk search results viewer.
- `[LookupResultsList.tsx:LookupResultsList]` — Dictionary / vocabulary definitions lookup results viewer.
- `[QuranResultsList.tsx:QuranResultsList]` — Quranic verse lookup results viewer with ayah formatting.
- `[SpellCheckResult.tsx:SpellCheckResultView]` — Spell-check query result viewer with diff highlights.

## Invariants
- `[LibraryView.tsx:isAuthenticated]` — Automatically forces active tab to `all-books` if an unauthenticated user attempts to view `reading` or `bookmarks`.
- `[LibraryView.tsx:useEffect]` — Disables infinite scroll observer when `!hasMore` or `isLoadingMore`.
- `[BookmarksTab.tsx:isAuthenticated]` / `[ReadingHistoryTab.tsx:isAuthenticated]` — Displays `GuestAuthWall` if the user is unauthenticated.

## Side Effects
- `[BookmarksTab.tsx:PersistenceService.getBookmarksGroupedByBook]` — Fetches persisted user bookmarks.
- `[BookmarksTab.tsx:PersistenceService.updateBookmark]` / `PersistenceService.deleteBookmark]` — Modifies or removes user bookmarks.
- `[ReadingHistoryTab.tsx:PersistenceService.listReadingProgress]` — Fetches reading progress entries.
- `[LibraryView.tsx:loadMore]` — Triggers paginated book list loading from backend API.

## Verification
- Run: `npm test`
