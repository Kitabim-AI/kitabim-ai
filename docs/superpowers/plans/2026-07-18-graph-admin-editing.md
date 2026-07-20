# Admin Graph Editing (Delete Relationship & Merge Entities) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins delete a specific relationship between two graph entities and merge two duplicate entities, directly from the existing public `GraphView.tsx`.

**Architecture:** Add a new `delete_relationship` method to `GraphRepository` plus a new admin-gated `POST /api/books/graph/relationship/delete` endpoint. Fix the existing (already-tested but never wired-up) `POST /api/books/graph/merge` endpoint's request schema to accept camelCase JSON, then wire both endpoints into `GraphView.tsx` behind `useIsAdmin()`, using the shared confirm `Modal` for delete and a small self-contained overlay for the merge pick/confirm flow (which needs a two-way "which node survives" toggle the shared Modal can't express).

**Tech Stack:** FastAPI + Pydantic v2 (backend), async Neo4j driver + Cypher (graph repo), React + TypeScript + `react-force-graph-2d` + Tailwind (frontend).

## Global Constraints

- No `print()` — use `log_json` / `logger` (backend already imports both in `books_router.py`).
- No hardcoded user-visible strings anywhere (backend `t("errors.key")`, frontend `t('namespace.key')`) — every new string needs an `en.json` **and** `ug.json` entry (frontend) or `en.json`/`ug.json` entry under `services/backend/locales/` (backend).
- All new/changed Pydantic request schemas use `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` so the frontend sends/receives camelCase.
- New write endpoints require `Depends(require_admin)` — never skip auth.
- Relationship deletion targets `(source_name, target_name, rel_type)` and removes **all** book-scoped duplicate edges of that triple (confirmed design decision — do not add per-book targeting).
- Merge reuses the existing `merge_entities` Cypher/repo logic unchanged — do not rewrite it.
- Frontend refresh strategy after a mutation is a full `fetchGraphData(searchQuery)` refetch, not optimistic local splicing (confirmed design decision).

---

### Task 1: `GraphRepository.delete_relationship`

**Files:**
- Modify: `packages/backend-core/app/db/repositories/graph_repository.py` (insert new method between `delete_book_graph`, which ends at line 195, and `query_subgraph`, which starts at line 197)
- Test: `packages/backend-core/tests/app/db/graph_repository_test.py` (append new tests at the end of the file, after `test_graph_repository_query_paths_success`)

**Interfaces:**
- Produces: `async def delete_relationship(self, source_name: str, target_name: str, rel_type: str) -> bool` on `GraphRepository` — raises `ValueError` if no matching edge exists, else deletes every `RELATED_TO` edge matching the triple (across all `book_id`s) and returns `True`. Consumed by Task 2's endpoint.

- [ ] **Step 1: Write the failing tests**

Append to `packages/backend-core/tests/app/db/graph_repository_test.py`:

```python
@pytest.mark.asyncio
async def test_graph_repository_delete_relationship_success():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"deleted": 2}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        success = await repo.delete_relationship("A", "B", "SON_OF")

        assert success is True
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "DELETE r" in call_args[0]
        assert "RELATED_TO {type: $rel_type}" in call_args[0]
        assert call_kwargs["source_name"] == "A"
        assert call_kwargs["target_name"] == "B"
        assert call_kwargs["rel_type"] == "SON_OF"


@pytest.mark.asyncio
async def test_graph_repository_delete_relationship_not_found():
    mock_result = AsyncMock()
    mock_result.data.return_value = [{"deleted": 0}]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = MagicMock()
    mock_driver.session.return_value = mock_session

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        with pytest.raises(ValueError) as excinfo:
            await repo.delete_relationship("A", "B", "SON_OF")
        assert "No 'SON_OF' relationship found between 'A' and 'B'." in str(
            excinfo.value
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/db/graph_repository_test.py -k delete_relationship -v`
Expected: FAIL with `AttributeError: 'GraphRepository' object has no attribute 'delete_relationship'`

- [ ] **Step 3: Implement `delete_relationship`**

Insert into `packages/backend-core/app/db/repositories/graph_repository.py`, immediately after `delete_book_graph` (line 195) and before `query_subgraph` (line 197):

