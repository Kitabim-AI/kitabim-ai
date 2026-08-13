# Manual ToC Page Marking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an editor/admin manually mark or unmark a reader page as a Table of Contents (ToC) page, correcting cases the OCR-time heuristic misses, and immediately purge that page's stale chunks from RAG/search when marking.

**Architecture:** `Page.is_toc` already exists in the schema. Add a repository method to flip it, a dedicated `POST /api/books/{book_id}/pages/{page_num}/toc` endpoint that also deletes the page's chunks when marking `true`, and a reader-page toggle button that calls it through the existing confirm-modal + optimistic-state-update pattern already used by sibling page actions (`handleReProcessPage`, `handleUpdatePage` in `useBookActions.ts`).

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async (backend), React + TypeScript + Vitest/RTL (frontend).

## Global Constraints

- Auth: `require_editor` (backend) / `useIsEditor()` (frontend) — same level as every other page action on this router. Never `require_admin`.
- No `print()` — n/a here (no new logging needed).
- No hardcoded user-visible strings — all new UI copy goes through `t('...')` with keys added to both `en.json` and `ug.json`.
- No raw SQL with user input — use SQLAlchemy bound parameters (already the pattern for every query touched here).
- Backend error messages use `t()` from `app.core.i18n`; the key `errors.page_not_found` already exists in both `services/backend/locales/en.json` and `ug.json` — reuse it, do not add a new one.
- The new Uyghur (`ug.json`) copy in this plan is an **unverified machine-generated first draft** (the user explicitly asked for a flagged draft rather than providing their own copy or an English placeholder) — call this out again at the end of the plan for the user's review.

---

### Task 1: `PagesRepository.set_is_toc`

**Files:**
- Modify: `packages/backend-core/app/db/repositories/pages_repository.py`
- Test: `packages/backend-core/tests/app/db/pages_repository_test.py`

**Interfaces:**
- Produces: `PagesRepository.set_is_toc(book_id: str, page_number: int, is_toc: bool, updated_by: str) -> bool` — returns `True` if a page row was matched and updated, `False` otherwise.

- [ ] **Step 1: Write the failing tests**

Add to `packages/backend-core/tests/app/db/pages_repository_test.py` (follow the existing `test_update_many_status`/`test_delete_by_book` style already in this file — fully mocked `AsyncSession`):

```python
@pytest.mark.asyncio
async def test_set_is_toc_marks_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    result = await repo.set_is_toc("b1", 5, True, "editor@example.com")
    assert result is True
    assert session.flush.called


@pytest.mark.asyncio
async def test_set_is_toc_unmarks_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res

    result = await repo.set_is_toc("b1", 5, False, "editor@example.com")
    assert result is True


@pytest.mark.asyncio
async def test_set_is_toc_returns_false_for_unknown_page():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res

    result = await repo.set_is_toc("b1", 999, True, "editor@example.com")
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/db/pages_repository_test.py -k set_is_toc -v`
Expected: FAIL with `AttributeError: 'PagesRepository' object has no attribute 'set_is_toc'`

- [ ] **Step 3: Implement `set_is_toc`**

In `packages/backend-core/app/db/repositories/pages_repository.py`, add this method to `PagesRepository`, placed after `update_many_status` (mirrors its `update(...)` + `rowcount` shape exactly):

```python
    async def set_is_toc(
        self, book_id: str, page_number: int, is_toc: bool, updated_by: str
    ) -> bool:
        """Manually mark or unmark a page as a Table of Contents page"""
        from sqlalchemy import update

        stmt = (
            update(Page)
            .where(Page.book_id == book_id, Page.page_number == page_number)
            .values(is_toc=is_toc, last_updated=func.now(), updated_by=updated_by)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/db/pages_repository_test.py -k set_is_toc -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/db/repositories/pages_repository.py packages/backend-core/tests/app/db/pages_repository_test.py
git commit -m "feat: add PagesRepository.set_is_toc for manual ToC flag correction"
```

---

### Task 2: Backend endpoint `POST /{book_id}/pages/{page_num}/toc`

