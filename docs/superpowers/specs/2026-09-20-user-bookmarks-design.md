# Design Document: User Bookmarks & Reading Progress

## Overview
Add two related, account-scoped reading features: a silent "resume where I left off" position per book, and explicit named bookmarks (whole-page or a selected passage) a reader saves on purpose. Both are new — there is no existing per-user reading-progress or bookmark/favorite concept anywhere in the schema today (`Book`/`Page` are global entities with no user relation). Surfaced via per-page icons and a per-book drawer in the reader, plus two new tabs on the Library page, plus shortcuts in the account dropdown.

## Problem & Motivation
Today, reopening a book always starts from the top — `currentPage` (`AppContext.tsx`) is pure in-memory React state, never persisted. There's also no way to save "this passage mattered to me" for later; the closest existing feature, `useTextSelectionShare`/`ShareSearchResultModal` (`PageItem.tsx`), only lets you *share* a selection externally, not save it privately. This feature closes both gaps.

## Scope
- **Automatic reading progress**: one silently-tracked "last read page" per (user, book), used only to resume on reopen and to populate a "Continue Reading" list. No user-facing save action.
- **Manual bookmarks**: a user explicitly saves a whole page, or a page + selected passage, under a required name they choose at creation time.
- Both are **sign-in required** — guests cannot create either, and are prompted to sign in inline when they try.
- **Out of scope**: bookmark notes/descriptions beyond the name; local-only (unsynced) guest bookmarks; server-side search over bookmarks/progress (client-side filter only, lists are small and personal); a visual scroll-progress-bar bookmark-position indicator (discussed, not requested); sharing a bookmark (distinct, pre-existing Share feature is untouched).

## Access Control
All six new endpoints (§5) require an authenticated user via `Depends(require_reader)` (`services/backend/auth/dependencies.py:180` — any of admin/editor/reader, i.e. "must be logged in", same dependency `chat_router.py` uses to gate chat). This matches the product decision that bookmarking is an account feature, not a public/guest one — unlike the existing page/quote *share* feature, which is intentionally public.