```python
    async def delete_relationship(
        self, source_name: str, target_name: str, rel_type: str
    ) -> bool:
        """Delete every RELATED_TO edge of a given type between two entities.

        Matches on (source_name, target_name, rel_type) and removes all matching
        edges, including duplicates from different books (book_id is not part of
        the match). Raises ValueError if no matching edge exists.
        """
        source_norm = unicodedata.normalize("NFC", source_name)
        target_norm = unicodedata.normalize("NFC", target_name)

        query = """
        MATCH (a:Entity {name: $source_name})-[r:RELATED_TO {type: $rel_type}]->(b:Entity {name: $target_name})
        DELETE r
        RETURN count(r) AS deleted
        """
        async with self._driver.session() as session:
            result = await session.run(
                query,
                source_name=source_norm,
                target_name=target_norm,
                rel_type=rel_type,
            )
            records = await result.data()

        deleted = records[0]["deleted"] if records else 0
        if deleted == 0:
            raise ValueError(
                f"No '{rel_type}' relationship found between '{source_name}' and '{target_name}'."
            )
        return True
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/db/graph_repository_test.py -k delete_relationship -v`
Expected: `2 passed`

- [ ] **Step 5: Run the full repository test file to check for regressions**

Run: `cd packages/backend-core && python -m pytest tests/app/db/graph_repository_test.py -v`
Expected: all tests pass (previous count + 2)

- [ ] **Step 6: Commit**

```bash
git add packages/backend-core/app/db/repositories/graph_repository.py packages/backend-core/tests/app/db/graph_repository_test.py
git commit -m "feat: add GraphRepository.delete_relationship for admin graph edits"
```

---

### Task 2: `POST /api/books/graph/relationship/delete` endpoint

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py` (add schema + endpoint after `merge_graph_entities`, which ends at line 1022)
- Modify: `services/backend/locales/en.json` (add `errors.relationship_not_found` after line 35)
- Modify: `services/backend/locales/ug.json` (add `errors.relationship_not_found` after line 35)
- Test: `services/backend/tests/api/endpoints/books_router_test.py` (append after `test_merge_graph_entities_endpoint`, which ends at line 171)

**Interfaces:**
- Consumes: `GraphRepository.delete_relationship(source_name, target_name, rel_type)` from Task 1.
- Produces: `DeleteRelationshipRequest` Pydantic model (fields `source_name`, `target_name`, `rel_type`; accepts JSON as `sourceName`/`targetName`/`relType`) and the route function `delete_graph_relationship`. Consumed by Task 4's frontend call to `/api/books/graph/relationship/delete`.

- [ ] **Step 1: Add the i18n key (both locales)**

In `services/backend/locales/en.json`, after line 35 (`"book_or_page_not_found": "Book or page not found",`), add:

```json
    "relationship_not_found": "Relationship not found",
```

In `services/backend/locales/ug.json`, after line 35 (`"book_or_page_not_found": "كىتاب ياكى بەت تېپىلمىدى",`), add:

```json
    "relationship_not_found": "مۇناسىۋەت تېپىلمىدى",