**Files:**
- Modify: `packages/backend-core/app/models/schemas.py`
- Modify: `services/backend/api/endpoints/books_router.py`
- Test: `services/backend/tests/api/endpoints/books_router_toc_test.py` (new file)

**Interfaces:**
- Consumes: `PagesRepository.set_is_toc(book_id, page_number, is_toc, updated_by) -> bool` (Task 1). `ChunksRepository.delete_by_page(book_id: str, page_number: int) -> int` (already exists at `packages/backend-core/app/db/repositories/chunks_repository.py:62`, not yet imported in `books_router.py`).
- Produces: `PageTocUpdate` Pydantic schema (`is_toc: bool`, camelCase `isToc`). Route `POST /api/books/{book_id}/pages/{page_num}/toc` returning `{"status": "ok", "isToc": bool}` on success, `404` with `t("errors.page_not_found")` if the page doesn't exist.

- [ ] **Step 1: Add the `PageTocUpdate` schema**

In `packages/backend-core/app/models/schemas.py`, add directly after the `ExtractionResult` class (after line 48, before `class Book(BaseModel):`):

```python
class PageTocUpdate(BaseModel):
    """Request body for manually marking/unmarking a page as ToC"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    is_toc: bool  # API: isToc
```

- [ ] **Step 2: Write the failing endpoint tests**

Create `services/backend/tests/api/endpoints/books_router_toc_test.py`, following the direct-call + `importlib` module-loading pattern already used in `services/backend/tests/api/endpoints/books_router_caching_test.py` (loads the router module from its file path so it doesn't need the full app import graph):

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
from pathlib import Path
import importlib.util

BACKEND_DIR = Path(__file__).resolve().parents[3]
BACKEND_CORE_DIR = Path(__file__).resolve().parents[5] / "packages" / "backend-core"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_CORE_DIR))

BOOKS_PATH = BACKEND_DIR / "api" / "endpoints" / "books_router.py"
spec = importlib.util.spec_from_file_location("test_books_toc_endpoint_module", BOOKS_PATH)
books_endpoint = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(books_endpoint)

from app.models.schemas import PageTocUpdate
from app.models.user import User, UserRole


def make_user():
    return User(
        id="u1",
        email="editor@example.com",
        name="Editor",
        role=UserRole.EDITOR,
        provider="google",
    )


@pytest.mark.asyncio
async def test_set_page_toc_marks_and_deletes_chunks(monkeypatch):
    mock_pages_repo = AsyncMock()
    mock_pages_repo.set_is_toc.return_value = True
    mock_chunks_repo = AsyncMock()
    mock_chunks_repo.delete_by_page.return_value = 4

    monkeypatch.setattr(books_endpoint, "PagesRepository", lambda session: mock_pages_repo)
    monkeypatch.setattr(books_endpoint, "ChunksRepository", lambda session: mock_chunks_repo)

    session = AsyncMock()
    result = await books_endpoint.set_page_toc(
        book_id="b1",
        page_num=5,
        body=PageTocUpdate(is_toc=True),
        current_user=make_user(),
        session=session,
    )

    mock_pages_repo.set_is_toc.assert_awaited_once_with("b1", 5, True, "editor@example.com")
    mock_chunks_repo.delete_by_page.assert_awaited_once_with("b1", 5)
    assert result == {"status": "ok", "isToc": True}
    assert session.commit.called


@pytest.mark.asyncio
async def test_set_page_toc_unmark_does_not_touch_chunks(monkeypatch):
    mock_pages_repo = AsyncMock()
    mock_pages_repo.set_is_toc.return_value = True
    mock_chunks_repo = AsyncMock()

    monkeypatch.setattr(books_endpoint, "PagesRepository", lambda session: mock_pages_repo)
    monkeypatch.setattr(books_endpoint, "ChunksRepository", lambda session: mock_chunks_repo)

    session = AsyncMock()
    result = await books_endpoint.set_page_toc(
        book_id="b1",
        page_num=5,
        body=PageTocUpdate(is_toc=False),
        current_user=make_user(),
        session=session,
    )

    mock_pages_repo.set_is_toc.assert_awaited_once_with("b1", 5, False, "editor@example.com")
    mock_chunks_repo.delete_by_page.assert_not_called()
    assert result == {"status": "ok", "isToc": False}


