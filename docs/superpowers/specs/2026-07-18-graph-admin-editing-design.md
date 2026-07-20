# Admin Graph Editing: Delete Relationship & Merge Entities

**Date:** 2026-07-18
**Status:** Approved

## Problem

Admins have no way to correct the knowledge graph (Neo4j `Entity` nodes + `RELATED_TO` edges) once it's extracted. Two corrections are needed:

1. Delete an incorrect relationship between two entities.
2. Merge two entity nodes that represent the same real-world thing (duplicates from extraction).

## Existing state

- `apps/frontend/src/components/graph/GraphView.tsx` is a **public**, unauthenticated page (`react-force-graph-2d`) showing all entities/relationships up to 150 rows, with free-text search and type filters. Clicking a node opens a side "details" panel (`renderDetailsPanelContent`, lines ~505-620) listing the node's attributes and a scrollable list of its connections (`nodeConnections`, derived client-side from `filteredData.links`). Edges are not independently clickable.
- Backend already has `POST /api/books/graph/merge` (`services/backend/api/endpoints/books_router.py:999`), admin-gated (`Depends(require_admin)`), backed by `GraphRepository.merge_entities(keep_name, remove_name)` (`packages/backend-core/app/db/repositories/graph_repository.py:289`). This is a **true merge**: it coalesces scalar properties (keep wins on conflict), combines `aliases`, migrates all outgoing/incoming `RELATED_TO` edges from the removed node onto the kept node (re-keyed per `book_id`), then deletes the removed node. It is fully tested (`services/backend/tests/api/endpoints/books_router_test.py`) but has **no frontend caller anywhere** — this feature wires it up rather than reimplementing merge logic.
- There is **no delete-relationship endpoint or repo method** at single-edge granularity. The only precedent is `delete_book_graph(book_id)` (`graph_repository.py:181`), which bulk-deletes all edges for a book plus orphan-node cleanup — not directly reusable.
- `RELATED_TO` relationships carry a `book_id` property as part of their identity (set by `connect_entities_bulk`), so the same conceptual relationship extracted from multiple books exists as multiple separate edges. The frontend renders one connection row per relationship **type** between two entities, not one per book-scoped edge — so "delete this relationship" must remove all book-scoped duplicates of that (source, target, type) triple to match what's visually shown.
- Admin role detection on the frontend: `useIsAdmin()` (`apps/frontend/src/hooks/useAuth.tsx:236`). Authenticated API calls use `authFetch` (`apps/frontend/src/services/authService.ts:94`) — attaches Bearer token, retries once on 401. Confirm dialogs use the shared `Modal` component via `useAppContext().setModal` (`apps/frontend/src/context/AppContext.tsx`), rendered globally in `Shell.tsx`.

## Design

### Access model
No new route or admin tab. `GraphView.tsx` stays public; when `useIsAdmin()` is true, extra destructive controls render inline in the existing details panel. All destructive calls hit admin-gated endpoints regardless of client-side gating.

### Backend: delete relationship

**Repo method** — `GraphRepository.delete_relationship(source_name: str, target_name: str, rel_type: str) -> bool`, added to `graph_repository.py` near `merge_entities`. NFC-normalizes both names, then:

```cypher
MATCH (a:Entity {name: $source_name})-[r:RELATED_TO {type: $rel_type}]->(b:Entity {name: $target_name})
DELETE r
RETURN count(r) AS deleted
```

Removes every matching edge regardless of `book_id` (matches the "delete all book-scoped duplicates" decision). Raises `ValueError` if zero edges matched, mirroring `merge_entities`'s not-found handling. No orphan-node cleanup — a node left with no edges after this becomes an isolated node, which is correct (the admin is editing one relationship, not purging book data).

**Endpoint** — added to `books_router.py` next to the existing `/graph/merge` route:

```
POST /api/books/graph/relationship/delete
Depends(require_admin)
Body: DeleteRelationshipRequest { sourceName, targetName, relType }  (camelCase schema, schemas.py)
```

200 on success, 400 (`t("errors.not_found")`) if nothing matched, 500 on unexpected errors — same shape as the existing merge endpoint's error handling.

### Backend: merge entities

No backend changes required. The frontend will call the existing `POST /api/books/graph/merge` with `{ keepName, removeName }`.

### Frontend: GraphView.tsx

**New imports:** `useIsAdmin` (`hooks/useAuth`), `authFetch` (`services/authService`), `useAppContext` (for `setModal`), `Trash2` and a merge icon (e.g. `GitMerge`) from `lucide-react`.

**Delete relationship:**
- Each connection row inside the details panel's connections list gets a `Trash2` icon button, rendered only when `isAdmin`.
- Click opens the shared confirm `Modal` (`destructive: true`) with a message naming both entities and the relationship type.
- On confirm: `authFetch('/api/books/graph/relationship/delete', { method: 'POST', body: JSON.stringify({ sourceName, targetName, relType }) })`. On success: refetch graph data, close modal, toast success via `addNotification`. On failure: surface the error in the modal.

**Merge entities:**
- New state: `mergeCandidate: GraphNode | null`.
- When a node is selected and `isAdmin`, the attribute block in the panel gets a "Merge into another entity…" button. Clicking sets `mergeCandidate` to the currently selected node and shows a small banner instructing the admin to click another node on the canvas (Esc cancels).
- `onNodeClick` is extended: if `mergeCandidate` is set and the newly clicked node differs from it, this click is interpreted as picking the merge target instead of normal node selection. This opens a confirm modal letting the admin choose which of the two entities survives (defaulting to `mergeCandidate`), then calls `authFetch('/api/books/graph/merge', { method: 'POST', body: JSON.stringify({ keepName, removeName }) })`.
- On success: refetch graph data, clear `mergeCandidate`, re-select the surviving node, toast success. On failure (400 = entity not found): surface the error in the modal.

**Refresh strategy:** both actions trigger a full `fetchGraphData()` refetch on success rather than optimistic local state splicing. The graph view is capped at 150 rows, so a full force-layout relayout is cheap; refetching also avoids any risk of client state drifting from Neo4j after a merge, which can touch many edges at once. This is a deliberate simplicity-over-polish trade-off for an infrequent admin action.

**i18n:** all new user-facing strings added under a `graph.admin.*` namespace in the locale files; no hardcoded text.

### Testing

- Backend: `graph_repository_test.py` — new tests for `delete_relationship` (edge found and deleted; not-found raises `ValueError`; multiple book-scoped duplicates all removed).
- Backend: `books_router_test.py` — new endpoint test mirroring the existing `test_merge_graph_entities_endpoint` pattern (403 without admin, 400 on not-found, 200 on success).
- Frontend: no existing test file for `GraphView.tsx`; not adding a full suite here. Manual verification via the local dev server (delete a connection, merge two nodes) once implemented.

## Explicitly out of scope

- Any new audit/logging trail for these actions (confirmed with user: confirm dialog only, no persistent audit record).
- True "link as alias without deleting" — the existing `/graph/merge` semantics (delete + migrate) are being reused as-is, not replaced with a lighter-weight linking feature.
- A dedicated admin-only graph tab/route — controls live inline on the existing public `GraphView`.
- Deleting an entity node outright (not requested).
- Picking a specific book-scoped edge to delete when duplicates exist across books — deletion always removes all duplicates of a (source, target, type) triple.