```

- [ ] **Step 2: Write the failing endpoint tests**

Append to `services/backend/tests/api/endpoints/books_router_test.py` (mirrors `test_merge_graph_entities_endpoint` at lines 149-171 exactly):

```python
@pytest.mark.asyncio
async def test_delete_graph_relationship_endpoint():
    setup_paths()
    from api.endpoints.books_router import (
        delete_graph_relationship,
        DeleteRelationshipRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()

    mock_request = DeleteRelationshipRequest(
        source_name="A", target_name="B", rel_type="SON_OF"
    )

    mock_repo = MagicMock()
    mock_repo.delete_relationship = AsyncMock()

    with patch(
        "app.db.repositories.graph_repository.GraphRepository", return_value=mock_repo
    ):
        response = await delete_graph_relationship(
            request=mock_request, current_user=mock_user, session=mock_session
        )

    assert response["status"] == "success"
    mock_repo.delete_relationship.assert_called_once_with("A", "B", "SON_OF")


@pytest.mark.asyncio
async def test_delete_graph_relationship_endpoint_not_found():
    setup_paths()
    from api.endpoints.books_router import (
        delete_graph_relationship,
        DeleteRelationshipRequest,
    )

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_request = DeleteRelationshipRequest(
        source_name="A", target_name="B", rel_type="SON_OF"
    )

    mock_repo = MagicMock()
    mock_repo.delete_relationship = AsyncMock(side_effect=ValueError("not found"))

    with patch(
        "app.db.repositories.graph_repository.GraphRepository", return_value=mock_repo
    ):
        with pytest.raises(HTTPException) as excinfo:
            await delete_graph_relationship(
                request=mock_request, current_user=mock_user, session=mock_session
            )
    assert excinfo.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_relationship_request_accepts_camel_case():
    setup_paths()
    from api.endpoints.books_router import DeleteRelationshipRequest

    req = DeleteRelationshipRequest.model_validate(
        {"sourceName": "A", "targetName": "B", "relType": "SON_OF"}
    )
    assert req.source_name == "A"
    assert req.target_name == "B"
    assert req.rel_type == "SON_OF"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k delete_relationship -v`
Expected: FAIL with `ImportError: cannot import name 'delete_graph_relationship'`

- [ ] **Step 4: Add the `to_camel` import**

In `services/backend/api/endpoints/books_router.py`, change line 41 from:

```python
from app.models.schemas import Book, PaginatedBooks, ExtractionResult
```

to:

```python
from app.models.schemas import Book, PaginatedBooks, ExtractionResult, to_camel
```

- [ ] **Step 5: Add the schema and endpoint**

In `services/backend/api/endpoints/books_router.py`, after the existing `merge_graph_entities` endpoint (which ends at line 1022 with the closing `}`), add:

```python
class DeleteRelationshipRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    source_name: str
    target_name: str
    rel_type: str


