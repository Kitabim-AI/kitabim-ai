# Knowledge Graph Component (`graph`)

## Overview
Provides an interactive 2D force-directed knowledge graph visualization of historical entities, relationships, and temporal timelines, accompanied by administrative curation tools for entity merging, unmerging, renaming, splitting, and relationship review queue management.

## Interface
- `[GraphView.tsx:GraphView]` — Interactive 2D force-directed knowledge graph visualization component using `react-force-graph-2d`, with node/link filtering by entity type and century, temporal timeline views, citation text previewing, and admin curation tools.

## Invariants
- `[GraphView.tsx:resolveEndpointId]` — Resolves link source and target endpoints defensively handling `null`, `undefined`, and mutated object references from the force simulation.
- `[GraphView.tsx:isAdmin]` — Restricts graph curation actions (entity merge, split, relationship deletion, review queue decisions) to administrators via `useIsAdmin()`.

## Side Effects
- `[GraphView.tsx:fetchGraphData]` — Performs HTTP `GET` to `/api/books/graph` with optional `query` and `book_id` parameters.
- `[GraphView.tsx:authFetch]` — Authenticated HTTP calls for `/api/books/graph/chunk`, `/api/books/graph/relationship/delete`, `/api/books/graph/merge`, `/api/admin/graph/merge-log/${mergeLogId}/unmerge`, `/api/books/graph/entity/rename`, `/api/admin/graph/entities/${id}/split`, and `/api/admin/graph/review-queue`.

## Verification
- Run: `npm test`
