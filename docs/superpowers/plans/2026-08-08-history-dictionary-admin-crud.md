# History Dictionary Admin Add/Edit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins create and edit `history_dictionary` entries from a modal on the History Dictionary panel, instead of only through the AI extraction → staging → approval pipeline.

**Architecture:** Two new admin-gated REST endpoints (`POST` and `PATCH /api/history-dictionary`) added to the existing `history_dictionary_router.py`, backed entirely by pre-existing `DictionaryRepository` methods (no repository or DB changes). The frontend `HistoryDictionaryPanel.tsx` gains an add/edit `createPortal` modal, following the exact pattern already used by `AutoCorrectRulesPanel.tsx`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async ORM (backend); React, TypeScript, Vitest + Testing Library (frontend).

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)` (not needed in this feature — no new logging).
- No `os.environ.get()` in application code — use `settings.*` (not applicable — no new config).
- No hardcoded user-visible strings — all HTTP error `detail` text goes through `t("errors.key")` from `app.core.i18n`; all frontend copy goes through `t()` from the i18n context, with keys added to both `apps/frontend/src/locales/en.json` and `ug.json`, and backend keys added to both `services/backend/locales/en.json` and `ug.json`.
- No raw SQL with user input — both new endpoints go through `DictionaryRepository`, which uses SQLAlchemy ORM/bound parameters throughout.
- Migration file → ORM model → repository → endpoint ordering: the first three layers already exist (`HistoryDictionary` ORM model, `create_history_dictionary_entry`/`update_history_dictionary_entry`/`find_matching_history_term`/`get_history_dictionary_by_id` repository methods) — this plan only adds the endpoint layer and the frontend.
- All new API endpoints need an auth dependency — both new endpoints use `current_user: User = Depends(require_admin)`, matching the existing `DELETE /history-dictionary/{entry_id}` endpoint in the same file.

---

## Task 1: `POST /api/history-dictionary` — create endpoint

**Files:**
- Modify: `services/backend/api/endpoints/history_dictionary_router.py`
- Modify: `services/backend/locales/en.json`
- Modify: `services/backend/locales/ug.json`
- Test: `services/backend/tests/api/endpoints/history_dictionary_router_test.py`

**Interfaces:**
- Consumes: `DictionaryRepository` (`app.db.repositories.dictionary_repository.DictionaryRepository`) — methods `find_matching_history_term(term: str) -> HistoryDictionary | None` and `create_history_dictionary_entry(**fields: Any) -> HistoryDictionary`. `require_admin` from `auth.dependencies`. `t` from `app.core.i18n`.
- Produces: Pydantic model `HistoryEntryCreate` (fields: `term: str`, `transliteration: Optional[str] = None`, `definition: Optional[str] = None`) and route function `create_history_entry`, both importable from `api.endpoints.history_dictionary_router` — Task 3 (frontend) calls this endpoint at `POST /api/history-dictionary`; Task 2 reuses the same file's imports.

- [ ] **Step 1: Write the failing tests**

Add to `services/backend/tests/api/endpoints/history_dictionary_router_test.py`, after the existing `test_delete_history_entry_not_found` test (keep the file's existing `setup_paths()`/`_mock_admin()` helpers and `AsyncMock`/`MagicMock` style — do not introduce a different mocking approach):

```python
@pytest.mark.asyncio
async def test_create_history_entry():
    setup_paths()
    from unittest.mock import patch
    from api.endpoints.history_dictionary_router import (
        create_history_entry,
        HistoryEntryCreate,
    )

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.find_matching_history_term.return_value = None
    created = MagicMock()
    created.id = 5
    created.term = "كاسى"
    created.transliteration = "Kasi"
    created.definition = "ھىندىستاندىكى قەدىمكى دۆلەت"
    created.letter_group = "ك"
    mock_repo.create_history_dictionary_entry.return_value = created

    with patch(
        "api.endpoints.history_dictionary_router.DictionaryRepository",
        return_value=mock_repo,
    ):
        result = await create_history_entry(
            body=HistoryEntryCreate(
                term="كاسى",
                transliteration="Kasi",
                definition="ھىندىستاندىكى قەدىمكى دۆلەت",
            ),
            session=mock_session,
            current_user=_mock_admin(),
        )

    assert result is created
    mock_repo.find_matching_history_term.assert_called_once_with("كاسى")
    mock_repo.create_history_dictionary_entry.assert_called_once_with(
        term="كاسى",
        transliteration="Kasi",
        definition="ھىندىستاندىكى قەدىمكى دۆلەت",
        letter_group="ك",
    )
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_history_entry_duplicate_term():
    setup_paths()
    from unittest.mock import patch
    from api.endpoints.history_dictionary_router import (
        create_history_entry,
        HistoryEntryCreate,
    )
    from fastapi import HTTPException

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    existing = MagicMock()
    existing.id = 3
    existing.term = "كاسى"
    mock_repo.find_matching_history_term.return_value = existing

    with patch(
        "api.endpoints.history_dictionary_router.DictionaryRepository",
        return_value=mock_repo,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_history_entry(
                body=HistoryEntryCreate(term="كاسى"),
                session=mock_session,
                current_user=_mock_admin(),
            )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["existing_id"] == 3
    mock_repo.create_history_dictionary_entry.assert_not_called()
    mock_session.commit.assert_not_called()


def test_history_entry_create_rejects_empty_term():
    setup_paths()
    from api.endpoints.history_dictionary_router import HistoryEntryCreate
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        HistoryEntryCreate(term="   ")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest services/backend/tests/api/endpoints/history_dictionary_router_test.py -v -k create_history_entry or history_entry_create`
Expected: FAIL with `ImportError: cannot import name 'create_history_entry'` (or `HistoryEntryCreate`) from `api.endpoints.history_dictionary_router`.

- [ ] **Step 3: Add the `errors.history_entry_duplicate_term` locale key**

In `services/backend/locales/en.json`, inside the top-level `"errors"` object, add (alphabetical position doesn't matter — this file isn't sorted; add it next to the other dictionary-related keys, e.g. right after `"staging_synthesis_failed"` if present, otherwise anywhere inside `"errors"`):

```json
    "history_entry_duplicate_term": "An entry for this term already exists",
```

In `services/backend/locales/ug.json`, inside the top-level `"errors"` object, add:

```json
    "history_entry_duplicate_term": "بۇ ئاتالغۇ ئۈچۈن خاتىرە ئاللىبۇرۇن مەۋجۇت",
```

- [ ] **Step 4: Implement the endpoint**

In `services/backend/api/endpoints/history_dictionary_router.py`, update the imports at the top of the file:

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, distinct, delete, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.i18n import t
from app.db.session import get_session
from app.db.models import HistoryDictionary
from app.db.repositories.dictionary_repository import DictionaryRepository
from app.models.user import User
from auth.dependencies import require_admin
```

(This adds `field_validator` to the `pydantic` import, and adds the two new imports `app.core.i18n.t` and `app.db.repositories.dictionary_repository.DictionaryRepository`. Leave every existing import and line as-is otherwise.)

Add this new Pydantic model directly below the existing `HistoryStatsOut` class (i.e. after the `# ── Response schemas ──` block, before `# ── Endpoints ──`):

```python
class HistoryEntryCreate(BaseModel):
    term: str
    transliteration: Optional[str] = None
    definition: Optional[str] = None

    @field_validator("term")
    @classmethod
    def validate_term_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Term cannot be empty")
        return v.strip()
```

Add the new endpoint directly below `list_history_entries` (i.e. immediately before the existing `delete_history_entry` endpoint):

```python
@router.post("/history-dictionary", response_model=HistoryEntryOut, status_code=201)
async def create_history_entry(
    body: HistoryEntryCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Create a new live history dictionary entry (Admin only)."""
    repo = DictionaryRepository(session)
    existing = await repo.find_matching_history_term(body.term)
    if existing:
        raise HTTPException(
            status_code=409,
            detail={
                "message": t("errors.history_entry_duplicate_term"),
                "existing_id": existing.id,
                "existing_term": existing.term,
            },
        )
    letter_group = body.term[0].upper()
    entry = await repo.create_history_dictionary_entry(
        term=body.term,
        transliteration=body.transliteration,
        definition=body.definition,
        letter_group=letter_group,
    )
    await session.commit()
    return entry
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest services/backend/tests/api/endpoints/history_dictionary_router_test.py -v`
Expected: all tests PASS (the 4 pre-existing plus the 3 new ones — 7 total).

- [ ] **Step 6: Commit**

```bash
git add services/backend/api/endpoints/history_dictionary_router.py \
  services/backend/locales/en.json services/backend/locales/ug.json \
  services/backend/tests/api/endpoints/history_dictionary_router_test.py
git commit -m "feat: add admin create endpoint for history dictionary entries"
```

---

## Task 2: `PATCH /api/history-dictionary/{entry_id}` — update endpoint

**Files:**
- Modify: `services/backend/api/endpoints/history_dictionary_router.py`
- Modify: `services/backend/locales/en.json`
- Modify: `services/backend/locales/ug.json`
- Test: `services/backend/tests/api/endpoints/history_dictionary_router_test.py`

**Interfaces:**
- Consumes: `DictionaryRepository.get_history_dictionary_by_id(entry_id: int) -> HistoryDictionary | None` and `DictionaryRepository.update_history_dictionary_entry(entry: HistoryDictionary, **fields: Any) -> HistoryDictionary` (both pre-existing, no changes). Everything imported in Task 1 (`DictionaryRepository`, `t`, `require_admin`, `HTTPException`) is already available in this file.
- Produces: Pydantic model `HistoryEntryUpdate` (fields: `transliteration: Optional[str] = None`, `definition: Optional[str] = None`) and route function `update_history_entry`, importable from `api.endpoints.history_dictionary_router` — Task 4 (frontend edit flow) calls `PATCH /api/history-dictionary/{id}`.

- [ ] **Step 1: Write the failing tests**

Add to `services/backend/tests/api/endpoints/history_dictionary_router_test.py`, after the Task 1 tests:

```python
@pytest.mark.asyncio
async def test_update_history_entry():
    setup_paths()
    from unittest.mock import patch
    from api.endpoints.history_dictionary_router import (
        update_history_entry,
        HistoryEntryUpdate,
    )

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    existing = MagicMock()
    existing.id = 5
    mock_repo.get_history_dictionary_by_id.return_value = existing
    updated = MagicMock()
    updated.id = 5
    updated.term = "كاسى"
    updated.transliteration = "Kaasi"
    updated.definition = "يېڭىلانغان ئېنىقلىما"
    updated.letter_group = "ك"
    mock_repo.update_history_dictionary_entry.return_value = updated

    with patch(
        "api.endpoints.history_dictionary_router.DictionaryRepository",
        return_value=mock_repo,
    ):
        result = await update_history_entry(
            entry_id=5,
            body=HistoryEntryUpdate(
                transliteration="Kaasi", definition="يېڭىلانغان ئېنىقلىما"
            ),
            session=mock_session,
            current_user=_mock_admin(),
        )

    assert result is updated
    mock_repo.get_history_dictionary_by_id.assert_called_once_with(5)
    mock_repo.update_history_dictionary_entry.assert_called_once_with(
        existing, transliteration="Kaasi", definition="يېڭىلانغان ئېنىقلىما"
    )
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_history_entry_not_found():
    setup_paths()
    from unittest.mock import patch
    from api.endpoints.history_dictionary_router import (
        update_history_entry,
        HistoryEntryUpdate,
    )
    from fastapi import HTTPException

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_history_dictionary_by_id.return_value = None

    with patch(
        "api.endpoints.history_dictionary_router.DictionaryRepository",
        return_value=mock_repo,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await update_history_entry(
                entry_id=999,
                body=HistoryEntryUpdate(definition="x"),
                session=mock_session,
                current_user=_mock_admin(),
            )

    assert exc_info.value.status_code == 404
    mock_repo.update_history_dictionary_entry.assert_not_called()
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_history_entry_partial_update_only_sends_provided_fields():
    setup_paths()
    from unittest.mock import patch
    from api.endpoints.history_dictionary_router import (
        update_history_entry,
        HistoryEntryUpdate,
    )

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    existing = MagicMock()
    existing.id = 5
    mock_repo.get_history_dictionary_by_id.return_value = existing
    mock_repo.update_history_dictionary_entry.return_value = existing

    with patch(
        "api.endpoints.history_dictionary_router.DictionaryRepository",
        return_value=mock_repo,
    ):
        await update_history_entry(
            entry_id=5,
            body=HistoryEntryUpdate(definition="only definition changed"),
            session=mock_session,
            current_user=_mock_admin(),
        )

    mock_repo.update_history_dictionary_entry.assert_called_once_with(
        existing, definition="only definition changed"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest services/backend/tests/api/endpoints/history_dictionary_router_test.py -v -k update_history_entry`
Expected: FAIL with `ImportError: cannot import name 'update_history_entry'` from `api.endpoints.history_dictionary_router`.

- [ ] **Step 3: Add the `errors.history_entry_not_found` locale key**

In `services/backend/locales/en.json`, inside `"errors"`, add:

```json
    "history_entry_not_found": "History dictionary entry not found",
```

In `services/backend/locales/ug.json`, inside `"errors"`, add:

```json
    "history_entry_not_found": "تارىخ لۇغىتى ئاتالغۇسى تېپىلمىدى",
```

- [ ] **Step 4: Implement the endpoint**

In `services/backend/api/endpoints/history_dictionary_router.py`, add this Pydantic model directly below `HistoryEntryCreate`:

```python
class HistoryEntryUpdate(BaseModel):
    transliteration: Optional[str] = None
    definition: Optional[str] = None
```

Add the new endpoint directly below `create_history_entry` (still before `delete_history_entry`):

```python
@router.patch("/history-dictionary/{entry_id}", response_model=HistoryEntryOut)
async def update_history_entry(
    entry_id: int,
    body: HistoryEntryUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_admin),
):
    """Update transliteration/definition of a live history dictionary entry (Admin only)."""
    repo = DictionaryRepository(session)
    entry = await repo.get_history_dictionary_by_id(entry_id)
    if entry is None:
        raise HTTPException(
            status_code=404, detail=t("errors.history_entry_not_found")
        )
    fields = body.model_dump(exclude_unset=True)
    updated = await repo.update_history_dictionary_entry(entry, **fields)
    await session.commit()
    return updated
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest services/backend/tests/api/endpoints/history_dictionary_router_test.py -v`
Expected: all tests PASS (10 total: 4 pre-existing + 3 from Task 1 + 3 from this task).

- [ ] **Step 6: Commit**

```bash
git add services/backend/api/endpoints/history_dictionary_router.py \
  services/backend/locales/en.json services/backend/locales/ug.json \
  services/backend/tests/api/endpoints/history_dictionary_router_test.py
git commit -m "feat: add admin update endpoint for history dictionary entries"
```

---

## Task 3: Frontend — "Add entry" modal

**Files:**
- Modify: `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`
- Test: `apps/frontend/src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`

**Interfaces:**
- Consumes: `POST /api/history-dictionary` (Task 1) via `authFetch` — body `{ term, transliteration, definition }`, success response has shape `HistoryEntry` (`{ id, term, transliteration?, definition?, letter_group }`), `409` response body `{ detail: { message, existing_id, existing_term } }`.
- Produces: local component state `isAddModalOpen`, `formTerm`, `formTransliteration`, `formDefinition`, `isSubmitting`, `duplicateError` and a `resetForm()` helper — Task 4 (edit flow) reuses this same modal and these same form-field state variables in edit mode.

- [ ] **Step 1: Write the failing test**

Add to `apps/frontend/src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`, after the existing `mockListResponses` function and before the `beforeEach` block, extend `mockListResponses` to also handle POST, and add new tests after the existing two tests:

Replace the existing `mockListResponses` function body with:

```tsx
function mockListResponses(writeResponse?: Response) {
  vi.mocked(authService.authFetch).mockImplementation(async (url: string, opts?: any) => {
    if (opts?.method === 'DELETE') return { ok: true } as Response;
    if (opts?.method === 'POST' || opts?.method === 'PATCH') {
      return writeResponse ?? ({ ok: true, json: async () => ({ id: 2, term: 'يېڭى سۆز', letter_group: 'ي' }) } as Response);
    }
    if (url.includes('/api/history-dictionary/stats')) {
      return { ok: true, json: async () => ({ total_entries: 1 }) } as Response;
    }
    if (url.includes('/api/history-dictionary?')) {
      return { ok: true, json: async () => [mockEntry] } as Response;
    }
    return { ok: true, json: async () => [] } as Response;
  });
}
```

(`writeResponse` covers both the `POST` create test's default success case and the `PATCH` edit test in Task 4 — both write operations share one override slot since no test needs to configure them differently in the same run.)

Add these two new tests at the end of the file:

```tsx
test('does not show an add button for non-admin users', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(false);
  mockListResponses();

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  expect(screen.queryByTitle('admin.historyDictionary.addEntry')).not.toBeInTheDocument();
});

test('admin can create a new entry via the add modal', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  mockListResponses();

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('admin.historyDictionary.addEntry'));

  fireEvent.change(screen.getByPlaceholderText('admin.historyDictionary.term'), {
    target: { value: 'يېڭى سۆز' },
  });

  fireEvent.click(screen.getByText('common.save'));

  await waitFor(() =>
    expect(authService.authFetch).toHaveBeenCalledWith(
      '/api/history-dictionary',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ term: 'يېڭى سۆز', transliteration: null, definition: null }),
      })
    )
  );

  await waitFor(() =>
    expect(screen.queryByPlaceholderText('admin.historyDictionary.term')).not.toBeInTheDocument()
  );
});

test('shows an inline error when the add modal gets a duplicate-term response', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  mockListResponses({
    ok: false,
    status: 409,
    json: async () => ({
      detail: { message: 'An entry for this term already exists', existing_id: 1, existing_term: 'تارىخ سۆزى' },
    }),
  } as Response);

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('admin.historyDictionary.addEntry'));
  fireEvent.change(screen.getByPlaceholderText('admin.historyDictionary.term'), {
    target: { value: 'تارىخ سۆزى' },
  });
  fireEvent.click(screen.getByText('common.save'));

  await screen.findByText('An entry for this term already exists');
  expect(screen.getByPlaceholderText('admin.historyDictionary.term')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/frontend/`): `npx vitest run src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`
Expected: FAIL — `screen.getByTitle('admin.historyDictionary.addEntry')` not found (no add button exists yet).

- [ ] **Step 3: Add i18n keys**

In `apps/frontend/src/locales/en.json`, inside the `admin.historyDictionary` block (currently at line 623-632), replace:

```json
    "historyDictionary": {
      "title": "History Dictionary",
      "searchPlaceholder": "Search history dictionary...",
      "totalEntries": "Total {{count}} entries",
      "entryNotFound": "No matching entries found.",
      "transliteration": "Romanization",
      "confirmDelete": "Are you sure you want to delete \"{{word}}\"?",
      "deleteSuccess": "Entry deleted.",
      "deleteError": "Failed to delete entry."
    },
```

with:

```json
    "historyDictionary": {
      "title": "History Dictionary",
      "searchPlaceholder": "Search history dictionary...",
      "totalEntries": "Total {{count}} entries",
      "entryNotFound": "No matching entries found.",
      "transliteration": "Romanization",
      "confirmDelete": "Are you sure you want to delete \"{{word}}\"?",
      "deleteSuccess": "Entry deleted.",
      "deleteError": "Failed to delete entry.",
      "addEntry": "Add entry",
      "editEntry": "Edit entry",
      "term": "Term",
      "definition": "Definition",
      "createSuccess": "Entry created.",
      "createError": "Failed to create entry.",
      "updateSuccess": "Entry updated.",
      "updateError": "Failed to update entry."
    },
```

In `apps/frontend/src/locales/ug.json`, inside the `admin.historyDictionary` block (currently at line 626-635), replace:

```json
    "historyDictionary": {
      "title": "تارىخ لۇغىتى",
      "searchPlaceholder": "تارىخ لۇغىتىدىن ئىزدەڭ...",
      "totalEntries": "جەمئىي {{count}} ئاتالغۇ",
      "entryNotFound": "ماس كېلىدىغان ئاتالغۇ تېپىلمىدى.",
      "transliteration": "يەشمىسى",
      "confirmDelete": "«{{word}}» دېگەن ئاتالغۇنى لۇغەتتىن راستىنلا ئۆچۈرەمسىز؟",
      "deleteSuccess": "ئاتالغۇ لۇغەتتىن مۇۋەپپەقىيەتلىك ئۆچۈرۈلدى.",
      "deleteError": "ئاتالغۇنى لۇغەتتىن ئۆچۈرەلمىدى."
    },
```

with:

```json
    "historyDictionary": {
      "title": "تارىخ لۇغىتى",
      "searchPlaceholder": "تارىخ لۇغىتىدىن ئىزدەڭ...",
      "totalEntries": "جەمئىي {{count}} ئاتالغۇ",
      "entryNotFound": "ماس كېلىدىغان ئاتالغۇ تېپىلمىدى.",
      "transliteration": "يەشمىسى",
      "confirmDelete": "«{{word}}» دېگەن ئاتالغۇنى لۇغەتتىن راستىنلا ئۆچۈرەمسىز؟",
      "deleteSuccess": "ئاتالغۇ لۇغەتتىن مۇۋەپپەقىيەتلىك ئۆچۈرۈلدى.",
      "deleteError": "ئاتالغۇنى لۇغەتتىن ئۆچۈرەلمىدى.",
      "addEntry": "يېڭى ئاتالغۇ قوشۇش",
      "editEntry": "ئاتالغۇنى تەھرىرلەش",
      "term": "ئاتالغۇ",
      "definition": "ئېنىقلىما",
      "createSuccess": "ئاتالغۇ مۇۋەپپەقىيەتلىك قوشۇلدى.",
      "createError": "ئاتالغۇ قوشالمىدى.",
      "updateSuccess": "ئاتالغۇ مۇۋەپپەقىيەتلىك يېڭىلاندى.",
      "updateError": "ئاتالغۇنى يېڭىلىيالمىدى."
    },
```

- [ ] **Step 4: Implement the add button and modal**

In `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`:

Update the `lucide-react` import (line 5-13) to add `Plus` and `Edit2`:

```tsx
import {
  AlertCircle,
  Edit2,
  Hash,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
```

Add `createPortal` to the React import block, replacing line 14:

```tsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
```

Add new state right after the existing `const inputRef = useRef<HTMLInputElement>(null);` line (line 58):

```tsx
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<HistoryEntry | null>(null);
  const [formTerm, setFormTerm] = useState('');
  const [formTransliteration, setFormTransliteration] = useState('');
  const [formDefinition, setFormDefinition] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);
```

Add these handlers right after the existing `handleDeleteEntry` function (after its closing `};`, before the `return (`):

```tsx
  const openAddModal = () => {
    setEditingEntry(null);
    setFormTerm('');
    setFormTransliteration('');
    setFormDefinition('');
    setDuplicateError(null);
    setIsAddModalOpen(true);
  };

  const closeModal = () => {
    setIsAddModalOpen(false);
    setEditingEntry(null);
    setDuplicateError(null);
  };

  const refreshCurrentView = async () => {
    if (searchQuery.trim()) {
      await searchEntries(searchQuery);
    } else {
      setAllEntries([]);
      setPage(0);
      setHasMore(true);
      await fetchEntries(0, true, activeGroup);
    }
    await fetchStats();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTerm.trim()) return;
    setIsSubmitting(true);
    setDuplicateError(null);
    try {
      const isEdit = !!editingEntry;
      const url = isEdit ? `/api/history-dictionary/${editingEntry!.id}` : '/api/history-dictionary';
      const method = isEdit ? 'PATCH' : 'POST';
      const body = isEdit
        ? { transliteration: formTransliteration.trim() || null, definition: formDefinition.trim() || null }
        : {
            term: formTerm.trim(),
            transliteration: formTransliteration.trim() || null,
            definition: formDefinition.trim() || null,
          };

      const resp = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        if (resp.status === 409) {
          const errorData = await resp.json();
          setDuplicateError(errorData?.detail?.message || t('admin.historyDictionary.createError'));
          return;
        }
        throw new Error(isEdit ? 'Failed to update entry' : 'Failed to create entry');
      }

      closeModal();
      await refreshCurrentView();
      addNotification(
        t(isEdit ? 'admin.historyDictionary.updateSuccess' : 'admin.historyDictionary.createSuccess'),
        'success',
      );
    } catch (e) {
      console.error('Failed to save history dictionary entry', e);
      addNotification(
        t(editingEntry ? 'admin.historyDictionary.updateError' : 'admin.historyDictionary.createError'),
        'error',
      );
    } finally {
      setIsSubmitting(false);
    }
  };
```

Add the add button inside the existing "Search + Stats row" `<div>` (line 190-231), right before the closing `</div>` of that row (i.e. after the `{stats && (...)}` block, still inside the outer flex row):

```tsx
        {isAdmin && (
          <button
            onClick={openAddModal}
            title={t('admin.historyDictionary.addEntry')}
            className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 shrink-0"
          >
            <Plus size={14} className="md:w-4 md:h-4" />
            <span className="text-xs md:text-sm font-normal">{t('admin.historyDictionary.addEntry')}</span>
          </button>
        )}
```

Wrap the component's existing return value in a fragment and add the modal, by replacing the final lines of the component (from the closing `</div>` of `{/* Entry list */}`'s container through the end of the file):