@router.post("/graph/relationship/delete")
async def delete_graph_relationship(
    request: DeleteRelationshipRequest,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Delete a relationship between two knowledge graph entities (admin only)."""
    from app.db.repositories.graph_repository import GraphRepository

    graph_repo = GraphRepository()
    try:
        await graph_repo.delete_relationship(
            request.source_name, request.target_name, request.rel_type
        )
    except ValueError:
        raise HTTPException(
            status_code=400, detail=t("errors.relationship_not_found")
        )
    except Exception as exc:
        logger.error(f"Failed to delete relationship: {exc}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during relationship deletion.",
        )

    return {
        "status": "success",
        "message": f"Deleted relationship '{request.rel_type}' between '{request.source_name}' and '{request.target_name}'",
    }
```

Also change line 991's `from pydantic import BaseModel` to `from pydantic import BaseModel, ConfigDict` (needed by both this schema and Task 3's fix).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k "delete_relationship or delete_graph_relationship" -v`
Expected: `3 passed`

- [ ] **Step 7: Run the full endpoint test file to check for regressions**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -v`
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/locales/en.json services/backend/locales/ug.json services/backend/tests/api/endpoints/books_router_test.py
git commit -m "feat: add admin endpoint to delete a graph relationship"
```

---

### Task 3: Fix `MergeEntitiesRequest` to accept camelCase

**Files:**
- Modify: `services/backend/api/endpoints/books_router.py:994-996`
- Test: `services/backend/tests/api/endpoints/books_router_test.py` (append one new test; verify the existing `test_merge_graph_entities_endpoint` still passes unchanged)

**Interfaces:**
- Consumes: `to_camel` import added in Task 2 Step 4.
- Produces: `MergeEntitiesRequest` now accepts both `{"keepName": ..., "removeName": ...}` (camelCase, what the frontend will send in Task 5) and `{"keep_name": ..., "remove_name": ...}` (snake_case, what the existing test and any direct Python construction use) via `populate_by_name=True`.

This is a pure additive fix — `MergeEntitiesRequest` currently has no `alias_generator`, so a frontend caller would have to send snake_case JSON, which breaks the codebase's camelCase convention (`.claude/skills/api-designer.md`) and was never actually exercised end-to-end (no existing frontend caller). Adding `alias_generator=to_camel, populate_by_name=True` is non-breaking: `populate_by_name=True` keeps the snake_case field names valid for direct Python construction, so `test_merge_graph_entities_endpoint`'s `MergeEntitiesRequest(keep_name="A", remove_name="B")` at line 157 keeps working unchanged.

- [ ] **Step 1: Write the failing test for camelCase input**

Append to `services/backend/tests/api/endpoints/books_router_test.py`:

```python
@pytest.mark.asyncio
async def test_merge_entities_request_accepts_camel_case():
    setup_paths()
    from api.endpoints.books_router import MergeEntitiesRequest

    req = MergeEntitiesRequest.model_validate(
        {"keepName": "KeepName", "removeName": "RemoveName"}
    )
    assert req.keep_name == "KeepName"
    assert req.remove_name == "RemoveName"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k test_merge_entities_request_accepts_camel_case -v`
Expected: FAIL with a Pydantic validation error (`keepName`/`removeName` not recognized — the model currently only accepts `keep_name`/`remove_name`)

- [ ] **Step 3: Fix `MergeEntitiesRequest`**

In `services/backend/api/endpoints/books_router.py`, change lines 994-996 from:

```python
class MergeEntitiesRequest(BaseModel):
    keep_name: str
    remove_name: str
```

to:

```python
class MergeEntitiesRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    keep_name: str
    remove_name: str
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -k "merge_entities or merge_graph_entities" -v`
Expected: `2 passed` (the new camelCase test, plus the existing `test_merge_graph_entities_endpoint` still passing unchanged)

- [ ] **Step 5: Run the full endpoint test file to check for regressions**

Run: `cd services/backend && python -m pytest tests/api/endpoints/books_router_test.py -v`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add services/backend/api/endpoints/books_router.py services/backend/tests/api/endpoints/books_router_test.py
git commit -m "fix: accept camelCase body on POST /graph/merge"
```

---

### Task 4: Frontend — delete relationship from the connections list

**Files:**
- Modify: `apps/frontend/src/components/graph/GraphView.tsx`
- Modify: `apps/frontend/src/locales/en.json` (add `graph.admin.*` keys inside the `graph` block, after `nodePanel`, i.e. after line 866)
- Modify: `apps/frontend/src/locales/ug.json` (same, after line 886)

**Interfaces:**
- Consumes: `POST /api/books/graph/relationship/delete` from Task 2 (body `{ sourceName, targetName, relType }`).
- Produces: nothing consumed by later tasks (Task 5 is independent), but introduces the `isAdmin`, `authFetch`, `useAppContext`/`setModal`, `useNotification`/`addNotification` imports and wiring that Task 5 reuses.

There is no automated test suite for `GraphView.tsx`; verification for this task is manual via the local dev server (see Step 7).

- [ ] **Step 1: Add the i18n keys (both locales)**

In `apps/frontend/src/locales/en.json`, `nodePanel` (lines 857-866) is currently the last key in the `graph` block, so its closing brace at line 866 has no trailing comma:

```json
866	    }
867	  },
```

Change line 866 from `    }` to `    },` and insert a new `admin` sibling key right after it (still before line 867's `  },` that closes `graph`):

```json
    "admin": {
      "deleteRelationshipTitle": "Delete Relationship",
      "deleteRelationshipMessage": "Delete the \"{relType}\" relationship between \"{sourceName}\" and \"{targetName}\"? This removes it from every book it was extracted from.",
      "deleteRelationshipSuccess": "Relationship deleted.",
      "deleteRelationshipError": "Failed to delete relationship.",
      "mergeStart": "Merge into another entity...",
      "mergePickTarget": "Click another node to merge with \"{name}\" (Esc to cancel)",
      "mergeConfirmMessage": "Choose which entity should survive the merge. The other entity's relationships will be moved over and it will be deleted.",
      "mergeKeep": "Keep",
      "mergeConfirmButton": "Merge",
      "mergeSuccess": "Entities merged.",
      "mergeError": "Failed to merge entities."
    }
```

In `apps/frontend/src/locales/ug.json`, `nodePanel` (lines 877-886) is likewise the last key in its `graph` block. Change its closing brace at line 886 from `    }` to `    },`, then insert the same sibling key in the same position:

```json
    "admin": {
      "deleteRelationshipTitle": "مۇناسىۋەتنى ئۆچۈرۈش",
      "deleteRelationshipMessage": "«{sourceName}» بىلەن «{targetName}» ئارىسىدىكى «{relType}» مۇناسىۋىتىنى ئۆچۈرەمسىز؟ بۇ ئۇنى بارلىق كىتابلاردىن ئۆچۈرىدۇ.",
      "deleteRelationshipSuccess": "مۇناسىۋەت ئۆچۈرۈلدى.",
      "deleteRelationshipError": "مۇناسىۋەتنى ئۆچۈرەلمىدى.",
      "mergeStart": "باشقا سۆزلۈك بىلەن بىرلەشتۈرۈش...",
      "mergePickTarget": "«{name}» بىلەن بىرلەشتۈرۈش ئۈچۈن باشقا كۇنۇپكىنى چېكىڭ (Esc ئارقىلىق بىكار قىلىڭ)",
      "mergeConfirmMessage": "بىرلەشتۈرگەندە قايسى سۆزلۈك ساقلىنىدىغانلىقىنى تاللاڭ. يەنە بىرىنىڭ مۇناسىۋەتلىرى كۆچۈرۈلۈپ، ئۆزى ئۆچۈرۈلىدۇ.",
      "mergeKeep": "ساقلا",
      "mergeConfirmButton": "بىرلەشتۈر",
      "mergeSuccess": "سۆزلۈكلەر بىرلەشتۈرۈلدى.",
      "mergeError": "بىرلەشتۈرەلمىدى."
    }
```

- [ ] **Step 2: Add new imports**

In `apps/frontend/src/components/graph/GraphView.tsx`, change lines 1-5 from:

```tsx
import React, { useEffect, useState, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useI18n } from '../../i18n/I18nContext';
import { useTheme } from '../../context/ThemeContext';
import { Search, Loader2, ZoomIn, ZoomOut, Maximize, Minimize, Maximize2, Network, BookOpen, MapPin, User, Calendar, HelpCircle, X, SlidersHorizontal, Building, Clock, Lightbulb, ChevronDown } from 'lucide-react';
```

to:

```tsx
import React, { useEffect, useState, useRef, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useI18n } from '../../i18n/I18nContext';
import { useTheme } from '../../context/ThemeContext';
import { useAppContext } from '../../context/AppContext';
import { useNotification } from '../../context/NotificationContext';
import { useIsAdmin } from '../../hooks/useAuth';
import { authFetch } from '../../services/authService';
import { Search, Loader2, ZoomIn, ZoomOut, Maximize, Minimize, Maximize2, Network, BookOpen, MapPin, User, Calendar, HelpCircle, X, SlidersHorizontal, Building, Clock, Lightbulb, ChevronDown, Trash2, GitMerge } from 'lucide-react';
```

- [ ] **Step 3: Add new hooks/state at the top of the component**

In `apps/frontend/src/components/graph/GraphView.tsx`, change lines 56-60 from:

```tsx
export const GraphView: React.FC = () => {
  const { t, language } = useI18n();
  const { theme } = useTheme();
  const isThemeDark = theme === 'dark';
  const [rawGraphData, setRawGraphData] = useState<GraphData>({ nodes: [], links: [] });
```

to:

```tsx
export const GraphView: React.FC = () => {
  const { t, language } = useI18n();
  const { theme } = useTheme();
  const isThemeDark = theme === 'dark';
  const isAdmin = useIsAdmin();
  const { modal, setModal } = useAppContext();
  const { addNotification } = useNotification();
  const [rawGraphData, setRawGraphData] = useState<GraphData>({ nodes: [], links: [] });
```

- [ ] **Step 4: Add the delete-relationship handler**

In `apps/frontend/src/components/graph/GraphView.tsx`, immediately after the `nodeConnections` `useEffect` (ends at line 468, i.e. right after `}, [selectedNode, filteredData]);`), add:

```tsx
  const handleDeleteRelationship = (conn: any) => {
    if (!selectedNode) return;
    const isOutgoing = conn.direction === 'outgoing';
    const sourceName = isOutgoing ? selectedNode.id : conn.node.id;
    const targetName = isOutgoing ? conn.node.id : selectedNode.id;
    const relType = conn.label;

    setModal({
      isOpen: true,
      title: t('graph.admin.deleteRelationshipTitle'),
      message: t('graph.admin.deleteRelationshipMessage', { relType, sourceName, targetName }),
      type: 'confirm',
      destructive: true,
      confirmText: t('common.delete'),
      onConfirm: async () => {
        try {
          const res = await authFetch('/api/books/graph/relationship/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sourceName, targetName, relType }),
          });
          if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(body.detail || t('graph.admin.deleteRelationshipError'));
          }
          setModal({ isOpen: false, title: '', message: '', type: 'alert' });
          addNotification(t('graph.admin.deleteRelationshipSuccess'), 'success');
          fetchGraphData(searchQuery);
        } catch (err: any) {
          setModal({
            isOpen: true,
            title: t('common.error'),
            message: err.message || t('graph.admin.deleteRelationshipError'),
            type: 'alert',
          });
        }
      },
    });
  };
```

- [ ] **Step 5: Add the delete icon button to each connection row**

In `apps/frontend/src/components/graph/GraphView.tsx`, change the connection row header (lines 569-575) from:

```tsx
                <div className="flex justify-between items-center mb-1">
                  <span className={`text-xs font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{conn.node.label}</span>
                  <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-200 text-slate-600'
                    }`}>
                    {conn.direction === 'outgoing' ? '←' : '→'} {conn.label}
                  </span>
                </div>
```

to:

```tsx
                <div className="flex justify-between items-center mb-1">
                  <span className={`text-xs font-semibold ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{conn.node.label}</span>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded ${isDark ? 'bg-slate-800 text-slate-400' : 'bg-slate-200 text-slate-600'
                      }`}>
                      {conn.direction === 'outgoing' ? '←' : '→'} {conn.label}
                    </span>
                    {isAdmin && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); handleDeleteRelationship(conn); }}
                        title={t('graph.admin.deleteRelationshipTitle')}
                        className="p-1 text-slate-400 hover:text-red-500 rounded-md transition-all active:scale-95"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>
```

Note: the outer connection card (lines 561-567) has `onClick={() => setSelectedNode(conn.node)}` — `e.stopPropagation()` in the new button's `onClick` is required so clicking delete doesn't also re-select the neighboring node.

- [ ] **Step 6: Verify the file still typechecks**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: no new errors introduced by this file (pre-existing unrelated errors, if any, are out of scope)

- [ ] **Step 7: Manual verification via the dev server**

Run: `./deploy/local/rebuild-and-restart.sh frontend` (or the project's normal frontend dev workflow), then in a browser logged in as an admin user:
1. Open the Graph view, select a node with at least one connection.
2. Confirm a small trash icon appears next to each connection's relationship label.
3. Click it — a confirm dialog naming both entities and the relationship type should appear.
4. Confirm — the graph should refetch and the deleted relationship should no longer appear in the connections list.
5. Log out (or check as a non-admin user) — confirm the trash icon does not render.

- [ ] **Step 8: Commit**

```bash
git add apps/frontend/src/components/graph/GraphView.tsx apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "feat: let admins delete a graph relationship from the graph view"
```

---

### Task 5: Frontend — merge two entities from the graph canvas

**Files:**
- Modify: `apps/frontend/src/components/graph/GraphView.tsx`

**Interfaces:**
- Consumes: `POST /api/books/graph/merge` (now camelCase per Task 3, body `{ keepName, removeName }`); `isAdmin`, `authFetch`, `addNotification`, i18n keys `graph.admin.*` all introduced in Task 4.
- Produces: nothing consumed elsewhere — this is the last task.

There is no automated test suite for `GraphView.tsx`; verification for this task is manual via the local dev server (see Step 7).

- [ ] **Step 1: Add merge-flow state**

In `apps/frontend/src/components/graph/GraphView.tsx`, change line 67 from:

```tsx
  const [nodeConnections, setNodeConnections] = useState<any[]>([]);
```

to:

```tsx
  const [nodeConnections, setNodeConnections] = useState<any[]>([]);
  const [mergeCandidate, setMergeCandidate] = useState<GraphNode | null>(null);
  const [mergePair, setMergePair] = useState<{ a: GraphNode; b: GraphNode; keepIsA: boolean } | null>(null);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const [mergeSubmitting, setMergeSubmitting] = useState(false);
```

- [ ] **Step 2: Extend the Escape-key handler to cancel an in-progress merge**

In `apps/frontend/src/components/graph/GraphView.tsx`, change lines 416-425 from:

```tsx
  // Escape key to exit fullscreen
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullScreen) {
        setIsFullScreen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullScreen]);
```

to:

```tsx
  // Escape key to exit fullscreen or cancel an in-progress merge pick
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isFullScreen) setIsFullScreen(false);
        if (mergeCandidate) setMergeCandidate(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullScreen, mergeCandidate]);
```

- [ ] **Step 3: Add the merge-confirm submit handler**

In `apps/frontend/src/components/graph/GraphView.tsx`, immediately after the `handleDeleteRelationship` function added in Task 4, add:

```tsx
  const handleConfirmMerge = async () => {
    if (!mergePair) return;
    const keepNode = mergePair.keepIsA ? mergePair.a : mergePair.b;
    const removeNode = mergePair.keepIsA ? mergePair.b : mergePair.a;
    setMergeSubmitting(true);
    setMergeError(null);
    try {
      const res = await authFetch('/api/books/graph/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keepName: keepNode.id, removeName: removeNode.id }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || t('graph.admin.mergeError'));
      }
      setMergePair(null);
      addNotification(t('graph.admin.mergeSuccess'), 'success');
      await fetchGraphData(searchQuery);
      setSelectedNode(keepNode);
    } catch (err: any) {
      setMergeError(err.message || t('graph.admin.mergeError'));
    } finally {
      setMergeSubmitting(false);
    }
  };
```

- [ ] **Step 4: Wire node clicks to the merge-target pick**

In `apps/frontend/src/components/graph/GraphView.tsx`, change line 798 from:

```tsx
              onNodeClick={(node: any) => setSelectedNode(node)}
```

to:

```tsx
              onNodeClick={(node: any) => {
                if (mergeCandidate) {
                  if (node.id !== mergeCandidate.id) {
                    setMergePair({ a: mergeCandidate, b: node, keepIsA: true });
                  }
                  setMergeCandidate(null);
                  return;
                }
                setSelectedNode(node);
              }}
```

- [ ] **Step 5: Add the "Merge into another entity..." button to the details panel**

In `apps/frontend/src/components/graph/GraphView.tsx`, the attribute block currently ends at line 552 with:

```tsx
          )}
        </div>

        <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{t('graph.nodePanel.connections')}</h4>
```

Change it to insert a merge button between the attribute block's closing `</div>` and the connections heading:

```tsx
          )}
        </div>

        {isAdmin && (
          <button
            type="button"
            onClick={() => setMergeCandidate(selectedNode)}
            className={`mb-6 flex items-center justify-center gap-2 text-xs font-semibold rounded-xl px-3 py-2 border transition-all active:scale-95 ${isDark
              ? 'text-amber-400 border-amber-900/40 hover:border-amber-700 bg-amber-950/20'
              : 'text-amber-700 border-amber-200 hover:border-amber-300 bg-amber-50'
              }`}
          >
            <GitMerge size={14} />
            {t('graph.admin.mergeStart')}
          </button>
        )}

        <h4 className={`text-sm font-bold mb-3 ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>{t('graph.nodePanel.connections')}</h4>
```

- [ ] **Step 6: Add the pick-target banner and merge-confirm overlay to the canvas panel**

In `apps/frontend/src/components/graph/GraphView.tsx`, the "Graph Canvas Panel" container renders a `loading` overlay at lines 769-776:

```tsx
          {loading && (
            <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm z-[160] flex flex-col items-center justify-center gap-3">
              <Loader2 className="animate-spin text-amber-400" size={40} />
              <span className="text-sm font-medium text-slate-300 tracking-wider">
                {t('graph.loading')}
              </span>
            </div>
          )}
```

Immediately after this block (before the `{!loading && rawGraphData.nodes.length === 0 && (` block at line 778), add:

```tsx
          {mergeCandidate && (
            <div className="absolute top-3 inset-x-0 z-[161] flex justify-center px-4 animate-fade-in">
              <div className="flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border border-amber-400/30 rounded-2xl px-4 py-2.5 shadow-lg">
                <GitMerge size={16} className="text-amber-400 shrink-0" />
                <span className="text-xs text-slate-200 font-medium">
                  {t('graph.admin.mergePickTarget', { name: mergeCandidate.label })}
                </span>
                <button
                  type="button"
                  onClick={() => setMergeCandidate(null)}
                  className="text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600 rounded-lg px-2 py-1 transition-all active:scale-95"
                >
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          )}

          {mergePair && (
            <div className="absolute top-3 inset-x-0 z-[161] flex justify-center px-4 animate-fade-in">
              <div className="flex flex-col gap-3 bg-slate-900/95 backdrop-blur-xl border border-amber-400/30 rounded-2xl px-4 py-3 shadow-lg max-w-md w-full">
                <span className="text-xs text-slate-200 font-medium text-center">
                  {t('graph.admin.mergeConfirmMessage')}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setMergePair({ ...mergePair, keepIsA: true })}
                    className={`flex-1 text-xs rounded-lg px-2 py-2 border transition-all active:scale-95 ${mergePair.keepIsA
                      ? 'border-emerald-500 bg-emerald-950/40 text-emerald-300'
                      : 'border-slate-700 text-slate-400'
                      }`}
                  >
                    {t('graph.admin.mergeKeep')}: {mergePair.a.label}
                  </button>
                  <button
                    type="button"
                    onClick={() => setMergePair({ ...mergePair, keepIsA: false })}
                    className={`flex-1 text-xs rounded-lg px-2 py-2 border transition-all active:scale-95 ${!mergePair.keepIsA
                      ? 'border-emerald-500 bg-emerald-950/40 text-emerald-300'
                      : 'border-slate-700 text-slate-400'
                      }`}
                  >
                    {t('graph.admin.mergeKeep')}: {mergePair.b.label}
                  </button>
                </div>
                {mergeError && (
                  <span className="text-[11px] text-red-400 text-center">{mergeError}</span>
                )}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => { setMergePair(null); setMergeError(null); }}
                    disabled={mergeSubmitting}
                    className="flex-1 text-xs text-slate-300 border border-slate-700 hover:border-slate-600 rounded-lg px-2 py-1.5 transition-all active:scale-95 disabled:opacity-50"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    type="button"
                    onClick={handleConfirmMerge}
                    disabled={mergeSubmitting}
                    className="flex-1 text-xs text-white bg-red-500 hover:bg-red-600 rounded-lg px-2 py-1.5 transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    {mergeSubmitting && <Loader2 size={12} className="animate-spin" />}
                    {t('graph.admin.mergeConfirmButton')}
                  </button>
                </div>
              </div>
            </div>
          )}
```

- [ ] **Step 7: Verify the file still typechecks**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: no new errors introduced by this file

- [ ] **Step 8: Manual verification via the dev server**

Run: `./deploy/local/rebuild-and-restart.sh frontend`, then in a browser logged in as an admin user:
1. Open the Graph view, select a node.
2. Confirm the "Merge into another entity..." button appears (amber) below the attribute block.
3. Click it — confirm a banner appears over the canvas saying to click another node, with a Cancel button.
4. Press Esc — confirm the banner disappears and no merge happens.
5. Repeat, then click a second, different node on the canvas — confirm the pick-target banner is replaced by a two-option "keep A / keep B" confirm panel.
6. Toggle between the two options, then click Merge — confirm the graph refetches, the removed entity's node disappears, and its former connections now show up under the kept entity.
7. Try again but click Cancel instead — confirm no request is sent and the graph is unchanged.
8. Log out (or check as a non-admin user) — confirm the merge button does not render and clicking nodes behaves as plain selection.

- [ ] **Step 9: Commit**

```bash
git add apps/frontend/src/components/graph/GraphView.tsx
git commit -m "feat: let admins merge two graph entities from the graph view"
```
