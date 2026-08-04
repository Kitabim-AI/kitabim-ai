# تارىخنامە (History Book) — Design

## Summary

Consolidate `history_dictionary`'s two populations — a legacy, manually-seeded world-history corpus and the AI-extracted Uyghur-history facts pipeline — into **one** unified, top-level, user-facing feature: **تارىخنامە (History Book)**. This replaces Dictionary's "history" tab (`HistoryDictionaryPanel.tsx`) entirely; it does not sit alongside it. Today that tab shows a plain, unfiltered, alphabetical list with nothing but a prose definition — no facts, no citations, and (as established below) an active bug that silently drops real Uyghur historical entities during extraction.

`history_dictionary` holds two populations sharing one table: a legacy world-history corpus (e.g. "Abbas I, Safavid king of Iran" — migration `061_import_history_dictionary_data.sql`) and AI-extracted Uyghur-history entries from the book extraction pipeline. No domain filter or domain column is needed to tell them apart in the UI (see Goals/Non-goals) — every entry shows its prose definition, and entries with extracted facts additionally show a facts+citations section. Whether an entry has facts *is* the visible distinction; nothing further needs to be classified or filterable by domain.

This spec covers the read-side feature (a new top-level nav item, a unified browse/search experience, richer entry detail pages) plus one blocking pipeline bug fix. The extraction pipeline's fact-merge logic, LLM prompts, and admin staging/approval workflow are otherwise **unchanged**.

## Goals

- **One consolidated top-level page**, تارىخنامە, replacing Dictionary's "history" tab — the single place to browse and search all `history_dictionary` content.
- Category-filterable (figure/event/dynasty/concept/general), significance-sorted grid as the landing experience.
- Show individual atomic facts + citations on entries that have them. Entries with no extracted facts show their existing prose definition only — no facts section, since none were ever extracted for them.
- Full-text search across term, transliteration, and (where present) fact text.
- Filter/browse by source book — naturally only matches entries that carry citations.
- Citations deep-link into the book reader at the cited page.

## Non-goals

- **No domain filter or domain classification.** No "Uyghur history / world history" toggle, no domain column, nothing that requires classifying an entry's subject matter. The unified page shows everything; facts (where present) are the only thing that varies per entry.
- No changes to the extraction pipeline, fact merge/dedup logic, or admin staging review workflow, **except** the name-collision fix below — a targeted, isolated bug fix that directly blocks History Book data completeness, not a broader pipeline change.
- No timeline/chronological view — there's no structured date field today (dates live loosely inside `transliteration`/fact text); adding one is a separate future effort if pursued.
- No changes to the Neo4j knowledge graph — history extraction and the graph pipeline remain independent, as they are today.
- **No changes to Dictionary's other tabs** (`words`, `dictionary`, `proverbs`, `names`, `english-uyghur`, `synonyms` in `DictionaryView.tsx`) — these are unrelated to `history_dictionary` and stay exactly as they are. Only the `history` tab is being replaced; Dictionary remains a substantial standalone feature afterward.
- No physical separation of `history_dictionary` into per-feature tables, and no new columns on it either — `history_dictionary`/`history_dictionary_staging` are targeted by actively-changing pipeline code (`HistoryExtractionService`, `DictionaryStagingService`, batch extraction, admin endpoints), and neither a rename nor extra schema is worth the risk for no new capability.

## Name-collision bug fix (blocking dependency)

### The bug

`history_dictionary.term` has a single `UNIQUE INDEX` across the whole table (migration `060_create_history_dictionary.sql`), shared by both populations. Because of that constraint, `HistoryExtractionService._stage_entity` (`history_extraction_service.py:466-473`) cannot create a new AI-generated row whenever an extracted term's name collides with an existing world-history row — inserting one would violate the unique index. Today it defensively bails out instead:

```python
if existing_live and not existing_live.is_ai_generated:
    logger.info(f"Skipping history extraction staging for non-AI generated term '{term}'")
    if not existing_staging:
        return None          # the newly-extracted entity is silently discarded
    existing_live = None
```

Net effect: any real Uyghur historical figure/term whose name happens to match something in the ~thousands-strong legacy world-history seed corpus is dropped during extraction — never staged, never retried, never reachable by History Book. This is active data loss, confirmed as the mechanism behind name conflicts already observed in the pipeline.

