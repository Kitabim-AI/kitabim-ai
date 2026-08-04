# Keyword Search – Practical Rework Plan (TODO)

**Branch:** `feature/graph-rag-with-GDS`
**DB constraint:** Google Cloud SQL for PostgreSQL – no BM25/ParadeDB extension available. Everything below uses stock Postgres FTS.
**Status:** Planning (no code changes yet).

---

## Guiding principle

Stop keyword-searching every word of every question. The keyword (lexical) leg runs
**only when the user genuinely wants an exact match**. All other questions are answered by
**vector + graph** retrieval (still "hybrid"). This removes the common-word flood
(e.g. "who is king Babur" no longer OR-matches "who/is/king").

### Decisions (confirmed)

| Topic | Decision |
|---|---|
| When keyword search runs | (a) quoted text `"..."` / `«...»` / `“...”`, **or** (b) explicit UI "Exact phrase" mode |
| `«...»` ownership | Reclaimed exclusively for phrase-search intent. It no longer signals a quoted book title — the existing title-scoping quote-match must migrate off it (see 1.7) |
| Match type | Exact **contiguous phrase** (`phraseto_tsquery('simple', ...)` / `<->`) |
| Phrase mode blending | **Keyword-only** (no vector/graph fusion in phrase mode) |
| Non-phrase questions | **Vector + graph only** (keyword leg OFF) |
| Page-finding requests | Natural-language requests that contain a quoted phrase (e.g. `find pages with "xx yy zz"`) route to exact phrase search and return page/chunk hits |
| Config flag behavior | Deprecate/remove `rag_hybrid_search_enabled`; explicit exact phrase search is not controlled by the old hybrid-fusion flag |
| Result cap | **10** records max from the keyword leg |
| Home search box | **Tabs**: "Find books" (title/author/category + exact phrase in content) vs "Ask" |

---

## Phase 1 – Gate the keyword leg behind exact-phrase intent

Goal: keyword leg is OFF by default; ON only for exact-match intent. Non-phrase questions run vector + graph.

- [x] **1.1 Add phrase-intent detection** (`services/rag/phrase_intent.py`, `detect_phrase_intent()`):
  - [x] Detect quoted spans: `"..."`, `«...»`, `“...”` → return the quoted phrase(s).
  - [x] `«...»` now belongs to phrase-search intent, not book-title scoping — see 1.7 for the required migration of the existing title-quote-match code so the two features stop colliding.
  - [x] Accept an explicit `exact_phrase` flag from the request (for the UI mode).
  - [x] Classify quoted natural-language page-finding requests – e.g. `find pages with "..."`, `which pages mention "..."`, `show me where "..." appears` – as exact content lookup. (English markers only for now — Uyghur-language equivalents need vetted, non-machine-translated phrasing from product/content before being added.)
  - [x] Return a small result object: `PhraseIntent(is_exact: bool, phrases: list[str], is_page_finding: bool)` — extended from the original two-field sketch to support ANDed multi-phrase queries (resolved decisions) and the page-hit vs. synthesized-answer formatting split (1.2).
