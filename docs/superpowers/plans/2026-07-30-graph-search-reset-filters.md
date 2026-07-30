# Graph Search Reset Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically reset all node type and relationship type filters to active/selected when searching for a node or executing search queries on the Graph View.

**Architecture:** Extend `fetchGraphData` in `GraphView.tsx` with a `resetFilters: boolean = false` parameter. When submitting a search, clearing search, or navigating to an entity node, set `resetFilters = true` and reset filter state (`selectedNodeTypes` and `selectedEdgeTypes`) to ensure all nodes and relationships in the query result are completely visible.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS.

## Global Constraints
- Do not affect filter preservation on administrative graph mutations (node merge, node rename, edge split, review approve/reject).
- Ensure node and edge types are dynamically populated from fetched data before resetting filters.

---

### Task 1: Update `fetchGraphData`, `handleSearchSubmit`, and `navigateToEntity` in `GraphView.tsx`

**Files:**
- Modify: `apps/frontend/src/components/graph/GraphView.tsx:183-288`
- Modify: `apps/frontend/src/components/graph/GraphView.tsx:585-591`
- Modify: `apps/frontend/src/components/graph/GraphView.tsx:1210-1475`

**Interfaces:**
- Consumes: `GraphView.tsx` internal state (`rawGraphData`, `availableNodeTypes`, `availableEdgeTypes`)
- Produces: Updated state setters `setSelectedNodeTypes`, `setSelectedEdgeTypes` when `resetFilters = true`

- [ ] **Step 1: Update `fetchGraphData` signature and filter reset logic**

In `apps/frontend/src/components/graph/GraphView.tsx`, update `fetchGraphData` to accept `resetFilters: boolean = false`:

```typescript
  const fetchGraphData = async (query = '', resetFilters = false) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/books/graph${query ? `?q=${encodeURIComponent(query)}` : ''}`);
      const graphData: GraphData = await res.json();

      const coloredNodes = graphData.nodes.map(node => {
        let color = '#94a3b8';
        const type = (node.type || '').toLowerCase();
        if (type.includes('person') || type.includes('character') || type.includes('يازغۇچى') || type.includes('شەخس')) {
          color = '#fbbf24';
        } else if (type.includes('place') || type.includes('location') || type.includes('يەر') || type.includes('جاھان')) {
          color = '#38bdf8';
        } else if (type.includes('org') || type.includes('group') || type.includes('تەشكىلات')) {
          color = '#34d399';
        } else if (type.includes('event') || type.includes('تارىخ') || type.includes('ۋەقە')) {
          color = '#f87171';
        } else if (type.includes('historicalera') || type.includes('era') || type.includes('دەۋر')) {
          color = '#c084fc';
        } else if (type.includes('concept') || type.includes('ئۇقۇم')) {
          color = '#818cf8';
        } else if (type.includes('other') || type.includes('باشقىلار')) {
          color = '#94a3b8';
        } else if (type.includes('book') || type.includes('ئەسەر') || type.includes('قىسسە')) {
          color = '#818cf8';
        }
        return { ...node, color };
      });

      setRawGraphData({ nodes: coloredNodes, links: graphData.links });

      const uniqueNodeTypes = Array.from(new Set(coloredNodes.map(node => node.type || 'Entity')));
      const uniqueEdgeTypes = Array.from(new Set(graphData.links.map(link => link.label || 'RELATED_TO')));

      if (!isInitializedRef.current || resetFilters) {
        setSelectedNodeTypes(uniqueNodeTypes);
        setSelectedEdgeTypes(uniqueEdgeTypes);
        isInitializedRef.current = true;
      } else {
        setSelectedNodeTypes(prev => {
          if (prev.length >= availableNodeTypes.length && availableNodeTypes.length > 0) {
            return uniqueNodeTypes;
          }
          return prev.filter(t => uniqueNodeTypes.includes(t));
        });

        setSelectedEdgeTypes(prev => {
          if (prev.length >= availableEdgeTypes.length && availableEdgeTypes.length > 0) {
            return uniqueEdgeTypes;
          }
          return prev.filter(t => uniqueEdgeTypes.includes(t));
        });
      }
      return coloredNodes;
    } catch (e) {
      console.error('Failed to load graph data', e);
      return [];
    } finally {
      setLoading(false);
    }
  };
```

- [ ] **Step 2: Update `navigateToEntity` to reset filters on target entity selection**

In `navigateToEntity`:
```typescript
  const navigateToEntity = async (entityId: string, entityName?: string) => {
    const normName = entityName ? entityName.trim().toLowerCase() : '';
    
    let targetNode = rawGraphData.nodes.find(
      n => n.id === entityId || (normName && n.label.trim().toLowerCase() === normName) || n.id === entityName
    );

    if (!targetNode) {
      const term = entityName || entityId;
      setSearchQuery(term);
      const loadedNodes = await fetchGraphData(term, true);
      if (loadedNodes && loadedNodes.length > 0) {
        targetNode = loadedNodes.find(
          n => n.id === entityId || (normName && n.label.trim().toLowerCase() === normName) || n.id === entityName
        ) || loadedNodes[0];
      }
    }

    if (targetNode) {
      setSelectedNodeTypes(availableNodeTypes);
      setSelectedEdgeTypes(availableEdgeTypes);

      setSelectedNode(targetNode);
      setActiveTab('details');

      setTimeout(() => {
        if (fgRef.current) {
          if (targetNode.x !== undefined && targetNode.y !== undefined) {
            fgRef.current.centerAt(targetNode.x, targetNode.y, 800);
            fgRef.current.zoom(2.5, 800);
          } else {
            fgRef.current.zoomToFit(400);
          }
        }
      }, 100);
    }
  };
```

- [ ] **Step 3: Update `handleSearchSubmit` and search clear handlers**

In `handleSearchSubmit`:
```typescript
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSelectedNode(null);
    setActiveTab('filters');
    fetchGraphData(searchQuery, true);
  };
```

And update the 3 clear search (`setSearchQuery('')`) handlers at lines 1216, 1260, and 1469:
```typescript
  onClick={() => {
    setSearchQuery('');
    fetchGraphData('', true);
  }}
```

- [ ] **Step 4: Verify build and test compilation**

Run: `npm --prefix apps/frontend test -- --run`
Expected: PASS

- [ ] **Step 5: Commit changes**

```bash
git add apps/frontend/src/components/graph/GraphView.tsx
git commit -m "feat(graph): reset node and edge filters on searching new node"
```
