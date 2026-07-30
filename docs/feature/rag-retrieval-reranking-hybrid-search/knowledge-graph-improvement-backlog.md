# Knowledge Graph – Improvement Backlog (TODO)

**Status:** Planning – no code changes made yet
**Date:** 2026-07-29
**Area:** Knowledge Graph entity resolution v2 (`packages/backend-core`, `services/worker`, `apps/frontend`)
**Related:**
[FINDING-child-of-resolution-query-mismatch.md](FINDING-child-of-resolution-query-mismatch.md),
[DESIGN-REVIEW-entity-resolution.md](DESIGN-REVIEW-entity-resolution.md),
[graph-extraction-normalization-diagrams.md](graph-extraction-normalization-diagrams.md)

> **Assumption:** existing graph data will be **wiped and regenerated manually** (step by step)
> after this work lands. So no backfill, migration, re-queue, or existing-data compatibility is
> needed for any item below – the graph starts clean, and every entity is (re)extracted under the
> fixed code.

Two independent tracks:
- **In-house correctness (items 1-4)** – no new dependency; do these first.
- **GDS adoption (items 5-9)** – external graph-algorithm engine for matching/clustering.
**UI (item 10, optional)** – items 1-8 need **no** frontend changes; item 9 can ship with none
(flatten clusters to pairwise reviews). Item 10 tracks the optional cluster-review UX + GDS extras.

---

## Checklist

- [x] **1. Fix parent/birthplace resolution queries**
- [x] **2. Persist `context_summary` on Entity nodes**
- [x] **3. Audit & harden merge/split decision rules**
- [x] **4. Harden relation extraction against figurative/honorific language**
- [x] **5. Enable Neo4j GDS + graph projection**
- [x] **6. Shared-neighbor matching via `nodeSimilarity`**
- [x] **7. Structural embeddings via `FastRP`/`node2vec`**
- [x] **8. Semantic name matching via `kNN`**
- [x] **9. Group-then-merge clustering via `WCC`**
- [x] **10. (Optional) Cluster-review UI + GDS UX extras**

---

## Details

### 1. Fix parent/birthplace resolution queries
The resolver reads facts by matching nonexistent typed edges (`:CHILD_OF`/`:BORN_IN`/`:DIED_IN`)
instead of `:RELATED_TO {rel_type: ...}`, so hard constraints and child re-propagation are
inert in prod. Also fold in the gendered kinship types (`SON_OF`/`DAUGHTER_OF`/`FATHER_OF`/`MOTHER_OF`)
with correct edge direction.
- **Files:** `packages/backend-core/app/db/repositories/graph_repository.py`
  (`get_entity_facts`, `get_children_via_child_of`)
- **Depends on:** nothing – do first.
- **Deploy note:** graph is wiped and regenerated after this work (see Assumption), so no
  re-queue or unmerge-of-bad-merges backfill is needed – just ship the fix + tests.

### 2. Persist `context_summary` on Entity nodes
The LLM already produces `ExtractedEntity.context_summary`, but the job drops it when building
`entity_data`, so it's never stored. Persist it for use as the embedding source (item 8) and as
richer LLM-judge input.
- **Files:** `services/worker/jobs/knowledge_graph_job.py` (entity_data assembly),
  `packages/backend-core/app/db/repositories/graph_repository.py` (`upsert_entities_bulk`)
- **Depends on:** nothing.

### 3. Audit & harden merge/split decision rules
The item-1 data bug. Today `_check_hard_constraints` returns `"match"` on **any shared parent**, and
`resolve_entity` turns that straight into an **auto-merge** (bypassing the graded score and the LLM
judge). Two problems:
1. **Siblings share a father** – two different, similarly-named "son of Ibrahim" people can be
   brothers, not the same person; auto-merge collapses them.