```tsx
      </div>
    </div>

    {isAddModalOpen && createPortal(
      <div className="fixed inset-0 z-[200] flex items-center justify-center p-4" dir="rtl" lang="ug">
        <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-md animate-fade-in" onClick={closeModal} />
        <div className="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-[32px] overflow-hidden shadow-2xl animate-scale-up border border-[#0369a1]/10 dark:border-slate-800 flex flex-col">
          <div className="px-8 py-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-[#0369a1]/5 dark:bg-[#38bdf8]/5">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
                {editingEntry ? <Edit2 size={20} /> : <Plus size={20} />}
              </div>
              <h3 className="text-xl font-bold text-[#1a1a1a] dark:text-slate-100">
                {editingEntry ? t('admin.historyDictionary.editEntry') : t('admin.historyDictionary.addEntry')}
              </h3>
            </div>
            <button
              onClick={closeModal}
              className="p-2 hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-[#1a1a1a] dark:hover:text-slate-100 rounded-xl transition-all"
            >
              <X size={20} strokeWidth={2.5} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="p-8 space-y-6 overflow-y-auto max-h-[70vh]">
            <div className="space-y-2">
              <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1">
                {t('admin.historyDictionary.term')} <span className="text-red-500">*</span>
              </label>
              <input
                autoFocus
                required
                disabled={!!editingEntry}
                type="text"
                dir="rtl"
                value={formTerm}
                onChange={(e) => setFormTerm(e.target.value)}
                className={`w-full px-5 py-3.5 border-2 rounded-2xl outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text text-xl ${
                  editingEntry
                    ? 'bg-slate-50 dark:bg-slate-800/50 border-slate-100 dark:border-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed'
                    : 'bg-white dark:bg-slate-950 border-slate-100 dark:border-slate-800 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500'
                }`}
                placeholder={t('admin.historyDictionary.term')}
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1">
                {t('admin.historyDictionary.transliteration')}
              </label>
              <input
                type="text"
                dir="ltr"
                value={formTransliteration}
                onChange={(e) => setFormTransliteration(e.target.value)}
                className="w-full px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all font-mono text-lg"
                placeholder={t('admin.historyDictionary.transliteration')}
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1">
                {t('admin.historyDictionary.definition')}
              </label>
              <textarea
                rows={4}
                dir="rtl"
                value={formDefinition}
                onChange={(e) => setFormDefinition(e.target.value)}
                className="w-full px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text text-base resize-none"
                placeholder={t('admin.historyDictionary.definition')}
              />
            </div>

            {duplicateError && (
              <div className="px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400 text-sm">
                {duplicateError}
              </div>
            )}
          </form>

          <div className="px-8 py-6 bg-slate-50 dark:bg-slate-950/40 border-t border-slate-100 dark:border-slate-800 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={closeModal}
              className="px-6 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all font-bold uppercase tracking-widest text-xs"
            >
              {t('common.cancel')}
            </button>
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || !formTerm.trim()}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-8 py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all active:scale-95 disabled:opacity-50 font-bold uppercase tracking-widest text-xs"
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : t('common.save')}
            </button>
          </div>
        </div>
      </div>,
      document.body
    )}
    </>
  );
};
```

