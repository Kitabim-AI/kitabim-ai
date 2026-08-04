# History Book (تارىخنامە) — Design

## Summary

Turn the AI-extracted Uyghur history facts currently sitting in `history_dictionary` / `history_dictionary_staging` into a first-class, top-level, user-facing feature: **تارىخنامە (History Book)**. Today, published entries are only reachable through a plain alphabetical "history" tab buried inside the Dictionary page, showing nothing but a synthesized prose definition — the individual facts and their book/page provenance (the most valuable part of the extraction pipeline) are invisible to end users.

`history_dictionary` actually holds two distinct populations that happen to share a table: a legacy, manually-seeded world-history corpus (`is_ai_generated = FALSE`, e.g. "Abbas I, Safavid king of Iran" — migration `061_import_history_dictionary_data.sql`) and AI-extracted Uyghur-history entries produced by the book extraction pipeline (`is_ai_generated = TRUE`). Facts are, and will only ever be, populated for the AI-extracted population — there is no plan to populate `facts` for the legacy world-history terms. History Book therefore scopes to `is_ai_generated = TRUE` only; the existing Dictionary "history" tab is explicitly **out of scope and untouched** (see Non-goals).

This spec covers the read-side feature only: a new top-level nav item, richer entry detail pages, and full-text/category/source-book search. The existing extraction pipeline, staging/review workflow, and admin approval flow (`HistoryExtractionService`, `DictionaryStagingService`, `HistoryStagingQueuePanel.tsx`, admin endpoints) are **unchanged** — this only changes what happens to a fact once it's approved and published.

## Goals

- Discovery-first browsing: category-filterable, significance-sorted grid as the landing experience (figures, events, dynasties, concepts together).
- Show the individual atomic facts on each entry's detail page — not just the synthesized prose summary — each with its source citation.
- Full-text search across entry name, transliteration, **and fact text** (e.g. searching "Kashgar" surfaces entries whose facts mention Kashgar, not just entries named Kashgar).
- Filter/browse entries by source book.
- Citations deep-link into the book reader at the cited page.
- Add History Book as a new top-level menu item, additive alongside Dictionary.

## Non-goals

- No changes to the extraction pipeline, fact merge/dedup logic, or admin staging review workflow.
- No timeline/chronological view — there's no structured date field today (dates live loosely inside `transliteration`/fact text); adding one is a separate future effort if pursued.
- No changes to the Neo4j knowledge graph — history extraction and the graph pipeline remain independent, as they are today.
- **No changes to the existing Dictionary "history" tab** (`HistoryDictionaryPanel.tsx`, `/history-dictionary` router). It keeps querying `history_dictionary` fully unfiltered, exactly as today. Since some AI-extracted Uyghur entries already exist live, this means those entries will appear in **both** Dictionary and History Book — that overlap is an accepted, explicit decision, not an oversight.
- No physical separation of `history_dictionary` into per-feature tables. `is_ai_generated` is a fully reliable discriminator given facts are never populated for world-history terms, and the new `history_facts`/`history_fact_citations` tables (below) already contain only Uyghur-history data by construction, since world-history rows never pass through `approve_staging_term`. A real table split was considered and deferred: `history_dictionary`/`history_dictionary_staging` are targeted by actively-changing pipeline code (`HistoryExtractionService`, `DictionaryStagingService`, batch extraction, admin endpoints), and a rename/migration there is not worth the risk for a naming/purity win with no new capability. Revisit if History Book ever needs a field that must never exist on world-history rows.

## Data model

### Why a new normalized read-model (vs. querying the JSONB directly)

`history_dictionary.facts` (JSONB) remains the source of truth for the admin review/approval workflow — untouched. But the JSONB shape can't be efficiently full-text-searched or filtered by source book at scale (`jsonb` scans have no real index support for either). Two new tables give real indexed search and book-filtering, populated from the JSONB at the one clear write funnel: `DictionaryStagingService.approve_staging_term`.

A denormalized-columns approach (tsvector + book-id array directly on `history_dictionary`) was considered and rejected in favor of full normalization — a normalized `history_facts`/`history_fact_citations` pair is the more scalable long-term model and keeps fact-level and citation-level indexing independent.

### Schema