2. **Shared prominent ancestors are pervasive in this corpus** – many distinct figures are "son of
   Adam / Nuh / Ibrahim / The Prophet", so "same father" is often a *weak, noisy* signal. Combined
   with a common given name it risks **mass over-merges onto a hub ancestor**.

Recommended changes:
- Treat **same father** as a *supporting signal that raises the score*, not a standalone auto-merge.
- **Discount shared-parent evidence when the parent is a high-degree hub** (common ancestor many
  nodes point to).
- Keep the **veto direction hard** (different father / different birthplace -> keep separate) – that
  one is safe.
- Add tests for the sibling and shared-ancestor cases.
- **Files:** `packages/backend-core/app/services/entity_resolution_service.py`
  (`_check_hard_constraints`, `resolve_entity` decision flow)
- **Depends on:** item 1 (rules need real data to act on); pairs well with an eval set.

### 4. Harden relation extraction against figurative/honorific language
A relation-extraction **precision** problem: figurative/metaphorical/honorific statements are being
turned into literal edges (observed: *"he gave me the love of a father"* produced a `SON_OF` edge
between two entities). No graph-side fix undoes this – it must be prevented at extraction (or caught
in review). This is an in-house / extraction-quality item; do it **before the graph regen** so the
regenerated graph is clean.