On the frontend, tapping any bookmark-creation control while signed out does not call the API at all; it opens a lightweight inline sign-in prompt (reusing `useAuth`'s `loginWithGoogle`/`loginWithFacebook`), not the full-screen `GuestAuthWall.tsx` (that component is reserved for the harder guest reading-limit block and would be disproportionate for a single blocked action).

## Data Model & Migrations
Two new tables, following the existing numbered-migration-with-rollback convention (`packages/backend-core/migrations/`, next available numbers `095`/`096`).

**`reading_progress`** — one row per (user, book), upserted:
```sql
CREATE TABLE reading_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, book_id)
);
CREATE INDEX ix_reading_progress_user_updated ON reading_progress (user_id, updated_at DESC);
```
(`user_id`/`book_id` column types matched to `users.id`/`books.id`'s existing `String` primary key types in `packages/backend-core/app/db/models.py`.)

**`bookmarks`** — many rows per (user, book):
```sql
CREATE TABLE bookmarks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    name TEXT NOT NULL,
    quote_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_bookmarks_user_book ON bookmarks (user_id, book_id);
CREATE INDEX ix_bookmarks_user ON bookmarks (user_id);
```
`quote_text` is `NULL` for a whole-page bookmark, populated for a passage bookmark. `name` is required (`NOT NULL`, no default) — enforced client-side by the required-name prompt (§3), not by any auto-generated fallback.

Per the migration-first convention: these two migrations land first, then two new ORM models (`ReadingProgress`, `Bookmark`) added to `packages/backend-core/app/db/models.py`, then two new repositories, then endpoints — in that order.

## Backend

### Repositories (new, `packages/backend-core/app/db/repositories/`)
- **`reading_progress_repository.py`**: `upsert(user_id, book_id, page_number)` (INSERT ... ON CONFLICT (user_id, book_id) DO UPDATE, via SQLAlchemy's `pg_insert(...).on_conflict_do_update(...)` — no raw SQL), `list_recent(user_id, limit)` joining `books` for title/cover.
- **`bookmarks_repository.py`**: `create(user_id, book_id, page_number, name, quote_text=None)`, `list(user_id, book_id=None)` (optional book scope), `get(id, user_id)` (ownership-checked), `update_name(id, user_id, name)`, `delete(id, user_id)`. Every mutating method takes `user_id` and filters by it — a user can only touch their own rows, checked at the repository layer, not just implied by the endpoint's auth dependency.

### Endpoints (new file, `services/backend/api/endpoints/bookmarks_router.py`)
A dedicated router (matching the existing one-router-per-domain convention — `share_router.py`, `dictionary_router.py`, etc. — rather than growing the already-large `books_router.py`), registered alongside the other 23 routers in the app's router include.

| Method & Path | Body / Query | Behavior |
|---|---|---|
| `PUT /bookmarks/progress/{book_id}` | `{page_number}` | Upsert this user's reading progress for the book. |
| `GET /bookmarks/progress` | — | List this user's books with progress, most-recent first (Continue Reading tab). |
| `POST /bookmarks/{book_id}` | `{page_number, name, quote_text?}` | Create a bookmark. |
| `GET /bookmarks` | `?book_id=` (optional) | List this user's bookmarks, optionally scoped to one book. |
| `PATCH /bookmarks/{bookmark_id}` | `{name}` | Rename. 404 if not owned by the caller. |
| `DELETE /bookmarks/{bookmark_id}` | — | Remove. 404 if not owned by the caller. |

All six use `Depends(require_reader)` and take the user id from the resolved user, never from a request parameter — no bookmark endpoint accepts a client-supplied `user_id`.

## Frontend

### 1. Auto progress tracking
`AppContext.tsx` already tracks the centered/active page in view (`currentPage`, driven by an `IntersectionObserver` inside `VirtualScrollReader.tsx`) but never persists it. New: a debounced effect (fires ~2s after `currentPage` stops changing, plus a flush on unmount/`visibilitychange`) calls `PUT /bookmarks/progress/{book_id}`. On opening a book, if no in-app deep link (`AppContext.tsx`'s existing `pageNumber` route-parsing) specifies a page, the saved progress (fetched once per book open) seeds `initialPage` instead of defaulting to page 1.

### 2. Whole-page bookmark — `PageItem.tsx`
Each `PageItem` gets its own bookmark icon in its hover-action row — same hover/active visibility behavior as the existing icons (Edit, Reprocess, Set-as-Page-1, TOC toggle), but rendered **outside** the `isEditor` gate (`PageItem.tsx:108`), since this is a feature for every reader, not editors. Icon is outline when the page has no bookmark, filled when it does (state known from the bookmark list already loaded for the drawer, §4).
- Tap when unbookmarked → small inline popover: a text input pre-filled with a default name (e.g. `"Page 42"`), Save/Cancel. Save calls `POST /bookmarks/{book_id}` with `{page_number, name}`, no `quote_text`.
- Tap when already bookmarked → opens that bookmark's entry for rename/delete (not an instant delete — avoids an accidental-tap data loss).

### 3. Passage bookmark — `PageItem.tsx`
Extends the existing text-selection popover (`useTextSelectionShare`, currently rendering one floating Share button on selection, `PageItem.tsx:212-230`) with a second floating button (Bookmark icon) next to Share. Tapping it opens the same required-name popover as §2, then `POST /bookmarks/{book_id}` with `{page_number, name, quote_text: textSelection.text}`.

### 4. Per-book bookmarks drawer — reader
A new icon in the reader's persistent top toolbar (distinct from the per-page bookmark icons — this one opens a list, it doesn't create anything) opens a slide-in drawer scoped to the current book (`GET /bookmarks?book_id=`), sorted by `page_number`: name, page number, quote snippet if present. Tapping an entry scrolls to that page (existing scroll-to-page mechanism, same one `onTocPageClick` uses) and, for passage bookmarks, re-runs `useQuoteHighlight` against `quote_text` to highlight it on arrival — reusing the exact hook already built for shared-quote deep links. Inline rename/delete.

### 5. Library page — two new tabs
The Library page (currently a single view) becomes a 3-tab page: **All Books** (today's unchanged content), **Continue Reading**, **Bookmarks**.
- **Continue Reading**: `GET /bookmarks/progress`, rendered with the existing `BookCard` component, most-recent first; tapping opens the reader at the saved page. Empty state when the list is empty (signed-in users with no reading history yet).
- **Bookmarks**: `GET /bookmarks` (no `book_id`), grouped by book title; each row shows name / page / quote snippet; tapping jumps into the reader at that page (+ quote highlight, same as §4). Inline rename/delete.
- **Guests**: since both backing endpoints require auth (§Access Control), neither tab calls its endpoint for a signed-out user. Each tab instead renders the existing `GuestAuthWall.tsx` component in place of the list — consistent with how the reader already uses that component to gate a whole content area (as opposed to the lightweight inline sign-in prompt used for a single bookmark-creation tap, §2/§3, which gates one action rather than a whole page section).
- Both tabs get a search input at the top, visually matching the existing tab search-box convention (`searchTabsConfig.ts`'s placeholder/no-results i18n pattern), but implemented as an **instant client-side filter** over the already-fetched list (by book title for Continue Reading; by bookmark name or book title for Bookmarks) — no new query params, no debounce, no backend change beyond §5's endpoints as already specified.

### 6. Profile menu shortcuts — `AuthButton.tsx`'s `UserMenu`
Two new entries added to the dropdown's menu content (`AuthButton.tsx:231-250`), below the user header and above Logout: "Continue Reading" and "Bookmarks", each calling `setView('library')` with the corresponding tab pre-selected (e.g. via the same query-string tab param the Library page itself reads). Pure navigation shortcuts — no separate data fetching, no new page. Since `UserMenu` already returns `null` when `!user` (`AuthButton.tsx:181`), these never render for guests, consistent with bookmarking being sign-in-only.

## Data Flow Summary
1. **Reading**: scroll → `currentPage` changes → debounced `PUT /bookmarks/progress/{book_id}` → next time this book is opened (from anywhere: Library, Continue Reading, a deep link), the reader seeds `initialPage` from the fetched progress instead of page 1.
2. **Bookmarking a page**: tap the page's bookmark icon → name prompt → `POST /bookmarks/{book_id}` → icon fills in; the bookmark now appears in this book's drawer (§4) and the global Bookmarks tab (§5).
3. **Bookmarking a passage**: select text → floating Bookmark button (next to Share) → name prompt → `POST /bookmarks/{book_id}` with `quote_text` set.
4. **Revisiting a bookmark**: tap it (drawer or Bookmarks tab) → reader scrolls to `page_number` → if `quote_text` is set, `useQuoteHighlight` highlights it, same mechanism as an opened shared-quote link.

## Testing
- **Backend**: `reading_progress_repository`/`bookmarks_repository` unit tests — upsert-on-conflict behavior, ownership-scoped `get`/`update`/`delete` (attempting to touch another user's bookmark returns not-found, never leaks existence). `bookmarks_router` endpoint tests — auth required on all six routes (401/403 for guests), full CRUD happy path, `GET /bookmarks?book_id=` scoping.
- **Frontend**: debounced progress-save effect (fires once after `currentPage` settles, flushes on unmount); `PageItem` bookmark icon toggles correctly per-page (not global) and stays independent of `isEditor`; the name-prompt popover blocks save on empty name; passage bookmark captures the exact selected text; Library tab client-side filters match by title/name; profile-menu shortcuts deep-link to the correct pre-selected tab; guest tap opens the inline sign-in prompt and makes no API call.

## Verification Plan
1. Backend: `pytest` for the new repository and router tests.
2. Frontend: `npm test` inside `apps/frontend/` for the new/extended test files above.
3. Manual: rebuild via `./deploy/local/rebuild-and-restart.sh all`; as a signed-in user, read partway into a book, close it, reopen from Library — confirm it resumes at the right page; bookmark a whole page and a selected passage, confirm both appear (with correct name/snippet) in the per-book drawer, the Library "Bookmarks" tab, and rename/delete work in both places; confirm the "Continue Reading" tab and profile-menu shortcuts show the right book/page; as a guest, confirm tapping either bookmark control prompts sign-in and creates nothing; check RTL layout and dark mode for the new drawer, tabs, and name-prompt popover.
