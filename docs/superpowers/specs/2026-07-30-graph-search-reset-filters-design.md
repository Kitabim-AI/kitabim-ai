# Design Spec: Reset Filters on Graph View Node Search

## Executive Summary
When searching for a node or executing a search query on the Graph View, all node type and relationship type filters must be reset to enabled/selected. This ensures that searched nodes and their full network of connections are completely visible without being hidden by leftover filter states.

## Problem Statement
Currently in `GraphView.tsx`, when users deselect specific Entity Types (e.g. *Location*) or Relationship Types (e.g. *WRITTEN_BY*), and subsequently search for a node via the search bar:
- `fetchGraphData` preserves the existing filter selections (`selectedNodeTypes` and `selectedEdgeTypes`).
- If the searched node or any connected nodes/edges match a currently filtered-out type, they remain hidden in the canvas.
- `navigateToEntity` only enabled the target node's type if disabled, keeping all edge filters and neighboring node filters unchanged.

## Proposed Changes

### `GraphView.tsx`

1. **`fetchGraphData` Signature & Filter Reset**:
   - Add parameter `resetFilters: boolean = false` to `fetchGraphData(query = '', resetFilters = false)`.
   - When `resetFilters` is `true`:
     - `setSelectedNodeTypes(uniqueNodeTypes)`
     - `setSelectedEdgeTypes(uniqueEdgeTypes)`
   - When `resetFilters` is `false`:
     - Maintain existing behavior of filtering `prev` against `uniqueNodeTypes` / `uniqueEdgeTypes`.

2. **Search Form Submissions (`handleSearchSubmit`)**:
   - Update `handleSearchSubmit`:
     ```ts
     const handleSearchSubmit = (e: React.FormEvent) => {
       e.preventDefault();
       setSelectedNode(null);
       setActiveTab('filters');
       fetchGraphData(searchQuery, true); // resetFilters = true
     };
     ```

3. **Clearing Search Input**:
   - Update all clear search (`X`) button click handlers across search inputs:
     ```ts
     setSearchQuery('');
     fetchGraphData('', true); // resetFilters = true
     ```

4. **Entity Navigation & Node Selection (`navigateToEntity`)**:
   - When navigating to an entity target node:
     - If fetching from backend (`!targetNode`), pass `resetFilters = true` to `fetchGraphData(term, true)`.
     - If `targetNode` is already present in `rawGraphData`, reset filters directly:
       - Set `selectedNodeTypes` to all `availableNodeTypes`.
       - Set `selectedEdgeTypes` to all `availableEdgeTypes`.

5. **Preserving Filters for Graph Mutations**:
   - Admin operations (node merge, node rename, merge undo, edge split, review approve/reject) call `fetchGraphData(searchQuery, false)` to refresh graph data while retaining the user's active filter state.

## Verification Plan

### Automated Tests
- Run `npm run test` in `apps/frontend/` to ensure frontend build and existing tests pass.
- Add unit test coverage for graph search filter resetting if applicable.

### Manual Verification
- Test unchecking node/edge filters, typing a query in the graph search input, and verifying all filters reset to active/selected when search is performed.
- Test clearing search and navigating to an entity node.