```sql
-- 081_create_history_facts.sql

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

`to_tsvector('simple', ...)` is used (not an English/language-specific config) since the content is Uyghur script — `simple` does word splitting without English stemming, which is the correct baseline for a language Postgres has no dedicated text search config for.

`history_dictionary.category` and `.significance_score` are already indexed (migration 079) — no changes needed there for the landing grid.

### Sync strategy: delete-and-reinsert on approval

`history_facts` / `history_fact_citations` only ever contain `status == 'active'` facts (rejected and unresolved-conflict facts stay inside the staging JSONB, admin-only, never published). On every `approve_staging_term` call — both first-time publish and re-publish via an `entry_type='enrichment'` staging candidate — the sync step:

1. `DELETE FROM history_facts WHERE dictionary_id = :id` (cascades to citations)
2. Re-insert one `history_facts` row per active fact from `staging.facts`, and one `history_fact_citations` row per citation on that fact

This runs in the same transaction/commit as the existing `history_dictionary` update in `approve_staging_term`, so the normalized tables are always an exact snapshot of what's currently live — no incremental upsert logic, no drift to reason about between commits.

### Backfill

A one-time script materializes every existing published `history_dictionary` row's `facts` JSONB into the new tables (same materialization logic as the sync step, run once against all rows with `status` implicitly "already published" — i.e. every row in `history_dictionary` today). Must be idempotent/safe to re-run (delete-and-reinsert per row, same as the live sync path).

## Backend API

New public, unauthenticated read endpoints (mirrors the existing public `/history-dictionary` endpoints' auth posture — read-only historical content, no login required):

Every endpoint filters `history_dictionary.is_ai_generated = TRUE` — this is the Uyghur History Book scope boundary, applied at the query level, not left implicit.

- `GET /history-book/entries?category=&book_id=&q=&sort=significance|alphabetical&page=&page_size=`
  Paginated list, `WHERE is_ai_generated = TRUE`. `q` searches `term`/`transliteration` (existing trigram index) OR fact `search_vector`, deduped. `book_id` filters via `history_fact_citations`. Default sort: `significance` desc.
- `GET /history-book/entries/{id}`
  Full detail (404 if `is_ai_generated = FALSE`, i.e. a world-history id): `term`, `transliteration`, `category`, `significance_score`, `significance_reason`, synthesized `definition`, and `facts: [{id, text, citations: [{book_id, book_title, volume, pages}]}]`.
- Letter-group/stats equivalents, scoped to `is_ai_generated = TRUE`, needed for the landing grid facets — these are new, `is_ai_generated`-scoped queries, not a reuse of the existing unfiltered `/history-dictionary/letter-groups`/`/stats`.

The existing admin endpoints (`admin_history_dictionary_router.py`) and the public `/history-dictionary` router are unaffected — this is an additive new router.

## Frontend

- **New top-level nav item**: تارىخنامە (History Book), added alongside Dictionary. `DictionaryView.tsx` and its "history" tab (`HistoryDictionaryPanel.tsx`) are **not modified or removed** — see Non-goals.
- **`HistoryBookView.tsx`** — landing page: category filter (figure/event/dynasty/concept), significance-sorted grid, search bar (term + transliteration + fact text), source-book filter.
- **`HistoryBookEntryView.tsx`** — detail page: synthesized prose definition, plus an expandable structured list of individual facts. Each fact's citation(s) deep-link into the book reader at the cited page.
  - *Open item to confirm during planning*: verify the book reader supports a page-anchor route (likely already used by RAG chat citations) so the deep link can reuse existing routing rather than adding new reader capability.

## Testing

- Repository/service tests for the `approve_staging_term` sync step: first publish, re-publish via enrichment (facts fully replaced, no duplicates/orphans), rejected/conflict facts never materialized.
- Backfill script test: idempotent on re-run, correct row counts against a fixture set of published entries.
- API tests: pagination, category filter, book filter, combined term+fact-text search, detail endpoint shape, and the `is_ai_generated` scope boundary (a world-history entry never appears in list/search results and its detail id 404s).
- Frontend tests: grid rendering/filtering, search-as-you-type, citation deep-link generation.

## Open questions for implementation planning

1. Exact book-reader deep-link route/mechanism (confirm reuse vs. net-new).
