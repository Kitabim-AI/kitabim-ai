# Design Document: Manual ToC Page Marking

## Overview
Give editors/admins a button on the reader page to manually mark (and unmark) a page as a Table of Contents (ToC) page, correcting cases where the automatic OCR-time heuristic fails to recognize a ToC page.

## Problem & Motivation
`Page.is_toc` (`packages/backend-core/app/db/models.py:178`) is set exactly once, during OCR, by the heuristic `is_toc_page()` (`packages/backend-core/app/utils/text.py:125`). There is no way to correct a wrong classification afterward. Downstream, `is_toc=True` pages are excluded from chunking (`chunking_job.py:81`), RAG/search (`chunks_repository.py`, `rag/retrieval.py:333`), and summary generation (`summary_job.py:97`). When the heuristic misses a ToC page, that page's already-generated chunks continue polluting RAG/search results indefinitely, since nothing re-evaluates `is_toc` after OCR.

The `is_toc` column, its exclusion logic everywhere it's consumed, and the frontend's read-only rendering of ToC pages (`MarkdownContent.tsx`) already exist and require no changes — this feature is additive at the repository, router, and frontend layers only.

## Proposed Changes

### 1. `packages/backend-core/app/db/repositories/pages_repository.py`

Add `set_is_toc(book_id: str, page_number: int, is_toc: bool, updated_by: str) -> bool`, following the existing `update_status`/`update_many_status` bulk-update pattern in this file:

```python
async def set_is_toc(self, book_id: str, page_number: int, is_toc: bool, updated_by: str) -> bool:
    result = await self.session.execute(
        update(Page)
        .where(Page.book_id == book_id, Page.page_number == page_number)
        .values(is_toc=is_toc, last_updated=datetime.now(timezone.utc), updated_by=updated_by)
    )
    return result.rowcount > 0
```

### 2. `packages/backend-core/app/models/schemas.py`

Add `PageTocUpdate` (camelCase alias config, matching every other schema in this file):

```python
class PageTocUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    is_toc: bool
```

### 3. `services/backend/api/endpoints/books_router.py`

Add `POST /{book_id}/pages/{page_num}/toc`, placed next to `reset_page`/`update_page_text`:

- Auth: `current_user: User = Depends(require_editor)` — same level as every other page action on this router (edit text, reprocess, reset, set start page). Not restricted to `require_admin`.
- Body: `PageTocUpdate`.
- Behavior:
  1. Call `pages_repo.set_is_toc(book_id, page_num, body.is_toc, current_user.email)`. If it returns `False`, raise `HTTPException(404, detail=t("errors.page_not_found"))`.
  2. If `body.is_toc is True`: also call `await chunks_repo.delete_by_page(book_id, page_num)` (`chunks_repository.py:62`, already exists) to remove stale chunks/embeddings for that page immediately — matching how normally-detected ToC pages never get chunked in the first place.
  3. If `body.is_toc is False`: flag flip only. No chunk regeneration — an editor who wants chunks rebuilt uses the existing Reprocess/Reset action separately.
  4. `await session.commit()`.
  5. Return `{"status": "ok", "isToc": body.is_toc}`.
- Book summary regeneration is explicitly out of scope — a single mis-flagged page causes only minor summary drift, and summaries are already refreshed through existing reprocessing flows.

### 4. `apps/frontend/src/services/persistenceService.ts`

Add `setPageToc(bookId: string, pageNum: number, isToc: boolean)`, same `authFetch(...).then(r => r.ok)` wrapper shape as `updatePage`/`resetPage` (`persistenceService.ts:328-346`), posting `{ isToc }` to the new endpoint.

### 5. `apps/frontend/src/components/reader/PageItem.tsx`

Add optional prop `onToggleToc?: (nextIsToc: boolean) => void`, rendered in the existing admin hover-toolbar (`isEditor && !isEditing`, line 83) alongside Reprocess / Edit / Mark as Page 1, following that toolbar's existing icon-button styling. Single toggle button, label/icon driven by `page.isToc`:
- `isToc` false → label `t('reader.markAsToc')` ("Mark as ToC"), icon `ListTree`, calls `onToggleToc?.(true)`.
- `isToc` true → label `t('reader.unmarkAsToc')` ("Unmark as ToC"), icon `ListX`, calls `onToggleToc?.(false)`.

### 6. `apps/frontend/src/components/reader/ReaderView.tsx`

Add `handleToggleToc(pageNumber: number, nextIsToc: boolean)`, mirroring `handleSetStartPage`'s confirm-modal flow (`ReaderView.tsx:372-398`) exactly: `setModal({ isOpen: true, title, message, type: 'confirm', confirmText, onConfirm: async () => {...} })`, calling `persistenceService.setPageToc(...)` inside `onConfirm`, then updating the page's local `isToc` state and showing a success toast via `addNotification`.

Confirm copy differs by direction:
- Marking (`nextIsToc === true`): message explicitly warns that this page's existing chunks will be deleted and it will be excluded from search/RAG.
- Unmarking (`nextIsToc === false`): lighter confirm copy, no chunk-deletion warning (there is none — chunks aren't regenerated automatically).

Wire `onToggleToc={(next) => handleToggleToc(page.pageNumber, next)}` on both `PageItem` render sites (mirroring how `onSetStartPage` is wired at `ReaderView.tsx:621,655`).

### 7. i18n — `apps/frontend/src/locales/en.json` and `ug.json`

Add under the existing `reader` namespace: `markAsToc`, `unmarkAsToc`, `markAsTocTitle`, `unmarkAsTocTitle`, `markAsTocConfirmTitle`, `markAsTocConfirmMessage`, `unmarkAsTocConfirmTitle`, `unmarkAsTocConfirmMessage`, `markAsTocSuccess`, `unmarkAsTocSuccess`.

### 8. Tests

- **Repository** (`packages/backend-core/tests/app/db/pages_repository_test.py`): `set_is_toc` sets `is_toc`/`last_updated`/`updated_by` and returns `True`; returns `False` for an unknown `(book_id, page_number)`.
- **Endpoint** (wherever `books_router` page actions are tested — `services/backend/tests/api/endpoints/`): marking a page `isToc=true` deletes that page's chunks and leaves other pages' chunks untouched; unmarking (`isToc=false`) does not delete chunks; unknown page returns 404; non-editor role returns 403.
- **Frontend** (`PageItem` and/or `ReaderView` tests): toggle button hidden for non-editor; label/icon reflect `page.isToc`; click opens confirm modal and, on confirm, calls `setPageToc` with the expected `isToc` value.

## Verification Plan
1. Backend: `pytest packages/backend-core/tests/app/db/pages_repository_test.py` and the updated/new `books_router` endpoint test file.
2. Frontend: `npm test` inside `apps/frontend/` for the updated `PageItem`/`ReaderView` tests.
3. Manual: rebuild via `./deploy/local/rebuild-and-restart.sh all`, log in as an editor, open a book with a mis-detected ToC page in the reader, click "Mark as ToC", confirm the page is excluded from search/RAG afterward (its chunks are gone) and renders with ToC-style link formatting; click "Unmark as ToC" on a page and confirm the flag clears; confirm the buttons are absent for a non-editor user.