Recommended changes:
- **Prompt hardening** (primary): in the extraction prompt kinship section, add an explicit rule –
  "only emit kinship edges (`SON_OF`/`FATHER_OF`/`CHILD_OF`/...) for a **literal biological, legal, or
  genealogical** relationship; never from figurative, simile, metaphorical, honorific, or emotional
  expressions." Include negative examples:
  - Simile/metaphor: "loved me *like* a father", "*gave the love of a father*", "was *a father to*
    the orphans" -> **no edge**
  - Honorific/epithet: "father of the nation", "father of medicine" -> **no edge**
  - Spiritual/figurative: "spiritual father", "father of the movement" -> **no edge**
  - Uyghur: `ئاتا / ئاتىسى` used figuratively (with comparison markers `ئوخشاش`, `گويا`, `دەك` ->
    **no edge**; treat these like the existing `نەسەبى / ئاتىسى` special-casing.
- **Precision over recall for relations**: "when unsure whether a relationship is literal, do not
  emit the edge."
- **Evidence field (defense in depth):** add an `evidence` (source phrase) field to
  `ExtractedRelation`, so figurative extractions are auditable and a cheap rule / LLM-judge pass can
  flag simile/honorific markers before the edge is written.
- **Files:** `services/worker/jobs/knowledge_graph_job.py` (extraction prompt),
  `packages/backend-core/app/services/knowledge_graph_service.py` (`ExtractedRelation` schema).
- **Depends on:** nothing.
- **Note:** LLM extraction can't be made perfect – `chunk_refs` + the review UI remain the safety net
  for the residual cases.

### 5. Enable Neo4j GDS + graph projection
Install/enable the GDS plugin on the Neo4j image and add projection lifecycle plumbing
(`gds.graph.project`, refresh strategy). Foundation for items 6-9.
- **Files:** `deploy/gcp/docker-compose.yml`, `docker-compose.yml`, worker/backend graph plumbing
- **Depends on:** nothing (but items 6-9 depend on it).
- **Licensing (verified 2026-07-29, GDS docs v2026.06):** GDS runs as **Community Edition by
  default** – free, open source – and "includes all algorithms." So `nodeSimilarity`, `kNN`,
  `wcc`, `FastRP`, `node2vec` (items 6-9) are all covered at no cost on Neo4j Community Edition.
  The plugin is bundled in the Neo4j Server distribution (`products/` -> `plugins/`, set
  `dbms.security.procedures.unrestricted=gds.*`). Community caps that do **not** affect our plan:
  max **4 CPU cores** (caps speed, not capability), **3-model** catalog + **no model persistence**
  (only relevant to *trained* ML pipelines like GraphSAGE – our plan uses untrained algorithms +
  FastRP, no stored model). Enterprise adds only scaling/ops features (unlimited cores, cluster
  writes, backup/restore, Apache Arrow), none of which are algorithms.
- **RAM & Lifecycle configuration:** Configure Neo4j heap memory (`dbms.memory.heap.max_size`) and GDS projection memory limits in `docker-compose.yml` and `deploy/gcp/docker-compose.yml`. Explicitly define the projection creation/eviction lifecycle (e.g. batch projection rebuild post-ingestion job vs scheduled refresh) to prevent host VM OOM issues.

### 6. Shared-neighbor matching via `nodeSimilarity`
Replace/augment per-entity neighbor overlap with a global Jaccard/overlap computation. No
embeddings required – reads graph structure directly.
- **Depends on:** item 5.

### 7. Structural embeddings via `FastRP`/`node2vec`
Generate node vectors from graph topology (no external model, no new text embeddings) for
structural similarity.
- **Depends on:** item 5.

### 8. Semantic name matching via `kNN`
Build a normalized entity-profile string (`canonical_name` + `aliases` + `type` + `context_summary`
+ key facts), embed with the existing Gemini stack, store as a node property, and match via GDS
`kNN`. Catches nicknames/titles/transliterations that lexical matching misses.
- **Depends on:** item 2 (context_summary) and item 5 (GDS).
- **Uyghur note:** NFC-normalize and strip grammatical suffixes before embedding; validate Uyghur
  embedding quality against a labeled pair set.

### 9. Group-then-merge clustering via `WCC`
Replace order-dependent greedy pairwise merging with global cluster formation over the similarity
graph; feed clusters into the review queue. Reuses the union-find concept already used for splitting.
- **Depends on:** item 5 (and benefits from items 6-8).
- **Cost & Latency Reduction:** Forming WCC clusters *before* invoking the LLM judge dramatically reduces LLM judge API calls and token consumption by evaluating a candidate cluster in a single group prompt pass rather than running $\binom{N}{2}$ separate pairwise LLM comparisons.
- **UX note:** can be introduced invisibly by flattening clusters back to pairwise review rows;
  a cluster-based review card is an optional later upgrade (item 10).

### 10. (Optional) Cluster-review UI + GDS UX extras
Items 1-8 require **no** UI changes, and item 9 can ship with none by flattening clusters into the
existing pairwise review rows. This item captures the *optional* frontend upgrades that GDS unlocks:
- **Cluster-review card** – review a whole suspected-duplicate group at once (approve all / tick
  which members belong), instead of pairwise approve/reject. Needs a changed review-queue API shape.
- **Confidence scores** on suggested merges in the review card.
- **"Suggested duplicates" dashboard** – proactively list likely duplicates from `nodeSimilarity`/`kNN`.
- **Graph visual extras** – cluster highlighting, community coloring (Louvain), centrality-based sizing.
- **Show `context_summary`** in the details/review panel now that it's persisted (item 2).
- **Files:** `apps/frontend/src/components/graph/GraphView.tsx` (+ review-queue endpoints if clusters
  are exposed).
- **Depends on:** item 9 for cluster review; item 2 for showing context_summary.

---

## Suggested order

1. **Items 1, 2, 3 & 4** – in-house correctness, data, decision-rule hardening, and extraction
   precision. Do all four **before the graph regen** so the regenerated graph is clean.
2. **Item 5** – GDS foundation.
3. **Items 6, 7, 8** – matching signals (6 and 7 need no embeddings; 8 needs item 2).
4. **Item 9** – clustering that consumes the signals above.
5. **Item 10 (optional)** – cluster-review UI + UX extras, only if/when you want them.

## Not covered by GDS (still in-house)
The storage-model fix (item 1), all domain decision rules (hard constraints, LLM judge, thresholds),
relation-extraction precision (item 4), an evaluation scorecard with a labeled Uyghur pair set, and
all Uyghur-specific normalization. See the design-review doc for the full buy-vs-build split.