- [x] **1.2 Route in the QA workflow**:
  - [x] `vector_search`/(removed) `_search_chunks` in `services/rag/retrieval.py` are now vector-only, unconditionally — the keyword leg no longer blends with vector results at all (not gated by a flag; the fusion mechanism itself was removed, see 1.4).
  - [x] `ChatOrchestrator.stream_response` (`services/chat/orchestrator.py`) — the real chat entry point (`DeterministicRAGHandler` handles only fast-signal pre-processing, not full retrieval/answer generation) — gates on `detect_phrase_intent()` right after building `QueryContext`: exact-phrase questions skip the ADK retrieval agent's LLM-driven tool loop (no vector/graph tool calls at all) and go straight to `run_exact_phrase_retrieval()` (new `services/chat/exact_phrase.py`), which calls the keyword-only leg and packages hits as a `search_chunks`-shaped observation.
  - [x] Page-finding exact requests (`PhraseIntent.is_page_finding`) skip reranking/grading and the LLM answer agent entirely; a new `page_hits` SSE event carries structured hits (`format_page_hits`), with a plain-text summary (`summarize_page_hits_as_text`) persisted to conversation history. Non-page-finding exact-phrase questions still get an LLM-synthesized answer, built only from the exact-phrase leg's `graded_context`.
  - [x] Multiple quoted phrases are ANDed via `exact_phrase_chunk_search` (intersecting per-phrase `keyword_search` results by `(book_id, page_number, chunk_index)` at the time). **Superseded 2026-08-04**: `keyword_search` was migrated from `chunks.text_search` to `pages.text_search` (see the Post-launch update at the end of this doc), so the intersection key is now `(book_id, page_number)` — a hit is a whole page, not a chunk.
  - [x] **Scope = current scope**: reader mode passes `[book_id]`; global mode passes `ctx.context_book_ids` (or `None` for all books) — same scope resolution the rest of the turn already uses.
  - [x] Graph lookup (`graph_entity_lookup`) rides along with the ADK `search_chunks` tool (`_run_search_chunks`) for non-phrase questions, unchanged; it's structurally unreachable for exact-phrase questions since the ADK retrieval agent loop (which is what calls that tool) never runs for them.
  - [x] New API surface: `ChatRequestDTO.exact_phrase` / `ChatRequest.exactPhrase` (defaults `false`) thread the explicit UI "Exact phrase" mode flag from `chat_router.py` through to `detect_phrase_intent()`.
- [x] **1.3 Replace the OR tsquery with exact phrase** in `ChunksRepository.keyword_search` (was `_format_tsquery_expression`, now removed):
  - [x] Uses `phraseto_tsquery('simple', :phrase)` for contiguous-phrase matching; `keyword_search`'s first param renamed `query_text` → `phrase` to match (its only caller, `exact_phrase_chunk_search`, was updated).
  - [x] Documented in the method docstring as FTS phrase-exact, not raw substring exact.
  - [x] Existing `work_mem` / `statement_timeout` guards kept as-is.