And update the component's opening `return (` (currently `return (` followed directly by the outer `<div className="space-y-6 ...`) to wrap in a fragment:

```tsx
  return (
    <>
    <div className="space-y-6 md:space-y-8 animate-fade-in pb-20" dir="rtl" lang="ug">
```

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `apps/frontend/`): `npx vitest run src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`
Expected: all tests PASS (2 pre-existing + 3 new = 5 total).

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx \
  apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json \
  apps/frontend/src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx
git commit -m "feat: add create-entry modal to history dictionary admin panel"
```

---

## Task 4: Frontend — "Edit entry" flow

**Files:**
- Modify: `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`
- Test: `apps/frontend/src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`

**Interfaces:**
- Consumes: `PATCH /api/history-dictionary/{id}` (Task 2), and the modal/form state and `handleSubmit`/`closeModal` from Task 3 (already branches on `editingEntry` — no changes needed there). Consumes the `Edit2` icon already imported in Task 3.
- Produces: `openEditModal(entry: HistoryEntry)` function, and an edit button rendered per row.

- [ ] **Step 1: Write the failing test**

Add to `apps/frontend/src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`, at the end of the file:

```tsx
test('admin can edit an existing entry via the edit modal', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  mockListResponses({
    ok: true,
    json: async () => ({ id: 1, term: 'تارىخ سۆزى', transliteration: 'Tarikh sozi', definition: 'يېڭىلانغان', letter_group: 'ت' }),
  } as Response);

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('common.edit'));

  const termInput = screen.getByPlaceholderText('admin.historyDictionary.term') as HTMLInputElement;
  expect(termInput.value).toBe('تارىخ سۆزى');
  expect(termInput).toBeDisabled();

  const definitionInput = screen.getByPlaceholderText('admin.historyDictionary.definition');
  fireEvent.change(definitionInput, { target: { value: 'يېڭىلانغان' } });
  fireEvent.click(screen.getByText('common.save'));

  await waitFor(() =>
    expect(authService.authFetch).toHaveBeenCalledWith(
      '/api/history-dictionary/1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ transliteration: null, definition: 'يېڭىلانغان' }),
      })
    )
  );
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/frontend/`): `npx vitest run src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`
Expected: FAIL — `screen.getByTitle('common.edit')` not found (no edit button exists yet).

- [ ] **Step 3: Implement the edit button and pre-fill logic**

In `apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx`, add `openEditModal` right after `openAddModal` (defined in Task 3):

```tsx
  const openEditModal = (entry: HistoryEntry) => {
    setEditingEntry(entry);
    setFormTerm(entry.term);
    setFormTransliteration(entry.transliteration || '');
    setFormDefinition(entry.definition || '');
    setDuplicateError(null);
    setIsAddModalOpen(true);
  };
