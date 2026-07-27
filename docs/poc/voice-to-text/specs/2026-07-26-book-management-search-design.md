# Design Document: Book Management Tab Multi-Field Search

**Date**: 2026-07-26  
**Feature**: Book Management Search Box Multi-Field Filter (Title, Author, Category)  
**Status**: Approved  

---

## 1. Overview
The search box in the Book Management tab (Admin Panel) enables administrators and editors to search through all uploaded books. This design enhances the search capabilities so queries filter across book title, author, and category fields simultaneously, including support for Uyghur orthographic normalization and volume-number queries.

---

## 2. Requirements & Behavior

### 2.1 User Interface & Guidance
- In the Admin Panel's Book Management tab (`AdminView.tsx`), update the search bar input placeholder to explicitly inform users that searching covers title, author, and category.
- Locales:
  - English (`en.json`): `"searchPlaceholder": "Search by book title, author, or category..."`
  - Uyghur (`ug.json`): `"searchPlaceholder": "كىتاب نامى، ئاپتورى ياكى تۈرى بويىچە ئىزدەش..."`

### 2.2 Backend Search Logic
- Endpoint: `GET /api/books/?q={query}` in `services/backend/api/endpoints/books_router.py`.
- Ensure SQL query conditions (`BookDB`) filter across:
  1. `BookDB.title` (ILike, original & alternate Uyghur characters)
  2. `BookDB.author` (ILike, original & alternate Uyghur characters)
  3. `func.array_to_string(BookDB.categories, ",")` (ILike, original & alternate Uyghur characters)
- Update both standard search query evaluation and volume number detection (`volume_match`) branches to consistently include category search matching.

### 2.3 Repository Layer
- Repository: `packages/backend-core/app/db/repositories/books_repository.py`.
- Update `BooksRepository.find_many()` to search `func.array_to_string(Book.categories, ",")` alongside `Book.title` and `Book.author`.

---

## 3. Architecture & Data Flow

```
+------------------------+      HTTP GET       +------------------------------------+
|  AdminView.tsx         | ----------------->  |  services/backend                  |
|  (Book Management Tab) |  /api/books/?q=...  |  books_router.py                   |
+------------------------+                     +------------------------------------+
                                                                  |
                                                                  v
                                              +-------------------------------------+
                                              | SQLAlchemy ORM                      |
                                              | WHERE title ILIKE %q%               |
                                              |    OR author ILIKE %q%              |
                                              |    OR array_to_string(categories)   |
                                              |       ILIKE %q%                     |
                                              +-------------------------------------+
                                                                  |
                                                                  v
                                              +-------------------------------------+
                                              | PostgreSQL DB (books table)         |
                                              +-------------------------------------+
```

---

## 4. Verification & Testing Strategy
1. **Frontend Verification**:
   - Verify search input placeholder in Admin -> Book Management tab.
2. **Backend API Verification**:
   - Query `/api/books/?q=<category_name>` (e.g. `تارىخ`, `ھېكايە`, `Fiction`) and verify books with matching categories are returned.
   - Query with title keywords and author names to ensure no regressions.
   - Query volume numbers (e.g. `ئانا يۇرت 3`) to ensure volume-aware matching works with category terms.
3. **Local Docker Deployment**:
   - Run `./deploy/local/rebuild-and-restart.sh all` to update running local containers.