- [x] **1.4 Remove the old hybrid-fusion flag path**: `rag_hybrid_search_enabled` removed from `retrieval.py`, `db/seeds.py`; the RRF fusion machinery itself (`_fuse_rrf`, `_search_chunks`'s hybrid branch, `RRF_K` constant) deleted rather than left dead, since nothing calls it anymore. The agent-supplied `keywords` tool parameter (`search_chunks` ADK tool, `vector_search`) was also removed — it existed solely to feed that fusion path. `rag_keyword_extraction_enabled` / `gemini_keyword_model` were not present in the codebase (nothing to remove). No replacement kill-switch flag was added, per the plan's default.
  - Existing `system_configs` rows for `rag_hybrid_search_enabled` in already-deployed databases are left in place (harmless, unread) — `seeds.py` has no deletion mechanism for existing keys.
- [x] **1.5 Tests**: `rag_phrase_intent_test.py` (phrase-intent detection: quotes/flag/page-finding), `chunks_repository_test.py` (phraseto_tsquery shape, phrase param), `rag_retrieval_test.py` (exact_phrase_chunk_search AND/limit/no-intersection), `chat_exact_phrase_test.py` (observation wrapping, page-hit formatting), `test_adk_orchestrator.py` (page-finding bypasses answer agent; non-page-finding still synthesizes from the exact-phrase leg only, retrieval agent never runs either way).
- [x] **1.6 Update stale docs**: `AGENTS.md`'s Production section (line ~54) lists `postgres` alongside `neo4j`/`redis` as a "stateful database container" — production Postgres is **Cloud SQL**, not a container (confirmed via `deploy/gcp/.env`'s `DATABASE_URL` pointing at a private Cloud SQL IP). Fix that line and add an explicit Cloud SQL callout to the Production section. (Note: line 43's "PostgreSQL runs as a standalone service on the host machine" is scoped to **Local Dev** and is correct as-is — do not touch it.)
- [x] **1.7 Migrate book-title quote matching off `«...»`**: today `«Title»` in a question is treated as an exact book-title reference (a real, organic user-typing convention — Uyghur users write `«Title»` naturally, the frontend doesn't insert it). Once `«...»` means phrase-search intent, this collides: `«Tarikh-i-Rashidi» kitabida Babur heqqide nemə deyilgen?` would wrongly route to keyword-only exact-phrase search instead of resolving the book and answering via vector+graph.
  - [x] `find_books_by_title_in_question` (`services/rag/retrieval.py`): dropped the `«title»` exact-match branch; always uses normalized fuzzy/word-prefix matching now (was already the fallback for when no `«»` was present). Bonus: fixes a pre-existing false-negative where a quoted title with a natural Uyghur suffix attached (e.g. `«ئانا يۇرتنى»`) failed exact-string comparison and returned no match at all.
  - [x] `entity_matches_question` (`services/rag/utils.py`): dropped the `is_quoted` (`«»`/`""`) signal used for single-word title matching; relies on the remaining heuristics (sentence-start position, title-indicator words like كىتابى/ناملىق/رومانى/ھەققىدە). This is a strict narrowing (one fewer way to match) — no test found a case where it drops legitimate matches beyond the quote itself, but this is only as good as the test cases written; watch for reports of single-word titles no longer resolving.
  - [x] `books_repository.py` (`find_author_by_title_in_question`, `find_volume_info_by_title_in_question`): same migration — both now always use fuzzy `_entity_matches_question`.
  - [x] `find_books_by_title` agent-tool docstring (`agent/tools.py`) and `find_books_by_title_in_question` docstring (`retrieval.py`) updated to stop advertising the removed quoted-exact-match behavior.
  - [x] **Tests**: `rag_service_utils_test.py`, `test_retrieval_subset_matching.py`, `books_repository_test.py` — quoted-with-suffix titles now resolve; quoted vs. unquoted give identical results; a quoted single-word title with no other signal no longer matches.

**Acceptance:** `"who is king Babur"` → vector + graph only (no keyword flood).
`"king Babur"` (quoted) or Exact-phrase mode → keyword-only exact match, ≤10 rows.
`find pages with "xx yy zz"` / `which pages mention "xx yy zz"` → exact page/chunk hits in the current scope, not a normal synthesized QA answer.
`«Tarikh-i-Rashidi» kitabida Babur heqqide nemə deyilgen?` → book resolved via fuzzy/positional title matching (not the quote), question answered via vector + graph — not routed to the keyword-only leg.

---

## Phase 2 – Split top-K into three configs + cap keyword results

Goal: replace the single, overloaded `rag_top_k` with **three independent per-leg limits** so vector, keyword, and graph retrieval are tuned separately – and the keyword leg can never flood (the "which page has 'king'" guard).

### 2A – Config split

Today one key `rag_top_k` (default `25`) drives the vector/fused chunk cap everywhere (`retrieval.py`, `chat/orchestrator.py`, `agent/tools.py`); graph retrieval (`graph_entity_lookup`) has **no cap at all** on its main matching path (a `top_k=10` exists in `graph_repository.py`, but on `run_gds_knn_similarity` — the unrelated offline entity-resolution/clustering job, not RAG chat retrieval; see 2.3). Split into:

| New config key | Controls | Default | Replaces / today |
|---|---|---|---|
| `rag_vector_top_k` | vector similarity leg (and final fused chunk cap) | `25` | renames `rag_top_k` |
| `rag_keyword_top_k` | keyword (exact-phrase) leg | `10` | new (the cap below) |
| `rag_graph_top_k` | graph retrieval leg | `10` | new — `graph_entity_lookup()` had no cap to promote (see 2.3) |

- [x] **2.1 Seed the three keys** in `db/seeds.py`; keep the numeric-config convention (read via `SystemConfigsRepository.get_value(key, default)` + `int()` parse, like `rag_top_k`).
- [x] **2.2 Migrate `rag_top_k` → `rag_vector_top_k`** at every `system_configs` read site: `retrieval.py`, `chat/orchestrator.py`, `agent/tools.py` (the Quran vector-search leg reuses the same cap — it's also pgvector similarity search), plus comment updates in `agent/config.py` and `deterministic_handler.py`. **Scoping decision**: went with a hard rename of the `system_configs` DB key (no fallback-read window — this whole plan ships as one deploy). Deliberately did **not** rename `settings.rag_top_k` / the `RAG_TOP_K` env var in `core/config.py` — that's only ever used as the fallback default value passed to `get_value()`, and renaming the env var would silently orphan any operator's existing `RAG_TOP_K` setting in `.env`/`deploy/gcp/.env` (confirmed a live value is set there locally) for near-zero benefit, since the DB config is the real source of truth.
- [x] **2.3 Wire `rag_graph_top_k`** into the actual RAG-facing graph retrieval path. **Correction to this plan's premise**: the `top_k=10` originally found via grep in `graph_repository.py` (`run_gds_knn_similarity`) belongs to the offline GDS entity-resolution/clustering job, not to `graph_entity_lookup()` (the function chat retrieval actually calls) — they're unrelated features that happen to share a file. `graph_entity_lookup()`'s B1/B2 matching stages had **no cap at all** (B3's fuzzy fallback has an unrelated hardcoded `limit=5`). Added a genuine new `top_k` param to `graph_entity_lookup()` (default 10, sorted by score descending before truncating — applied both on the cache-hit early-return and the freshly-computed path, while the *cached* value stays uncapped so a later call with a different top_k isn't stuck with a stale truncation), wired from `_run_search_chunks` (`agent/tools.py`) via a `rag_graph_top_k` config read.
- [x] **2.4 Wire `rag_keyword_top_k`** into the exact-phrase leg (see 2B) — not `keyword_search` directly, since Phase 1 changed the caller from the old RRF-fusion path to `exact_phrase_chunk_search`/`ChatOrchestrator.stream_response`; the cap is read there and passed through as `keyword_search`'s existing `limit` param.

### 2B – Keyword-leg hard cap

- [x] **2.5 Enforce the limit**: `ChatOrchestrator.stream_response` reads `rag_keyword_top_k` (default `10`) and passes it as `run_exact_phrase_retrieval(..., limit=...)` → `exact_phrase_chunk_search(..., limit=...)` → each `keyword_search(..., limit=...)` call, independent of the vector/graph caps. `keyword_search`'s own `ORDER BY rank DESC LIMIT :limit` (unchanged from Phase 1) enforces it in SQL.
- [x] **2.6 Guard single-common-token phrases**: unchanged from Phase 1 — the exact-phrase query (`phraseto_tsquery`) + `LIMIT` + existing `statement_timeout`/`work_mem` guards apply regardless of phrase length.
- [x] **2.7 Tests**: `rag_retrieval_test.py` (`graph_entity_lookup` top_k capping), `rag_system_config_top_k_test.py`/`rag_service_caching_test.py`/`rag_agent_tools_test.py` (updated to the renamed `rag_vector_top_k` key), `test_adk_orchestrator.py` (`rag_keyword_top_k` flows into the exact-phrase leg's limit). No `rag_top_k` fallback-read test needed — hard rename, no dual-read window (see 2.2).

**Acceptance:** vector/keyword/graph limits are independently configurable in system config; searching `"king"` returns at most `rag_keyword_top_k` (default 10) rows and never times out.

---

## Phase 3 – Home search box: multi-tab search

Goal: turn the home search box into a multi-tab search surface with a **fixed tab order** (static, no usage tracking).

### Tab set (final, fixed order)

| # | Tab | What it does | Backend | Status |
|---|---|---|---|---|
| 1 | **Ask** | Natural-language question → RAG (vector + graph) | chat/RAG flow | ✅ exists |
| 2 | **Books** | Find books by **title / author / category** | `books_repository` full-text | ✅ exists |
| 3 | **Quran** | Search by surah/ayah or verse text | `search_quran` | ✅ exists |
| 4 | **Content** | **Exact phrase inside book content** → matching books/pages | `phraseto_tsquery` over `chunks` (Phase 1), later migrated to `pages` (see Post-launch update) | 🆕 new |
| 5 | **Dictionary** | Uyghur word meaning | `lookup_uyghur_word` | ✅ exists |
| 6 | **Names** | Uyghur name origin/meaning | `lookup_uyghur_name` | ✅ exists |
| 7 | **History Terms** | Historical term lookup | `lookup_history_term` | ✅ exists |
| 8 | **Proverbs** | Proverb lookup | `lookup_proverbs` | ✅ exists |
| 9 | **Spell Check** | Check/correct Uyghur spelling | `check_word_spelling` | ✅ exists |
| 10 | **EN↔UG** | English↔Uyghur translation | `translate_english_to_uyghur` | ✅ exists |

### Tasks

- [x] **3.1 Frontend – multi-tab search box** in the home search component (`apps/frontend/src/components/library/`): renders the 10 tabs in the fixed order above (`searchTabsConfig.ts`), default tab "Ask" (`useHomeSearchTab`). New pieces: `SearchTabBar.tsx` (tab bar UI), `HomeSearchTabResults.tsx` (per-tab data fetching + result rendering, dispatches to `LookupResultsList`/`QuranResultsList`/`SpellCheckResultView`/book-grid), `useLookupSearch`/`useContentSearch`/`useSpellingCheck` hooks, `searchTabsService.ts` (REST calls for the 7 non-book tabs). `HomeView.tsx` keeps its existing Ask/Books book-fetch path (via `AppContext`'s `useBooks`) unchanged; the other 8 tabs fetch independently, gated so only the active tab's hook has a live query. Result-shape polish (loading/empty states, RTL, dark mode) follows the existing glass-morphism design system rather than a bespoke design pass — no separate `/ui-designer` round was run given the tabs reuse established list/card patterns almost directly.
- [x] **3.1A Chat parity requirement**: confirmed, not new work — every listed tool is already registered in the ADK agent's tool list (`adk_agent.py`: `search_chunks`, `find_books_by_title`, `get_books_by_author`, `search_catalog`, `search_quran`, `lookup_uyghur_word`, `lookup_uyghur_name`, `lookup_history_term`, `lookup_proverbs`, `check_word_spelling`, `translate_english_to_uyghur`, plus `search_language_sources`/`lookup_synonyms`), so natural-language prompts for every tab already route to the same backend capability the tab UI calls directly. No gating/routing code needed; this item was a verification pass, not an implementation gap.
  - [x] **Ask**: normal question → vector + graph RAG.
  - [x] **Books**: `find books by ...`, `books by author ...`, `books about ...` → catalog / book-title / author tools.
  - [x] **Quran**: `find ayah ...`, `search Quran for ...` → `search_quran`.
  - [x] **Content**: `find pages with "..."`, `which pages mention "..."` → exact phrase page/chunk hits (backend done — see 1.2's page-hit formatting).
  - [x] **Dictionary**: `what does ... mean?` → `lookup_uyghur_word`.
  - [x] **Names**: `what does the name ... mean?` → `lookup_uyghur_name`.
  - [x] **History Terms**: historical/person/place/event term prompts → `lookup_history_term`.
  - [x] **Proverbs**: `find a proverb about ...` → `lookup_proverbs`.
  - [x] **Spell Check**: `is ... spelled correctly?` → `check_word_spelling` (chat tool already existed; the tab itself needed a new public REST endpoint — see 3.3).
  - [x] **EN↔UG**: `translate ... to Uyghur` → `translate_english_to_uyghur`.
- [x] **3.2 "Content" tab (new) — backend**: `GET /api/books/content-search` (`services/backend/api/endpoints/books_router.py`) — exact-phrase search over `chunks.text` via `ChunksRepository.find_books_by_exact_phrase()` (new; `phraseto_tsquery` `EXISTS` subquery against `books`, grouped/deduped naturally since it selects `Book` rows directly), paginated (`page`/`pageSize` → `PaginatedBooks` with `total`). Guest/reader requests are restricted to `status == "ready"` and public/legacy-NULL visibility, matching every other book-listing endpoint in this router — admins/editors see private/draft book content too. **Superseded 2026-08-04**: `find_books_by_exact_phrase()` and the chunk-grouped `search_content_chunks()` it grew into were deleted; the endpoint now calls `PagesRepository.search_content_pages()` instead — see the Post-launch update below and `docs/superpowers/specs/2026-08-04-pages-content-keyword-search-design.md`.
  - [x] **Note**: this browse/discovery search is **separate** from the in-chat keyword retrieval leg. The `rag_keyword_top_k` cap applies **only to chat retrieval** to bound LLM context — it does **not** apply here; the endpoint paginates (infinite scroll) instead.
  - Frontend wiring (the tab UI calling this endpoint) is part of 3.1, not started.
- [x] **3.3 Existing tabs**: "Ask" and "Books" wire straight through the existing `AppContext`/`useBooks` book-search path (unchanged). "Quran", "Dictionary", "Names", "History Terms", "Proverbs", "EN↔UG" call their pre-existing `GET .../search?q=&limit=` routers via the new `searchTabsService.ts`. The one gap found in 3.1A's audit — `check_word_spelling` had no public REST route, only the chat tool — is closed by the new `GET /api/dictionary/check-spelling?word=` endpoint (`dictionary_router.py`), used by both the "Spell Check" tab and available for any future non-chat caller.
- [x] **3.4 Remember last-used tab** client-side (`localStorage`) — `useHomeSearchTab` (`apps/frontend/src/hooks/useHomeSearchTab.ts`) reads/writes `kitabim:homeSearchTab`, falls back to "Ask" for an empty or unrecognized stored value (e.g. from a future removed tab), and defends against `localStorage` being unavailable (private browsing). Tested in `useHomeSearchTab.test.tsx`.
- [~] **3.5 Infinite scroll on search results**: extended to the **Content** tab only (`useContentSearch` mirrors the existing `IntersectionObserver`/`loadMore` pattern). The 6 simple lookup tabs (Quran, Dictionary, Names, History Terms, Proverbs, EN↔UG) are single-shot, capped at `limit=20` via `useLookupSearch` — no pagination/infinite-scroll for those, since their backend routers only expose `limit`, not `skip`/`page` (see 3.6's last sub-item, still open). Books/Ask are unchanged (already had infinite scroll).
- [x] **3.6 Batch size = a new system config `collection_page_size` (default 40)**, replacing the hardcoded `COLLECTION_PAGE_SIZE = 40` in `hooks/useBooks.ts`. Applies to the library shelves and the search results alike (one source of truth).
  - [x] Seeded `collection_page_size` (default `40`) in `db/seeds.py`.
  - [x] Exposed via `GET /api/config` (`services/backend/main.py`) — now takes a `session` dependency, returns `{appId, collectionPageSize}`, read from `SystemConfigsRepository` with `int()` parse + 40 fallback.
  - [x] Frontend: `authService.ts` fetches it alongside `appId` in `initAppConfig()`, exposed via a new `getCollectionPageSize()` export; `useBooks.ts` and the new Content-tab hook (`useContentSearch`) both read it instead of a hardcoded constant.
  - [ ] Still open: the 6 lookup routers (dictionary/names/history/proverbs/english-uyghur/quran) only support `limit`, not `skip`/`page` — true pagination for those tabs (beyond the current `limit=20` single page) is unaudited/unbuilt.
- [x] **3.7 Shared types**: kept minimal by design — the Content-tab endpoint reuses the existing `PaginatedBooks`/`Book` schemas; the other 6 lookup tabs got small frontend-only interfaces in `searchTabsService.ts` (`DictionaryEntry`, `NameEntry`, `HistoryTermEntry`, `ProverbEntry`, `EnglishUyghurEntry`, `QuranAyah`, `SpellingCheckResult`) rather than new backend-shared types, since these are simple flat shapes only consumed by this one frontend surface.
- [~] **3.8 Tests**: backend — `check_spelling` endpoint covered in the new `dictionary_router_test.py` (known word / unknown word with suggestions). Frontend — `useLookupSearch.test.tsx` (debounce, min-length gate, stale-response race), `useContentSearch.test.tsx`, `useSpellingCheck.test.tsx`, `useHomeSearchTab.test.tsx` (localStorage persistence/fallback), `SearchTabBar.test.tsx` (fixed tab order, active state, click), `searchTabsService.test.ts` (field mapping, failure fallbacks). **Not covered**: a full `HomeView` integration test exercising tab-click → result-render end-to-end (only the underlying hooks/components are unit-tested in isolation); chat-parity prompts were verified by reading the existing ADK tool registration, not via new deterministic-eval test cases.

**Status:** Phase 3 is now fully implemented for the scope of 3.1/3.1A/3.3/3.4: the home search box is a working 10-tab surface (`HomeView.tsx` + `SearchTabBar`/`HomeSearchTabResults`), chat parity was confirmed pre-existing (no code changes needed), the one missing REST endpoint (spell check) was added, and the active tab persists across visits. Two items remain intentionally partial: 3.5/3.6's infinite-scroll-everywhere goal only covers the Content tab (the other 6 lookup tabs need `skip`/`page` support added to their routers first), and a full HomeView tab-switching integration test wasn't added (3.8).

**Acceptance:** `GET /api/books/content-search?q=...` returns books that literally contain the typed phrase, paginated, respecting guest visibility rules. All 10 tabs render in the fixed order, default to "Ask", and each queries its real backend. Chat parity holds for every tab's underlying capability. The last-used tab persists across page loads. Infinite scroll is not yet extended past the Content tab for the 6 simple lookup tabs.

---

## Resolved decisions

- **Multiple quoted phrases** in one query → **AND** (a result must contain all phrases).
- **Phrase search scope in chat** → **match the current scope** (reader = open book, global = all books).
- **Config flags** → `rag_hybrid_search_enabled` belongs to the old vector+keyword RRF fusion behavior and should be removed/deprecated with that behavior. Explicit exact phrase search does not need a flag by default; add a narrowly named kill switch only if operations require one.
- **`«...»` ownership** → reclaimed exclusively for phrase-search intent; it no longer signals a quoted book title. Existing title-scoping code that keyed off `«...»` migrates to its non-quote fallback heuristics (1.7).

---

## Out of scope (explicitly not doing now)

- BM25 / ParadeDB `pg_search` – **not possible on Cloud SQL**.
- LLM-based keyword extraction for general questions – dropped in favor of the explicit exact-phrase trigger.
- Corpus-statistics stopword table (`ts_stat` / IDF) – not needed once the keyword leg only runs on exact phrases; revisit only if broad keyword search returns.

---

## Post-launch update (2026-08-04): keyword search moved from `chunks` to `pages`

Everything above (Phase 1–3) shipped against `chunks.text_search` (migration `074_add_chunks_text_search.sql`). A single OCR'd page is split into multiple `chunks` rows, so both keyword legs described above returned multiple hits for the same page — the Content tab needed a chunk-grouping/dedup step, and the exact-phrase chat leg diluted `ts_rank` across chunk-level fragments. This was reworked to query `pages` directly instead, one row per page:

- Migration `076_add_pages_text_search.sql` added the same generated `tsvector` shape (`GENERATED ALWAYS AS to_tsvector('simple', text) STORED`) + GIN index (`idx_pages_text_search`) to `pages`.
- `PagesRepository.search_content_pages()` replaced `ChunksRepository.find_books_by_exact_phrase()` / `search_content_chunks()` (both deleted) for the home Content tab — see `docs/superpowers/specs/2026-08-04-pages-content-keyword-search-design.md` for the full design.
- `ChunksRepository.keyword_search()` — still that name, still that class, for historical/organizational reasons only — was rewritten to query `pages.text_search` instead of `chunks.text_search` for the chat exact-phrase leg (`retrieval.exact_phrase_chunk_search`). Its multi-phrase AND intersection key dropped `chunk_index`: it's now `(book_id, page_number)`.
- Migration `083_drop_chunks_text_search.sql` dropped `chunks.text_search` and `idx_chunks_text_search` once nothing queried them anymore.

See [CHAT_RAG_DESIGN.md](../../main/CHAT_RAG_DESIGN.md) and [CHUNKING_DESIGN.md](../../main/CHUNKING_DESIGN.md) for the living architecture docs.
