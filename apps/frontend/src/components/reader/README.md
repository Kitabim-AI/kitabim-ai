# Reader Component (`reader`)

## Overview
Provides the full book reading and text editing experience, featuring virtualized page-by-page scrolling, inline OCR text editing, text selection sharing, bookmark creation, and integrated side-by-side RAG chat.

## Interface
- `[BookmarkPrompt.tsx:BookmarkPrompt]` — Modal and popover dialog for creating, naming, and updating a book bookmark.
- `[BookmarksDrawer.tsx:BookmarksDrawer]` — Slide-out side drawer displaying book bookmarks with jump-to-page and delete controls.
- `[GuestAuthWall.tsx:GuestAuthWall]` — Authentication prompt card shown to unauthenticated users attempting to access bookmarks or reading history.
- `[PageItem.tsx:PageItem]` — Individual book page component rendering text (`contentPageNumber` / `displayPageNumber` with `(PDF N)` footer), typography styling, text selection sharing triggers, `contentPageMap`-aware TOC jump buttons, and inline editor.
- `[ReaderView.tsx:ReaderView]` — Primary reading workspace integrating virtual scrolling, `POST /api/books/{id}/pages/{page_num}/set-start-page` start-page anchoring, reading progress tracking, book exports, and book-level chat assistant.
- `[VirtualScrollReader.tsx:default]` — Windowed virtualized scrolling list component handling dynamic page measurement and smooth scrolling.

## Invariants
- `[ReaderView.tsx:selectedBook]` — Returns `null` if `selectedBook` is null or undefined in `AppContext`.
- `[PageItem.tsx:isEditor]` — Restricts page editing, start page setting, TOC tagging, and page reprocessing controls to users with editor/admin privileges (`useIsEditor()`).

## Side Effects
- `[ReaderView.tsx:PersistenceService.updateReadingProgress]` — Saves user reading location and percentage completion to backend on page change.
- `[ReaderView.tsx:PersistenceService.downloadBook]` — Triggers book document export and file download.
- `[PageItem.tsx:onCreateBookmark]` / `onRenameBookmark` / `onDeleteBookmark` — Dispatches bookmark mutation handlers.

## Verification
- Run: `npm test`