@pytest.mark.asyncio
async def test_set_page_toc_404_for_unknown_page(monkeypatch):
    from fastapi import HTTPException

    mock_pages_repo = AsyncMock()
    mock_pages_repo.set_is_toc.return_value = False
    mock_chunks_repo = AsyncMock()

    monkeypatch.setattr(books_endpoint, "PagesRepository", lambda session: mock_pages_repo)
    monkeypatch.setattr(books_endpoint, "ChunksRepository", lambda session: mock_chunks_repo)

    with pytest.raises(HTTPException) as exc_info:
        await books_endpoint.set_page_toc(
            book_id="b1",
            page_num=999,
            body=PageTocUpdate(is_toc=True),
            current_user=make_user(),
            session=AsyncMock(),
        )

    assert exc_info.value.status_code == 404
    mock_chunks_repo.delete_by_page.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_toc_test.py -v`
Expected: FAIL with `AttributeError: module 'test_books_toc_endpoint_module' has no attribute 'set_page_toc'`

- [ ] **Step 4: Add the `ChunksRepository` import and the endpoint**

In `services/backend/api/endpoints/books_router.py`:

1. Add the import next to the existing `PagesRepository` import (around line 37):

```python
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.chunks_repository import ChunksRepository
```

2. Add `PageTocUpdate` to the existing `from app.models.schemas import (...)` block (around line 44-50):

```python
from app.models.schemas import (
    Book,
    PaginatedBooks,
    ContentSearchHit,
    PaginatedContentHits,
    ExtractionResult,
    PageTocUpdate,
    to_camel,
)
```

3. Add the endpoint immediately after `update_page_text` (the function ending with `return {"status": "ok", ...}` for that route — insert right after its closing, before the next `@router` decorator):

```python
@router.post("/{book_id}/pages/{page_num}/toc")
async def set_page_toc(
    book_id: str,
    page_num: int,
    body: PageTocUpdate,
    current_user: User = Depends(require_editor),
    session: AsyncSession = Depends(get_session),
):
    """Manually mark or unmark a page as a Table of Contents page"""
    pages_repo = PagesRepository(session)
    chunks_repo = ChunksRepository(session)

    updated = await pages_repo.set_is_toc(
        book_id, page_num, body.is_toc, current_user.email
    )
    if not updated:
        raise HTTPException(status_code=404, detail=t("errors.page_not_found"))

    if body.is_toc:
        await chunks_repo.delete_by_page(book_id, page_num)

    await session.commit()
    return {"status": "ok", "isToc": body.is_toc}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_toc_test.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add packages/backend-core/app/models/schemas.py services/backend/api/endpoints/books_router.py services/backend/tests/api/endpoints/books_router_toc_test.py
git commit -m "feat: add POST /books/{book_id}/pages/{page_num}/toc endpoint"
```

---

### Task 3: Frontend `PersistenceService.setPageToc`

**Files:**
- Modify: `apps/frontend/src/services/persistenceService.ts`

**Interfaces:**
- Consumes: `POST /api/books/{bookId}/pages/{pageNum}/toc` (Task 2), body `{ isToc: boolean }`.
- Produces: `PersistenceService.setPageToc(bookId: string, pageNum: number, isToc: boolean): Promise<void>` — throws on non-OK response, matching `updatePage`/`resetPage`.

- [ ] **Step 1: Implement `setPageToc`**

No existing test file covers `persistenceService.ts` directly (`updatePage`/`resetPage` aren't unit-tested there either — they're exercised through `useBookActions.test.tsx`, which mocks this whole module). Task 5 below covers this through that same mock. Add the method in `apps/frontend/src/services/persistenceService.ts` immediately after `resetPage` (after line 346):

```ts
  async setPageToc(bookId: string, pageNum: number, isToc: boolean): Promise<void> {
    const response = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/toc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ isToc })
    });
    if (!response.ok) {
      throw new Error("Failed to update page ToC flag");
    }
  },