```

In the entry row rendering (inside `{isAdmin && (...)}` that currently renders only the delete `<Trash2>` button, around what was line 324-332), add the edit button before the delete button:

```tsx
                    {isAdmin && (
                      <div className="flex items-center gap-1.5 md:gap-2 shrink-0">
                        <button
                          onClick={() => openEditModal(entry)}
                          className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 transition-all"
                          title={t('common.edit')}
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          onClick={() => handleDeleteEntry(entry)}
                          className="p-2 bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 rounded-xl hover:bg-red-500 dark:hover:bg-red-600 hover:text-white transition-all"
                          title={t('common.delete')}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    )}
```

(This replaces the existing single-button `{isAdmin && (<button onClick={() => handleDeleteEntry(entry)} ...><Trash2 .../></button>)}` block with the two-button version above — the delete button's `onClick`/`title`/icon stay exactly the same, just now wrapped alongside the new edit button.)

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `apps/frontend/`): `npx vitest run src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx`
Expected: all tests PASS (5 pre-existing + 1 new = 6 total).

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/admin/dictionary/HistoryDictionaryPanel.tsx \
  apps/frontend/src/tests/components/admin/dictionary/HistoryDictionaryPanel.test.tsx
git commit -m "feat: add edit-entry flow to history dictionary admin panel"
```

---

## Manual Verification (no commit)

- [ ] Run `./deploy/local/rebuild-and-restart.sh all` (or `backend` + `frontend` if `worker`/DB are already up to date).
- [ ] Log in as a user with `role = admin`. Open the History Dictionary tab (Dictionary page → History tab).
- [ ] Confirm the "Add entry" button is visible; click it, fill in a term, transliteration, and definition, save — confirm the new entry appears in the list and a success toast shows.
- [ ] Search for that term via the search box — confirm it's findable (exercises `GET /api/history-dictionary/search`, unchanged but validates the new row round-trips correctly).
- [ ] Click the edit button on that entry, change the definition, save — confirm the term field was disabled during edit, the update persists, and a success toast shows.
- [ ] Attempt to add a new entry with the exact same term as an existing one — confirm a 409 inline error appears in the modal (not a toast) and the modal stays open.
- [ ] Log in as (or switch to) a non-admin user — confirm the Add and Edit buttons are both absent, and only the read-only list is visible.
