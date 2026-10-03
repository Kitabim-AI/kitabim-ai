# Design Specification: Separate Reading History and Bookmarks Tabs

**Date**: 2026-10-03  
**Branch**: `feature/user-bookmark`  
**Status**: Approved by User  

---

## 1. Overview & Goals

Currently, the user's reading history (`PersistenceService.listReadingProgress()`) and bookmarks (`PersistenceService.listBookmarks()`) are merged into a single library tab (`reading-bookmarks` / "ئوقۇۋاتقانلىرىم ۋە خەتكۈشلەر").

This design separates them into two distinct, dedicated tabs:
1. **Reading History Tab (`reading` / "ئوقۇۋاتقانلىرىم")**: Displays books the user has read / is reading. Clicking a book card directly opens the book at the last read page (no separate "continue reading" button).
2. **Bookmarks Tab (`bookmarks` / "خەتكۈشلەر")**: Retains the existing polished UX of `ReadingBookmarksTab`, but **strictly filters out any book that has 0 bookmarks**. Only books with at least one saved bookmark will be displayed.

---

## 2. Architecture & Components

```
apps/frontend/src/components/library/
├── LibraryView.tsx              # Updates top-level tabs: [All Books, Reading, Bookmarks]
├── ReadingHistoryTab.tsx        # New: Clean grid of read books; clicks open last-read page
└── BookmarksTab.tsx             # Dedicated: Preserves current UX, filtered to books with bookmarks > 0
```

### 2.1 Tab Navigation in `LibraryView.tsx`

* **Tabs Array** (for authenticated users):
  1. `all-books`: Label `t('library.tabs.allBooks')` ("بارلىق كىتابلار"), Icon `LibraryBig`.
  2. `reading`: Label `t('library.tabs.reading')` ("ئوقۇۋاتقانلىرىم"), Icon `History`.
  3. `bookmarks`: Label `t('library.tabs.bookmarks')` ("خەتكۈشلەر"), Icon `BookMarked`.
* **Guest Access**:
  * Unauthenticated users only see `all-books`.
  * If a user logs out while on `reading` or `bookmarks`, `activeTab` automatically switches to `all-books`.
* **Top-Right Count Badge**:
  * `all-books`: `{totalBooks} {t('home.totalBooks')}`
  * `reading`: `{readingCount} {t('home.totalBooks')}`
  * `bookmarks`: `{bookmarksCount} {t('library.readingBookmarks.bookmarksCount')}`

---

## 3. Component Details

### 3.1 `ReadingHistoryTab.tsx`
* **Data Source**: `PersistenceService.listReadingProgress()`.
* **Search**: Filters books by `bookTitle`.
* **Book Card Presentation**:
  * Book cover, title, author/volume, last read page pill (e.g. `45-بەت`), and relative updated time.
  * **Click Behavior**: Clicking anywhere on the book card calls `onOpenBook(book.bookId, book.pageNumber)`.
  * **No separate "Continue Reading" button** — streamlined visual presentation.
* **Empty State**: Friendly Uyghur empty message if no reading progress exists.

### 3.2 `BookmarksTab.tsx`
* **Data Source**: `PersistenceService.listBookmarks()` and `PersistenceService.listReadingProgress()`.
* **Core Rule**: **Only display books where `bookmarks.length > 0`**.
* **UX Continuity**: Retains all existing features of `ReadingBookmarksTab`:
  * Search by bookmark name, quote text, and book title.
  * Collapsible / organized bookmark cards grouped under the book header.
  * Page bookmarks and quote bookmarks with distinct styling.
  * Inline renaming of bookmarks.
  * Deletion of bookmarks.
  * Clicking a bookmark opens the book at that page (and highlights the quote if applicable).

---

## 4. Localization (`ug.json` & `en.json`)

Update `library.tabs` in translation files:
* `ug.json`:
  ```json
  "tabs": {
    "allBooks": "بارلىق كىتابلار",
    "reading": "ئوقۇۋاتقانلىرىم",
    "bookmarks": "خەتكۈشلەر"
  }
  ```
* `en.json`:
  ```json
  "tabs": {
    "allBooks": "All Books",
    "reading": "Reading History",
    "bookmarks": "Bookmarks"
  }
  ```

---

## 5. Testing & Verification

1. **Unit & Component Tests**:
   * Update `LibraryView.test.tsx` to verify all 3 tabs render when authenticated.
   * Add tests for `ReadingHistoryTab`:
     * Clicking a book opens it at `pageNumber`.
     * Does not render bookmarks or "continue reading" button.
   * Add tests for `BookmarksTab`:
     * Books with 0 bookmarks are not shown.
     * Books with bookmarks > 0 render their bookmarks properly.
2. **Build Verification**:
   * Run `npm run build --workspace apps/frontend` to ensure zero compilation or typing issues.