```

- [ ] **Step 2: Type-check**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: No new errors.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/src/services/persistenceService.ts
git commit -m "feat: add PersistenceService.setPageToc"
```

---

### Task 4: `PageItem` toggle button

**Files:**
- Modify: `apps/frontend/src/components/reader/PageItem.tsx`
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`
- Test: `apps/frontend/src/tests/components/reader/PageItem.test.tsx`

**Interfaces:**
- Produces: new optional prop `onToggleToc?: (nextIsToc: boolean) => void` on `PageItem`. Renders a toolbar button reading `page.isToc` (falls back to `page.is_toc`, matching the existing `isTocPage={page?.isToc ?? page?.is_toc}` line already in this file) to decide label/icon and the value passed to `onToggleToc`.

- [ ] **Step 1: Add the i18n keys**

In `apps/frontend/src/locales/en.json`, in the `"reader"` block, insert after `"setStartPageSuccess"` (line 314) and before the `"reprocess": {` key (line 315):

```json
    "markAsToc": "Mark as ToC",
    "unmarkAsToc": "Unmark as ToC",
    "markAsTocTitle": "Mark this page as a Table of Contents page",
    "unmarkAsTocTitle": "Remove Table of Contents flag from this page",
```

In `apps/frontend/src/locales/ug.json`, in the `"reader"` block, insert after `"setStartPageSuccess"` (line 316) and before `"reprocess": {` (line 317) — **machine-translated first draft, needs your review**:

```json
    "markAsToc": "مۇندەرىجە قىلىش",
    "unmarkAsToc": "مۇندەرىجىدىن چىقىرىش",
    "markAsTocTitle": "بۇ بەتنى مۇندەرىجە بېتى قىلىپ بەلگىلەش",
    "unmarkAsTocTitle": "بۇ بەتتىن مۇندەرىجە بەلگىسىنى ئېلىپ تاشلاش",
```

- [ ] **Step 2: Write the failing tests**

Add to `apps/frontend/src/tests/components/reader/PageItem.test.tsx`:

```tsx
test('PageItem shows Mark as ToC button and calls onToggleToc(true) when page is not ToC', () => {
  const onToggleToc = vi.fn();
  renderPageItem({ page: { ...mockPage, isToc: false }, onToggleToc });

  const button = screen.getByText('reader.markAsToc');
  fireEvent.click(button);
  expect(onToggleToc).toHaveBeenCalledWith(true);
});

test('PageItem shows Unmark as ToC button and calls onToggleToc(false) when page is ToC', () => {
  const onToggleToc = vi.fn();
  renderPageItem({ page: { ...mockPage, isToc: true }, onToggleToc });

  const button = screen.getByText('reader.unmarkAsToc');
  fireEvent.click(button);
  expect(onToggleToc).toHaveBeenCalledWith(false);
});

test('PageItem hides the ToC toggle button for non-editors', () => {
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(false);
  renderPageItem({ page: { ...mockPage, isToc: false }, onToggleToc: vi.fn() });

  expect(screen.queryByText('reader.markAsToc')).not.toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: FAIL — `reader.markAsToc` / `reader.unmarkAsToc` text not found.

- [ ] **Step 4: Implement the button**

In `apps/frontend/src/components/reader/PageItem.tsx`:

1. Update the icon import (line 1):

```tsx
import { BookmarkCheck, Edit3, ListTree, ListX, Loader2, RotateCcw, Save } from 'lucide-react';
```

2. Add the prop to `PageItemProps` (after `onSetStartPage?: () => void;`, line 26):

```tsx
  onSetStartPage?: () => void;
  onToggleToc?: (nextIsToc: boolean) => void;
```

3. Destructure it in the component signature (line 40-41):

```tsx
  page, isActive, isEditing, fontSize, contentFontFamily, contentFontClassName, onSetActive, onEdit, onReprocess, onSetStartPage, onToggleToc,
  tempText, onTempTextChange, onSave, onCancel, isLoading, isSaving, isFullscreen, contentPageOffset, onTocPageClick
```

4. Render the button right after the `onSetStartPage` button block (after the closing `)}` of that block, still inside the `isEditor && !isEditing` toolbar `<div>`, i.e. right before the toolbar's closing `</div>` at line 97):

```tsx
              {onToggleToc && (
                <button
                  onClick={() => onToggleToc(!(page?.isToc ?? page?.is_toc))}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-lg text-xs font-bold uppercase"
                  title={(page?.isToc ?? page?.is_toc) ? t('reader.unmarkAsTocTitle') : t('reader.markAsTocTitle')}
                >
                  {(page?.isToc ?? page?.is_toc) ? <ListX size={12} /> : <ListTree size={12} />}
                  <span>{(page?.isToc ?? page?.is_toc) ? t('reader.unmarkAsToc') : t('reader.markAsToc')}</span>
                </button>
              )}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: PASS (all tests, including the 3 new ones)

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/components/reader/PageItem.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json apps/frontend/src/tests/components/reader/PageItem.test.tsx
git commit -m "feat: add ToC toggle button to PageItem"
```

---

### Task 5: `useBookActions.handleToggleToc`

**Files:**
- Modify: `apps/frontend/src/hooks/useBookActions.ts`
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`
- Test: `apps/frontend/src/tests/hooks/useBookActions.test.tsx`

**Interfaces:**
- Consumes: `PersistenceService.setPageToc(bookId, pageNum, isToc)` (Task 3).
- Produces: `handleToggleToc(bookId: string, pageNum: number, nextIsToc: boolean): void` — opens a confirm modal (mirroring `handleReProcessPage`'s `setModal` shape), and on confirm calls `PersistenceService.setPageToc`, updates `selectedBook.pages[].isToc` via `setSelectedBook`, and shows a success/error toast via `addNotification`.

- [ ] **Step 1: Add the i18n keys**

In `apps/frontend/src/locales/en.json`:

Under `"modal"` (after the `"resetPage": { ... }` block, line 780, before `"reOcrError": {` at line 781):

```json
    "markAsToc": {
      "title": "Mark as Table of Contents",
      "message": "Are you sure you want to mark page {{pageNum}} as a Table of Contents page? This will delete its existing chunks and exclude it from search/RAG.",
      "confirm": "Mark as ToC"
    },
    "unmarkAsToc": {
      "title": "Unmark Table of Contents",
      "message": "Are you sure you want to unmark page {{pageNum}} as a Table of Contents page? It will be re-included in search/RAG. Existing chunks are not regenerated automatically — use Reprocess if needed.",
      "confirm": "Unmark as ToC"
    },
```

Under `"common"` (after `"pageUpdated"`, line 55):

```json
    "pageTocMarked": "Page {{pageNum}} marked as Table of Contents.",
    "pageTocUnmarked": "Page {{pageNum}} unmarked as Table of Contents.",
    "pageTocError": "Failed to update Table of Contents flag for page {{pageNum}}. Please try again.",
```

In `apps/frontend/src/locales/ug.json` — **machine-translated first draft, needs your review**:

Under `"modal"` (after the `"resetPage": { ... }` block, line 799, before `"reOcrError": {` at line 800):

```json
    "markAsToc": {
      "title": "مۇندەرىجە قىلىپ بەلگىلەش",
      "message": "بۇ بەتنى ({{pageNum}}-بەت) مۇندەرىجە بېتى قىلىپ بەلگىلەمسىز؟ بۇ ھەرىكەت بۇ بەتنىڭ مەۋجۇت پارچىلىرىنى ئۆچۈرۈپ، ئىزدەش ۋە سۈنئىي ئەقىل جاۋابلىرىدىن چىقىرىۋېتىدۇ.",
      "confirm": "مۇندەرىجە قىلىش"
    },
    "unmarkAsToc": {
      "title": "مۇندەرىجە بەلگىسىنى ئېلىش",
      "message": "بۇ بەتنى ({{pageNum}}-بەت) مۇندەرىجىدىن چىقىرىۋېتەمسىز؟ بۇ بەت قايتىدىن ئىزدەش ۋە سۈنئىي ئەقىل جاۋابلىرىغا قوشۇلىدۇ. مەۋجۇت پارچىلار ئاپتوماتىك قايتا ھاسىل قىلىنمايدۇ — زۆرۈر بولسا «قايتا بىر تەرەپ قىلىش» نى ئىشلىتىڭ.",
      "confirm": "مۇندەرىجىدىن چىقىرىش"
    },
```

Under `"common"` (after `"pageUpdated"`, line 56):

```json
    "pageTocMarked": "{{pageNum}}-بەت مۇندەرىجە بېتى قىلىپ بەلگىلەندى.",
    "pageTocUnmarked": "{{pageNum}}-بەتتىن مۇندەرىجە بەلگىسى ئېلىندى.",
    "pageTocError": "{{pageNum}}-بەتنىڭ مۇندەرىجە بەلگىسىنى يېڭىلىيالمىدى. قايتا سىناڭ.",
```

- [ ] **Step 2: Write the failing tests**

Add to `apps/frontend/src/tests/hooks/useBookActions.test.tsx` (first add `setPageToc: vi.fn(),` to the `vi.mock('@/src/services/persistenceService', ...)` block near the top of the file, alongside the existing `resetPage: vi.fn(),`):

```tsx
test('useBookActions marks a page as ToC through confirm modal', async () => {
  vi.mocked(PersistenceService.setPageToc).mockResolvedValue(undefined as any);
  const { result, setModal, setSelectedBook } = createHook();

  act(() => {
    result.current.handleToggleToc('1', 1, true);
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({
    isOpen: true,
    type: 'confirm'
  }));

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.setPageToc).toHaveBeenCalledWith('1', 1, true);
  expect(setSelectedBook).toHaveBeenCalled();
});

test('useBookActions unmarks a page as ToC and reports errors', async () => {
  vi.mocked(PersistenceService.setPageToc).mockRejectedValue(new Error('boom'));
  const { result, setModal } = createHook();

  act(() => {
    result.current.handleToggleToc('1', 1, false);
  });

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.setPageToc).toHaveBeenCalledWith('1', 1, false);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookActions.test.tsx`
Expected: FAIL — `result.current.handleToggleToc is not a function`

- [ ] **Step 4: Implement `handleToggleToc`**

In `apps/frontend/src/hooks/useBookActions.ts`, add this function right after `handleReProcessPage` (after its closing `};` at line 119), and add `handleToggleToc,` to the returned object at the end of the hook (alongside `handleReProcessPage,` in the return block around line 532):

```ts
  const handleToggleToc = (bookId: string, pageNum: number, nextIsToc: boolean) => {
    const copy = nextIsToc ? 'markAsToc' : 'unmarkAsToc';
    setModal({
      isOpen: true,
      title: t(`modal.${copy}.title`),
      message: t(`modal.${copy}.message`, { pageNum }),
      type: 'confirm',
      confirmText: t(`modal.${copy}.confirm`),
      onConfirm: async () => {
        setModal((prev: any) => ({ ...prev, isOpen: false }));
        try {
          await PersistenceService.setPageToc(bookId, pageNum, nextIsToc);

          setSelectedBook(prev => {
            if (!prev || prev.id !== bookId) return prev;
            return {
              ...prev,
              pages: (prev.pages || []).map(r =>
                r.pageNumber === pageNum ? { ...r, isToc: nextIsToc } : r
              ),
            };
          });

          addNotification(
            t(nextIsToc ? 'common.pageTocMarked' : 'common.pageTocUnmarked', { pageNum }),
            'success'
          );
        } catch (err) {
          console.error("Failed to update page ToC flag", err);
          addNotification(t('common.pageTocError', { pageNum }), 'error');
        }
      }
    });
  };
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useBookActions.test.tsx`
Expected: PASS (all tests, including the 2 new ones)

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/hooks/useBookActions.ts apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json apps/frontend/src/tests/hooks/useBookActions.test.tsx
git commit -m "feat: add useBookActions.handleToggleToc"
```

---

### Task 6: Wire the button through `ReaderView` and `VirtualScrollReader`

**Files:**
- Modify: `apps/frontend/src/components/reader/ReaderView.tsx`
- Modify: `apps/frontend/src/components/reader/VirtualScrollReader.tsx`

**Interfaces:**
- Consumes: `PageItem`'s `onToggleToc?: (nextIsToc: boolean) => void` (Task 4), `bookActions.handleToggleToc(bookId, pageNum, nextIsToc)` (Task 5).

There is no existing dedicated test for the equivalent `onSetStartPage` plumbing in either `VirtualScrollReader.test.tsx` or `ReaderView.test.tsx` — this task follows that same established coverage level (prop-threading only, verified manually in Step 3 below plus the full test suite in Step 2) rather than introducing new test infrastructure these files don't otherwise have for this kind of wiring.

- [ ] **Step 1: Wire `VirtualScrollReader`**

In `apps/frontend/src/components/reader/VirtualScrollReader.tsx`:

1. Add the prop to `VirtualScrollReaderProps` (after `onSetStartPage?: (pageNum: number) => void;`, line 28):

```tsx
  onSetStartPage?: (pageNum: number) => void;
  onToggleToc?: (pageNum: number, nextIsToc: boolean) => void;
```

2. Destructure it (after `onSetStartPage,`, line 53):

```tsx
  onSetStartPage,
  onToggleToc,
```

3. Pass it to `PageItem` (after `onSetStartPage={() => onSetStartPage?.(pageNum)}`, line 288):

```tsx
                  onSetStartPage={() => onSetStartPage?.(pageNum)}
                  onToggleToc={(nextIsToc) => onToggleToc?.(pageNum, nextIsToc)}
```

- [ ] **Step 2: Wire `ReaderView`**

In `apps/frontend/src/components/reader/ReaderView.tsx`:

1. On the `VirtualScrollReader` render (after `onSetStartPage={(pageNum) => handleSetStartPage(pageNum)}`, line 621):

```tsx
                onSetStartPage={(pageNum) => handleSetStartPage(pageNum)}
                onToggleToc={(pageNum, nextIsToc) => bookActions.handleToggleToc(selectedBook.id, pageNum, nextIsToc)}
```

2. On the direct `PageItem` render in the non-virtual-scroll branch (after `onSetStartPage={() => handleSetStartPage(page.pageNumber)}`, line 655):

```tsx
                        onSetStartPage={() => handleSetStartPage(page.pageNumber)}
                        onToggleToc={(nextIsToc) => bookActions.handleToggleToc(selectedBook.id, page.pageNumber, nextIsToc)}
```

- [ ] **Step 3: Manual verification**

Run: `./deploy/local/rebuild-and-restart.sh frontend` (or `cd apps/frontend && npm run dev` if iterating locally), log in as an editor, open a book in the reader, and confirm:
- The "Mark as ToC" button appears on the page toolbar (both in and out of Virtual Scroll mode) and is hidden for non-editors.
- Clicking it opens the confirm modal with the mark-copy, and confirming shows a success toast and flips the button to "Unmark as ToC".
- Clicking "Unmark as ToC" opens the confirm modal with the unmark-copy, and confirming flips it back.

- [ ] **Step 4: Run the full frontend test suite**

Run: `cd apps/frontend && npx vitest run`
Expected: PASS (no regressions)

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/reader/ReaderView.tsx apps/frontend/src/components/reader/VirtualScrollReader.tsx
git commit -m "feat: wire ToC toggle button through ReaderView and VirtualScrollReader"
```

---

## Final Verification

- [ ] Backend: `cd packages/backend-core && python -m pytest tests/app/db/pages_repository_test.py` and `cd services/backend && python -m pytest tests/api/endpoints/books_router_toc_test.py` — both pass.
- [ ] Frontend: `cd apps/frontend && npx vitest run` — full suite passes.
- [ ] Manual end-to-end pass per Task 6 Step 3, on a real book with a mis-detected ToC page: confirm marking it removes its chunks (e.g. via the admin content-search tool or a RAG query that previously surfaced that page) and that it renders with ToC-style clickable links; confirm unmarking restores normal chunking-eligibility once reprocessed.
- [ ] **Flag for the user:** all new `ug.json` strings (Tasks 4 and 5) are an unverified machine-generated first draft, as agreed — they need your review before this is considered final Uyghur copy.