### The fix

1. **Migration `081_scope_history_dictionary_term_uniqueness.sql`** — replace the single global unique index with two partial unique indexes, so `term` stays unique *within* each population but the two can coexist under the same name:
   ```sql
   BEGIN;
   DROP INDEX IF EXISTS public.idx_history_dictionary_term;
   CREATE UNIQUE INDEX IF NOT EXISTS idx_history_dictionary_term_ai
       ON public.history_dictionary (term) WHERE is_ai_generated = TRUE;
   CREATE UNIQUE INDEX IF NOT EXISTS idx_history_dictionary_term_manual
       ON public.history_dictionary (term) WHERE is_ai_generated = FALSE;
   COMMIT;
   ```
   Safe against existing data — global uniqueness is strictly stronger than per-partition uniqueness, so nothing currently violates the relaxed constraint. (`history_dictionary_staging.term` has no unique index, so it's unaffected.)
2. **`dictionary_repository.py::find_matching_history_term`** — scope the match itself to `is_ai_generated = TRUE`, so a non-AI row can never surface as a candidate in the first place:
   ```python
   stmt = (
       select(HistoryDictionary)
       .where(
           HistoryDictionary.is_ai_generated == True,
           _build_strict_term_where(HistoryDictionary.term, norm_term),
       )
       .order_by(...)
       .limit(1)
   )
   ```
   Required for correctness, not just cleanliness, once same-named AI/non-AI rows can coexist: without it, `ORDER BY similarity DESC LIMIT 1` is nondeterministic between two exact-match (similarity `1.0`) rows — a *repeat* extraction of the same Uyghur term could match the non-AI row again, attempt to create a second same-named AI row, and violate the new partial unique index. Scoping to `is_ai_generated = TRUE` means the query can only ever return the one AI row for a given term or nothing.
3. **`history_extraction_service.py:466-473`** — with step 2 in place, `existing_live` can now only ever be an AI-generated row or `None`; the defensive non-AI check is unreachable and is deleted rather than reworked.

### Consolidation side-note

Allowing same-named AI/non-AI rows to coexist means a unified alphabetical browse could show one term twice, with two different prose definitions. No domain label is needed to explain this (see Non-goals) — the facts+citations section itself is the visible differentiator: one version has it, the other doesn't. That's self-explanatory without adding any UI concept of "domain."

## Data model

### `history_facts` / `history_fact_citations` — normalized fact read-model

`history_dictionary.facts` (JSONB) remains the source of truth for the admin review/approval workflow — untouched. But the JSONB shape can't be efficiently full-text-searched or filtered by source book at scale. Two new tables give real indexed search and book-filtering, populated from the JSONB at the one clear write funnel: `DictionaryStagingService.approve_staging_term`.

```sql
-- 082_create_history_facts.sql

CREATE TABLE history_facts (
    id            SERIAL PRIMARY KEY,
    dictionary_id INTEGER NOT NULL REFERENCES history_dictionary(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_history_facts_dictionary_id ON history_facts(dictionary_id);
CREATE INDEX idx_history_facts_search ON history_facts USING GIN(search_vector);

CREATE TABLE history_fact_citations (
    id         SERIAL PRIMARY KEY,
    fact_id    INTEGER NOT NULL REFERENCES history_facts(id) ON DELETE CASCADE,
    book_id    VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    book_title TEXT NOT NULL,
    volume     TEXT,
    pages      INTEGER[] NOT NULL
);
CREATE INDEX idx_history_fact_citations_fact_id ON history_fact_citations(fact_id);
CREATE INDEX idx_history_fact_citations_book_id ON history_fact_citations(book_id);
```

`to_tsvector('simple', ...)` is used (not an English/language-specific config) since the content is Uyghur script. `history_dictionary.category` and `.significance_score` are already indexed (migration 079).

`history_facts` presence is a pure *display* concern here — whether an entry's detail page renders a facts+citations section — not a filter or scope boundary. The unified page never excludes or groups by it; every `history_dictionary` row is shown.

**Sync strategy** — delete-and-reinsert on every `approve_staging_term` call (first publish or re-publish via `entry_type='enrichment'`): `DELETE FROM history_facts WHERE dictionary_id = :id` (cascades to citations), then re-insert one row per active fact/citation from `staging.facts`. Runs in the same transaction as the `history_dictionary` update — always an exact snapshot of what's live, no incremental upsert logic.

**Backfill** — a one-time script materializes existing published rows' `facts` JSONB into the new tables, **scoped to `WHERE is_ai_generated = TRUE`**, not all rows. This filter is required, not optional: migration `080_add_history_facts.sql` bootstrapped a synthetic single fact (wrapping the prose `definition`) onto every row with a non-empty definition, world-history included. Backfilling unfiltered would materialize a fake fact — e.g. for Abbas I of Persia — into every world-history entry. `is_ai_generated` isn't used anywhere else in this feature; this one-time script is its only remaining relevance here. Must be idempotent/safe to re-run.

## Backend API

**Extend the existing public `/history-dictionary` router in place** rather than standing up a parallel one — once `HistoryDictionaryPanel.tsx` is replaced, that router's only consumer becomes the new unified page, so there's no reason to run two overlapping public routers over the same table.

- `GET /history-dictionary?category=&book_id=&q=&sort=significance|alphabetical&page=&page_size=`
  Paginated list. `LEFT JOIN history_facts` (not `INNER JOIN`) so entries without facts still appear. `q` searches `term`/`transliteration` (existing trigram index) OR fact `search_vector` where present. `book_id` filters via `history_fact_citations` — naturally returns only entries with citations. Response includes `category` and `significance_score` (not exposed publicly before).
- `GET /history-dictionary/{id}` (new) — full detail, always resolves for any valid id: `term`, `transliteration`, `category`, `significance_score`, `significance_reason`, synthesized `definition`, and `facts: [{id, text, citations: [{book_id, book_title, volume, pages}]}]` (empty array when none were extracted).
- `GET /history-dictionary/letter-groups`, `/stats` — unchanged in shape, still useful as-is for the landing grid facets.
- Existing admin endpoints (`admin_history_dictionary_router.py`) are unaffected.

## Frontend

- **تارىخنامە becomes the top-level nav item**, replacing Dictionary's `history` tab. `HistoryDictionaryPanel.tsx` is removed from `DictionaryView.tsx`'s tab list. Dictionary's other six tabs are untouched.
- **`HistoryBookView.tsx`** — landing page: category filter, significance-sorted grid, search bar (term + transliteration + fact text), source-book filter.
- **`HistoryBookEntryView.tsx`** — detail page: synthesized prose definition always shown; an expandable structured facts list (with citations deep-linking into the book reader) renders only when `facts` is non-empty.
  - *Open item for planning*: verify the book reader supports a page-anchor route (likely already used by RAG chat citations) so the citation deep-link can reuse existing routing.
  - *Open item for planning*: where the admin `history-staging` tab (`HistoryStagingQueuePanel.tsx`, currently a sibling of `history` in `DictionaryView.tsx`) should live once `history` moves out — leaving it in Dictionary is the low-risk default since it's an unrelated admin curation workflow, not part of this consolidation's public-facing scope.

## Testing

- Repository/service tests for the `approve_staging_term` sync step: first publish, re-publish via enrichment (facts fully replaced, no duplicates/orphans), rejected/conflict facts never materialized.
- Extraction tests for the name-collision fix: (1) a term matching an existing non-AI `history_dictionary` row is staged as `entry_type='new'` (not dropped, not treated as enrichment), coexisting with the non-AI row under the same `term`; (2) a *second* extraction of that same term correctly matches and enriches the AI row from (1), not the non-AI row.
- Backfill script test: idempotent on re-run, correct row counts against a fixture set of published entries, scoped correctly by `is_ai_generated`.
- API tests: pagination, category filter, book filter, combined term+fact-text search, detail endpoint returns for every valid id (never 404s), entries with no extracted facts return `facts: []`.
- Frontend tests: grid rendering/filtering, search-as-you-type, conditional facts-section rendering, citation deep-link generation.

## Open questions for implementation planning

1. Exact book-reader deep-link route/mechanism (confirm reuse vs. net-new).
2. Placement of the admin `history-staging` tab once `history` moves out of Dictionary.
