# Knowledge Graph Entity Resolution – Design v2

**Status:** Proposed (supersedes `knowledge-graph-entity-resolution-design.md`)
**Date:** 2026-07-28
**Related:** RAG retrieval quality – graph data is currently *not referenced* in queries. See v1 §1 for the problem statement (unchanged) and its review notes for why v1's mechanics needed rework before implementation.

**Scope:** Same as v1 – the graph is dropped and regenerated from scratch. No legacy retrofit.

---

## 1. What's different from v1

v1 got the principles right (stable id over name, fiction/non-fiction scope, immutable facts over role/title, precision over recall) but described the *mechanics* in a way that didn't fit the existing pipeline and left several load-bearing pieces unspecified. This version keeps every v1 principle and fixes the mechanics:

| v1 gap | v2 fix |
|--------|--------|
| Presented fiction/non-fiction scoping as new work | Extraction is only ever manually triggered per book today (`POST /{book_id}/reprocess/graph`, `books_router.py:1767` — the automatic scanner exists in code but isn't registered). The admin already picks which specific books to extract, so their choice *is* the scope decision — passed as a parameter to the job, no derived/persisted classification needed (§3) |
| Didn't say what happens to the existing per-book `NameResolutionResponse` (Roman-numeral splitting) or the fiction book-title-name-suffix hack | Both are deleted outright – see §3. Extraction no longer does *any* name-based merge/split decision; identity is assigned by extraction position, not by name |
| No schema-level plan for dropping `entity_name_unique` | §2 makes the constraint change explicit and part of the migration |
| Two conceptually separate resolution processes (book-local vs global) | One resolution algorithm, parameterized by scope – fiction resolves within a book, non-fiction resolves across the library. Same code, same queue, same decision logic (§4) |
| `RELATED_TO` merge key excluded relation type, so two distinct facts about the same pair could collide | Relation identity now includes `rel_type` (§2) |
| Query-time disambiguation was an unbounded LLM call on the hot path | Disambiguation is pre-computed by the resolution pass and cached; query time is a lookup, with genuine ambiguity pushed into the RAG answer LLM call that already runs per query, not a second round-trip (§6) |
| Split's provenance partitioning was unspecified | §5 gives a concrete algorithm: connected-component partitioning from the admin-chosen split point |
| Iterative resolution had no ordering/convergence guarantee | §4 processes oldest-generation-first and caps re-propagation passes |

---

## 2. Data model

### Neo4j: Entity node

```
(:Entity {
  id: <uuid>,                # NEW — stable identity, assigned once at extraction, never reused
  canonical_name: <string>,  # display name (was: name)
  aliases: [<string>],       # every observed spelling incl. canonical_name
  type: <EntityType>,
  subtype: <string?>,
  scope: "fiction" | "nonfiction",
  book_id: <string?>,        # set for fiction entities only; null for non-fiction
  year_hijri: <int?>,        # Person: birth year. Event/Era: the event/era year.
  year_gregorian: <int?>,
  century_gregorian: <int?>,
  resolution_status: "unresolved" | "resolving" | "resolved",  # non-fiction only, drives the queue
})
```

**Constraint change:**
```sql
DROP CONSTRAINT entity_name_unique IF EXISTS;
CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE INDEX entity_canonical_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name);
CREATE INDEX entity_aliases_idx IF NOT EXISTS FOR (e:Entity) ON (e.aliases);
```
This is a prerequisite for §1's whole premise (two entities can share a name) and must ship in the same migration that drops the old constraint – there is no valid intermediate state.

### Neo4j: RELATED_TO edge

```
[:RELATED_TO {
  id: <uuid>,                 # NEW — identifies this specific fact
  rel_type: <string>,         # SON_OF, CONQUERED, BORN_IN, ...
  book_id: <string>,
  chunk_refs: [<string>],     # NEW — "(book_id, page_number, chunk_index)" per supporting mention, a set
  year_hijri: <int?>,
  year_gregorian: <int?>,
  century_gregorian: <int?>,
}]
```

`MERGE` key becomes `{rel_type, book_id}` between the two endpoint ids (was `{book_id}` alone) — this is what makes "the edge is the citable unit" actually true; two distinct facts about the same pair in the same book no longer collide.

> **Review note:** plain `MERGE ... SET` on this key overwrites `chunk_refs` on every re-run instead of accumulating it. Needs explicit `ON CREATE`/`ON MATCH` semantics, with the union computed in Python before the query (the codebase has no APOC plugin installed — neither `docker-compose.yml` nor `deploy/gcp/docker-compose.yml` sets `NEO4J_PLUGINS` — so `apoc.coll.toSet` isn't available; this also matches how `merge_entities` already dedups `aliases` in Python today, `graph_repository.py:349-362`, not in Cypher):
> ```cypher
> MERGE (a)-[r:RELATED_TO {rel_type: $rel_type, book_id: $book_id}]->(b)
> ON CREATE SET r.id = $edge_id, r.chunk_refs = $chunk_refs, r.year_hijri = $year_hijri
> ON MATCH SET r.chunk_refs = $merged_chunk_refs   -- Python computes list(set(existing + new)) beforehand
> ```
> Since `connect_entities_bulk` is a bulk `UNWIND`, this needs a read-before-write: query existing `chunk_refs` for the batch's `(source_id, rel_type, target_id, book_id)` keys first, union with the new batch's refs in Python, then send the already-merged value as `$merged_chunk_refs` in the same `UNWIND` write. `$edge_id`/`year_*` stay `ON CREATE`-only so a re-run never regenerates an edge's `id` or clobbers its original year fields.

**Canonical relation types for functional facts** (needed so resolution queries can pattern-match reliably instead of grepping free text): `CHILD_OF` (with `parent_role: "father" | "mother"` property, direction person → parent), `BORN_IN` (person → location), `DIED_IN` (person → era/event, carries the year). These join the existing free-form vocabulary (`SON_OF`, `RULED`, `CONQUERED`, etc.) — the extraction prompt is updated to prefer `CHILD_OF`/`BORN_IN`/`DIED_IN` specifically when the text supports them, since these three are what the resolution algorithm queries directly.

### PostgreSQL: new tables

> **Revision:** an earlier draft of this section added a persisted `books.is_fiction` column, an auto-classification-on-write hook, and an admin toggle in `AdminView.tsx`. Dropped — `run_graph_scanner` (`graph_scanner.py`) is written but never registered in `worker.py`'s `cron_jobs`, so there is no automatic milestone-driven graph extraction today. The only live path is `POST /{book_id}/reprocess/graph` (`books_router.py:1767`, admin-only, additionally gated behind the `knowledge_graph_enabled` system config), which an admin calls per book, one at a time. Since the admin is already choosing which specific books to extract, their choice *is* the fiction/non-fiction decision — see §3. No new Postgres table is needed for classification. (`fictional_categories` remains as-is, unused by this design; whether to revive it — e.g. if automatic extraction is ever turned on — is deferred.)

```sql
-- graph_resolution_queue: coordinates claiming of Neo4j entities for resolution.
-- Postgres owns queue state (FOR UPDATE SKIP LOCKED); Neo4j owns entity data.
CREATE TABLE graph_resolution_queue (
    id              SERIAL PRIMARY KEY,
    entity_id       UUID NOT NULL,            -- Entity.id in Neo4j
    scope           TEXT NOT NULL CHECK (scope IN ('fiction','nonfiction')),
    book_id         TEXT REFERENCES books(id) ON DELETE CASCADE,  -- fiction only
    sort_year       INTEGER,                  -- birth year if known, else NULL — oldest-first ordering
    status          TEXT NOT NULL DEFAULT 'idle' CHECK (status IN ('idle','in_progress','succeeded','failed','needs_review')),
    pass_count      INTEGER NOT NULL DEFAULT 0,  -- re-propagation guard, see §4
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id)
);
CREATE INDEX graph_resolution_queue_status_idx ON graph_resolution_queue (status);
CREATE INDEX graph_resolution_queue_sort_idx ON graph_resolution_queue (scope, sort_year);
```

```sql
-- graph_resolution_reviews: admin review queue, same shape as auto_correct_rules'
-- pending-queue pattern (packages/backend-core/app/db/models.py:690).
CREATE TABLE graph_resolution_reviews (
    id              SERIAL PRIMARY KEY,
    entity_a_id     UUID NOT NULL,
    entity_b_id     UUID NOT NULL,
    scope           TEXT NOT NULL CHECK (scope IN ('fiction','nonfiction')),
    evidence        JSONB NOT NULL,          -- shared/conflicting facts, LLM verdict + confidence
    suggested_action TEXT NOT NULL CHECK (suggested_action IN ('merge','split','unsure')),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    reviewed_by     TEXT REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX graph_resolution_reviews_status_idx ON graph_resolution_reviews (status);
```

Both new tables follow the project's standard migration/model/repository layering (migration file → `models.py` → repository → endpoint).

---

## 3. Extraction (light touch, revised)

**Identity is assigned at extraction, not derived from name.** Change `ExtractedEntity` so the LLM emits a `local_id` (e.g. `"e1"`, `"e2"`) unique within that one extraction call, and `ExtractedRelation.source_entity`/`target_entity` reference `local_id`, not name. `canonical_name` becomes a plain display field.

```python
class ExtractedEntity(BaseModel):
    local_id: str = Field(..., description="Unique key for this entity within this response, e.g. 'e1'. Referenced by relations.")
    name: Optional[str] = Field(None, description="Display name, original script, no year embedded")
    type: Optional[EntityType] = None
    subtype: Optional[str] = None
    year_hijri: Optional[int] = Field(None, description="For Person: birth year. For Event/Era: the event/era year.")
    century_gregorian: Optional[int] = None
    context_summary: Optional[str] = Field(None, description="Brief context to help the global resolution pass — role, era, key relationships")
```

Prompt addition (light-touch guidance, replacing the current "resolve coreferences to canonical entity names" instruction which today conflates same-name-different-people):

> "If two mentions could refer to different people who happen to share a name (different roles, no stated family/era connection), emit them as **separate** entity objects, each with its own `local_id` and `context_summary`. Do not force them together. When in doubt, keep them separate — a global resolution pass, not this extraction step, makes the final call."

**What gets deleted from `knowledge_graph_job.py` / `knowledge_graph_service.py`:**
- The `NameResolutionResponse` / `EntityOccurrenceResolution` pass and its Roman-numeral output (`knowledge_graph_service.py:134-147`, prompt ~L421-429) — no longer needed. Coreference resolution within one extraction call is handled by the LLM directly via `local_id` reuse; cross-call and cross-book duplicates are handled entirely by the global resolution pass (§4), which has strictly more context than this pass ever did.
- `get_display_name`'s book-title-suffix hack (`knowledge_graph_job.py:471-482`) — no longer needed, since fiction entities carry `scope="fiction"` + `book_id` as their actual disambiguator, not a name mutation.

**`upsert_entities_bulk` / `connect_entities_bulk` changes:**
- Each entity gets `id = uuid4()` assigned in the job (Python side), `scope` set from the job's `scope` parameter (see below), `book_id` set only when `scope == "fiction"`.
- `MERGE` is now purely by `id` (never by name) — there is no dedup at write time; dedup is entirely the resolution pass's job.
- Every non-fiction entity gets a `graph_resolution_queue` row inserted (`status='idle'`, `sort_year` from `year_hijri`/`year_gregorian` if present). Fiction entities also get a row, scoped to `book_id`, for the within-book resolution pass described in §4.

**Where scope comes from.** Extraction is only ever manually triggered, one book at a time, via `POST /{book_id}/reprocess/graph` (`books_router.py:1767-1830`, admin-only) — the automatic scanner that would need a derived classification (`graph_scanner.py`) exists in code but is never registered in `worker.py`, so there's no live path that runs extraction without an admin explicitly picking the book. That means the admin already knows, at the moment they trigger it, whether the book is fiction or non-fiction — no heuristic or persisted classification is needed to answer a question the admin is already answering by their choice of action.

Concretely: `reprocess_graph` gains a required `scope: "fiction" | "nonfiction"` field in its request body; it's passed straight through to `knowledge_graph_job` as a parameter (`enqueue_job("knowledge_graph_job", book_id=book_id, scope=scope, ...)`) and stamped onto every `Entity.scope` the job creates for that run. No `books.is_fiction` column, no `fictional_categories` auto-classification hook, no admin toggle in `AdminView.tsx` — all deferred. If automatic scanner-driven extraction is ever turned on later, *that's* the point to revisit how scope gets determined without a human in the loop (reviving `fictional_categories` matching, or something else) — not before.

---

## 4. Global resolution pass

One algorithm, parameterized by `scope`. Runs as a standard scanner+job pair, following the project's established pipeline pattern.

**`graph_resolution_scanner`** (arq cron, every 5 min):
1. Claim up to `resolution_batch_size` rows from `graph_resolution_queue` where `status = 'idle'`, `FOR UPDATE SKIP LOCKED`, ordered by `scope, sort_year ASC NULLS LAST` (oldest generation first — this is the ordering guarantee v1 lacked, and it matters here: resolving a parent before its children means "same father" evidence is checked against an already-resolved father, not a still-ambiguous one).
2. Mark claimed rows `in_progress`, commit.
3. Enqueue `graph_resolution_job` with the batch of `entity_id`s, deduplicated by `_job_id=f"graph_resolution:{scope}:batch"`.

**`graph_resolution_job`** — for each claimed `entity_id`:
0. **Existence check.** Postgres (`graph_resolution_queue`) and Neo4j (`Entity` nodes) are two separate stores with no cross-store transaction — a crash between a Neo4j merge/delete and the Postgres queue update, or a node deleted through another path (e.g. `delete_book_graph`'s orphan cleanup, `graph_repository.py:181-195`, when a contributing book is deleted), can leave a queue row pointing at an `entity_id` that no longer exists. If the claimed `entity_id` isn't found in Neo4j, mark the row `failed` and continue to the next claimed id — never let one stale reference abort the whole batch. Fiction-scoped rows self-clean on book deletion via the `book_id` FK `CASCADE` already in §2; this check covers non-fiction rows (no `book_id` to cascade from) and any Neo4j-side deletion or crash.
1. **Candidate selection.** Non-fiction: query Neo4j for other `Entity` nodes (any book, `resolution_status != 'resolving'`) whose `canonical_name` or any `aliases` entry fuzzy-matches this entity's name (edit-distance threshold from `system_configs`). Fiction: same query, restricted to `book_id = <this entity's book_id>`. No candidates → mark `resolved`, done.

   > **Review note:** the `entity_canonical_name_idx`/`entity_aliases_idx` B-tree indexes from §2 don't support fuzzy matching — Cypher has no native trigram operator, and a naive `CONTAINS`/regex scan over unindexed fuzzy comparisons degrades to a full graph scan as the library grows. Candidate selection needs a native Neo4j full-text index (no APOC required) instead:
   > ```cypher
   > CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS
   > FOR (e:Entity) ON EACH [e.canonical_name, e.aliases];
   > ```
   > queried with Lucene's fuzzy operator for the edit-distance behavior this step assumes:
   > ```cypher
   > CALL db.index.fulltext.queryNodes("entity_search_idx", $name + "~" + $editDistance)
   > YIELD node, score
   > WHERE node.id <> $entity_id
   > RETURN node, score
   > ```
   > This index replaces the plain B-tree name/alias indexes in §2 for candidate lookup (the B-tree indexes stay for exact-match reads elsewhere, e.g. the manual admin search in `GraphView.tsx`).
2. **Decision order**, per candidate pair (same as v1 §6, unchanged — the principles were correct):
   a. Scope gate — different `scope`, or fiction with different `book_id` ⇒ never candidates (already excluded by step 1, kept here as a hard invariant check).
   b. Hard constraints — conflicting `CHILD_OF` target (different resolved father/mother), conflicting `BORN_IN` target, or disjoint `[year_hijri(birth), DIED_IN year]` lifespans ⇒ split (stay separate); matching ⇒ strong merge signal.
   c. Graded signals — name/alias similarity + relationship-neighborhood overlap (shared `RELATED_TO` endpoints) + weak role/era hints ⇒ merge/split score.
   d. Gray zone — score inconclusive ⇒ single-shot LLM verdict (§4.1).
3. **Execute:**
   - Strong merge / high-confidence LLM "same" → call `merge_entities(keep_id, remove_id)` (§5).
   - Hard split signal / high-confidence LLM "different" → leave separate, done.
   - LLM "unsure" or score in the ambiguous band → insert a `graph_resolution_reviews` row, mark this queue entry `needs_review` (not `succeeded` — it stays out of future candidate scans but is visible in the admin queue).
4. **Re-propagation.** If a merge or split happened, any entity connected to the affected node(s) via `CHILD_OF` (children who might now have a different resolved parent) is re-queued (`status='idle'`) **only if `pass_count < resolution_max_passes`** (system config, default 5) — this bounds the iteration v1 left unbounded. `pass_count` increments each time a row is re-queued this way; a node that keeps flip-flopping past the cap is force-marked `needs_review` instead of looping forever.
5. Mark the original queue row `succeeded`.

### 4.1 Gray-zone LLM call

Follows the existing single-shot structured-LLM pattern (`packages/backend-core/app/services/rag/judge.py:30-69` — raw `generate_content`, not ADK Agent, per project convention). New prompt constant `ENTITY_RESOLUTION_JUDGE_PROMPT` in `prompts.py`, new config key `gemini_entity_resolution_model` (seed default = `gemini_chat_model`'s value).

```python
class EntityResolutionVerdict(BaseModel):
    verdict: Literal["same", "different", "unsure"]
    confidence: float
    reasoning: str  # logged for the admin review evidence field, not shown to end users
```

Input: both entities' `canonical_name`, `aliases`, `type`/`subtype`, resolved `CHILD_OF`/`BORN_IN`/`DIED_IN` facts, `context_summary`s, and a sample of shared/differing relationship neighbors. Output feeds directly into `graph_resolution_reviews.evidence` whether or not it's auto-applied, so every automated decision is auditable.

---

## 5. Manual control: merge / split / unmerge

`GraphRepository` moves from name-keyed to id-keyed operations:

- **`merge_entities(keep_id, remove_id, performed_by)`** — unions `aliases`, re-points all `remove_id`'s edges to `keep_id` (merging `chunk_refs` where an edge with the same `(rel_type, other_endpoint)` already exists on `keep_id`), then **before deleting `remove_id`**, writes a snapshot row to a new Postgres table `graph_merge_log` (node properties + full edge list, as they stood immediately before the merge), and only then deletes the `remove_id` node.
- **`split_entities(entity_id, split_point_edge_id)`** — addresses the gap in v1 (finding: "split's provenance partitioning was unspecified"). The admin (or the resolution job, for a hard-constraint split) identifies one conflicting edge as the split point — e.g. a `CHILD_OF` edge to a specific father. Algorithm:
  1. Remove the split-point edge from the node's edge set for clustering purposes.
  2. Run connected-component analysis on the remaining `RELATED_TO` neighborhood (via `book_id` and shared endpoints) to partition edges into two clusters — one anchored to the split-point edge's endpoint, one anchored to whatever contradicts it (the other father/birthplace/era evidence that triggered the split).
  3. Edges that don't cluster cleanly (isolated, no connection to either anchor) are left on the original node and flagged in the response for manual admin reassignment — never silently dropped or guessed.
  4. Create a new node for one cluster (new `id`; `aliases: [canonical_name]` only — **not** the original node's full alias list, see review note below). Re-point that cluster's edges (with their `chunk_refs`) to it.
- **`unmerge_entities(merge_log_id)`** — targets a specific `graph_merge_log` row, not an entity id (see review note below). Recreates `removed_entity_snapshot` as a new node, re-points the edges listed in `removed_edges_snapshot` (matched by their stable `id` from §2, which never changes across re-pointing) back onto the recreated node, marks the log row `reverted_at`.

> **Review note (split):** "aliases inherited" on the split-off node was wrong as originally written — if both post-split nodes keep the full alias list, they look identical by name/alias to the very candidate-selection query in §4 and get immediately re-flagged as merge candidates, undoing the split in the next resolution pass. The fix above (new node starts with only its `canonical_name`) avoids that loop without needing per-alias mention provenance, which doesn't exist anywhere in the current schema and would be a much larger addition than this bug warrants. Its aliases re-accumulate normally as future extraction/resolution passes re-encounter it.

> **Review note (unmerge):** a flat `merged_from` list on the surviving node can't correctly handle chained merges — and chaining is the ordinary case, not a corner case: unifying three-plus spelling variants of one figure (an extension of this doc's own `A`/`Ae` example with a third variant) merges pairwise, so `merged_from` would need to represent "C was folded into B, then B was folded into A" as a hierarchy, not a flat set, to know which edges to peel back off `A` for a single-level undo. `graph_merge_log` fixes this because each row captures an exact pre-merge snapshot tied to one merge event; reverting row N restores exactly what existed at that event, including anything absorbed by an earlier merge into the same node, with no hierarchy reconstruction needed. One limitation this doesn't solve: when a merge *combines* two edges sharing `(rel_type, other_endpoint)` into one (chunk_refs unioned, per the note above), unmerge restores both nodes but can't split that unioned `chunk_refs` set back to "which citation came from which original entity" — accepted as a known gap rather than solved here; it only affects citation-level provenance on an unmerge of a collided edge, not the node/edge structure itself.
>
> ```sql
> CREATE TABLE graph_merge_log (
>     id                       SERIAL PRIMARY KEY,
>     kept_entity_id           UUID NOT NULL,
>     removed_entity_id        UUID NOT NULL,
>     removed_entity_snapshot  JSONB NOT NULL,   -- canonical_name, aliases, type, subtype, scope, book_id, year fields
>     removed_edges_snapshot   JSONB NOT NULL,   -- [{id, rel_type, direction, other_endpoint_id, book_id, chunk_refs, year fields}, ...]
>     performed_by             TEXT,             -- admin user id, or 'system:resolution_job'
>     performed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
>     reverted_at              TIMESTAMPTZ
> );
> ```

All three are exposed under `/api/admin/graph/entities/{id}/merge|split`, `/api/admin/graph/merge-log/{merge_log_id}/unmerge`, `require_admin`, following `api-designer` conventions (camelCase schemas, `t()` errors, cache invalidation on the query-time lookup cache from §6). The existing `GraphView.tsx` admin merge UI (`d0566d8`) is extended with split/unmerge actions (unmerge listing pulled from `graph_merge_log`) and a review-queue tab backed by `graph_resolution_reviews`, styled after `AutoCorrectRulesPanel.tsx`'s pending-approve/reject pattern.

---

## 6. Query time

No LLM call in the interactive path. After every successful merge/split/unmerge and every `graph_resolution_job` batch, the affected `(alias → [entity_id])` mappings are recomputed and written to Redis (`cache_config.KEY_GRAPH_ALIAS_LOOKUP.format(alias=normalized_alias)`, TTL matches other RAG cache entries).

- **Single match** → resolve directly, no extra call.
- **Multiple matches** (genuine ambiguity, e.g. king A vs president A both still valid, distinct entities) → do not guess and do not make a second LLM round-trip. Retrieve facts/edges from *all* matching entities, each tagged with its own citations, and hand them to the existing RAG answer-generation call (already one LLM call per user turn) exactly as multiple retrieved chunks are handled today. The answer model resolves ambiguity using the user's question wording — the same "precision over recall" principle from v1, but paid for with zero extra latency since it rides the call that was happening anyway.
- **No match** → fall back to the existing hybrid text search leg, unchanged.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Over-merging distinct figures | Hard-constraint blocks on conflicting `CHILD_OF`/`BORN_IN`; oldest-first ordering resolves parents before children so "same father" evidence isn't built on an unresolved node; every merge reversible via `graph_merge_log`. |
| Under-merging (residual duplicates) | Global queue re-scans on graph changes; admins can merge manually via `GraphView`. |
| Wrong automated split | Split only fires on a hard-constraint conflict or high-confidence LLM verdict; connected-component partitioning flags unclustered edges for manual review rather than guessing; fully reversible via `unmerge_entities`. |
| Noisy source data | LLM gray-zone verdict always logged to `graph_resolution_reviews.evidence` even when auto-applied, so a bad automated call is auditable and correctable after the fact. |
| Unbounded iterative re-propagation | `pass_count` cap (`resolution_max_passes`, default 5) forces `needs_review` instead of looping. |
| Wrong scope crossing the fiction/non-fiction boundary | Scope is a deliberate, per-book admin choice at the moment of triggering extraction (§3), not an automated guess — no heuristic to misfire. |
| Query-time latency/cost | No LLM call added to the hot path (§6) — ambiguity is resolved by the existing per-turn RAG call, not a new one. |
| `graph_resolution_queue` referencing a Neo4j entity that no longer exists (crash mid-merge, or deletion via another path) | `graph_resolution_job` checks entity existence before processing a claimed row; missing entity → mark row `failed` and skip, not crash the batch (§4). |
| Unmerge across a collided edge losing citation-level provenance | Accepted limitation, not solved — see the unmerge review note in §5. |

---

## 8. Rollout

1. **Migrations** — `graph_resolution_queue`, `graph_resolution_reviews`, `graph_merge_log` (§5); Neo4j constraint swap (`entity_name_unique` → `entity_id_unique`) and the `entity_search_idx` full-text index (§4) applied as part of the "drop and regenerate" reset, not a live migration on existing data. Update `init_constraints()` in `graph_repository.py:80-104` to drop `entity_name_unique` / create `entity_id_unique` / create `entity_search_idx` — otherwise the next application restart re-creates the old name-uniqueness constraint on startup and silently reintroduces the bug this whole design fixes.
2. **Extraction changes** — `local_id`-keyed `ExtractedEntity`/`ExtractedRelation`, remove `NameResolutionResponse` pass and book-title-suffix hack, wire `graph_resolution_queue` inserts, `connect_entities_bulk` moves to the `ON CREATE`/`ON MATCH` upsert from §2, `knowledge_graph_job` takes `scope` as a required parameter instead of deriving it.
3. **`reprocess_graph` endpoint change** — add the required `scope: "fiction" | "nonfiction"` field to the request body and pass it through to the enqueued job (§3).
4. **New scanner/job** — `graph_resolution_scanner` + `graph_resolution_job`, registered in `WorkerSettings`, config keys seeded (`resolution_batch_size`, `resolution_max_passes`, `resolution_similarity_threshold`, `gemini_entity_resolution_model`), existence-check guard from §4 in place before the batch runs.
5. **Admin API + UI** — id-keyed merge/split endpoints, merge-log-keyed unmerge endpoint, review-queue endpoints, `GraphView.tsx` extensions.
6. **Query-time cache** — alias-lookup cache population hook on every resolution outcome; RAG retrieval reads it instead of any live disambiguation call.
7. **Production cutover** — old graph data is name-keyed and has no `id`/`scope`/canonical `chunk_refs`; it's structurally incompatible with everything above, not just stale. Wipe it rather than migrate it in place, in this order:
   1. Set `knowledge_graph_enabled=false` (system config) so no `reprocess_graph` call can race the cutover.
   2. Apply the Postgres migrations (§2/§5) and deploy the updated backend/worker. `init_constraints()` runs its `DROP CONSTRAINT entity_name_unique` / `CREATE CONSTRAINT entity_id_unique` / `CREATE FULLTEXT INDEX entity_search_idx` on the new code's next startup (step 1) — let that happen before the next step, so the constraint swap starts from a clean slate.
   3. Wipe Neo4j: `docker exec -it <neo4j_container> cypher-shell -u neo4j -p $NEO4J_PASSWORD "MATCH (n) DETACH DELETE n"` (`cypher-shell` is bundled in the `neo4j:5.26.0` image already in use, `deploy/gcp/docker-compose.yml:97`; auth from `NEO4J_AUTH`/`NEO4J_PASSWORD`, `deploy/gcp/docker-compose.yml:103`). No need to touch the `/mnt/kitabim-data/neo4j/data` volume directly — this clears node/edge data while leaving the running instance and its (freshly swapped) constraints intact.
   4. Bulk-reset `books.graph_milestone = 'idle'` for every book in Postgres — without this, books keep showing a stale `succeeded` from the wiped-out old graph even though Neo4j now has nothing for them. This matters more than it would have under the old automatic-scanner design, since re-extraction is manual and selective (§3) — most books will legitimately stay at `idle`/no-graph indefinitely until an admin picks them, not just transiently during a backfill window.
   5. Set `knowledge_graph_enabled=true` again, then re-trigger `reprocess_graph` (with `scope`) per book, at whatever pace the admin chooses — no bulk/automatic re-extraction, consistent with §3.
