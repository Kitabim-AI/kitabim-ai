# History Dictionary Extraction: Fact-Based Model to Fix Compounding Duplication

**Date:** 2026-08-02
**Status:** Draft (pending review)

## Problem

`HistoryExtractionService` (`packages/backend-core/app/services/history_extraction_service.py`) extracts historical entities from OCR'd book pages using a 15-page sliding window (`batch_size=15`, `overlap=2`) and, for each window, asks the LLM to write a full freeform-prose `definition` per entity. When the same term reappears in a later window (matched via trigram/fuzzy similarity on the term name, which works correctly), `_stage_entity` merges it with a **pairwise LLM rewrite**: `CONSOLIDATION_PROMPT_TEMPLATE` takes the running merged text plus the new window's paragraph and asks the model to produce one deduplicated blob.

For a prominent figure who appears throughout a book, this merge runs once per overlapping window — dozens of times per book — and each merge's output becomes the next merge's "existing" input, with no memory of why earlier merges made the choices they did. In production this produces exactly the failure a real generated entry showed: the same clause ("سۇلتان سەئىدخاننىڭ ئوغلى") restated dozens of times with slightly different phrasing and citation lists, because the LLM's "eliminate duplicates" instruction is a best-effort judgment call over an ever-growing paragraph, and it silently misses restatements that differ only in spelling (`تارىخى رەشىدى` vs `تارىخى رەشىدىي` — different Perso-Arabic letter variants for the same word) or in word choice (خان vs ھۆكۈمران, both meaning "ruler"). A deterministic regex pass (`_clean_and_deduplicate_text`) exists on top but only catches exact-normalized-string matches, so it doesn't help with either failure mode.

The admin review UI (`HistoryStagingQueuePanel.tsx`) and its approve/reject/bulk-approve endpoints already exist and work correctly at the term-matching level — the problem is entirely in what ends up in the `definition` text by the time a human sees it, and in the fact that a human only ever sees the final compounded result, never an earlier point where a bad merge could be caught.

## Existing state

- `HistoryExtractionService.process_book_pages` (`history_extraction_service.py:227-286`) sorts pages, slides a window of `batch_size` (default from `system_configs.history_extraction_batch_size`, fallback 15) with `overlap=2`, and calls `_call_llm_extraction` per window.
- `_stage_entity` (`history_extraction_service.py:288-439`) is the merge entry point, called for every entity in every window. It branches three ways: matching pending staging row exists → `update_staging_term`; matching *AI-generated* live row exists → create a new staging row of `entry_type="enrichment"`; neither exists → create a new staging row of `entry_type="new"`. Non-AI-generated live rows are explicitly skipped (`existing_live.is_ai_generated` check, line 314) — that protection stays unchanged.
- Term-level matching already uses normalized trigram similarity (`find_matching_history_term`/`find_matching_staging_term` in `dictionary_repository.py:428-461`, via `_build_fuzzy_term_where`/`_sql_normalize_uyghur` at lines 21-46, and `normalize_uyghur_spelling` imported from `app/services/rag/utils.py`) — this pattern is reused for fact-text normalization below, not re-invented.
- `_call_llm_enrichment` (`history_extraction_service.py:183-225`) is the pairwise merge: short-circuits if either side is empty/a substring of the other, else calls `CONSOLIDATION_PROMPT_TEMPLATE`, else falls back to `_merge_definitions` + `_clean_and_deduplicate_text` (line-level dedup) if the LLM call fails.
- `batch_history_extraction_service.py` (Gemini Batch API path, gated by `gemini_batch_history_extraction_enabled`) reuses `EXTRACTION_PROMPT_TEMPLATE` directly (line 25) and calls `HistoryExtractionService._stage_entity` directly (line 246) — it has no separate merge logic, so every change below applies to both the interactive and batch extraction paths without a separate design.
- `HistoryDictionary` and `HistoryDictionaryStaging` ORM models (`packages/backend-core/app/db/models.py:925-989`) currently carry `definition: Text`, `sources: JSON` (list of `{id, book_id, book_title, volume, pages}`), plus staging-only `original_definition` and `entry_type`.
- `DictionaryStagingService.approve_staging_term`/`reject_staging_term` (`packages/backend-core/app/services/dictionary_staging_service.py:20-84`) copies `staging.definition` verbatim onto the live `HistoryDictionary` row on approve, guarded by the same `is_ai_generated` check.
- `admin_history_dictionary_router.py` exposes `POST /books/{book_id}/extract-history`, `GET/staging`, `POST /staging/{id}/approve`, `POST /staging/bulk-approve`, `DELETE /staging/{id}` — all admin-only via `require_admin`.
- This is unreleased, same-branch work: migration `079_create_history_dictionary_staging.sql` is part of this same branch's uncommitted-to-main changes, so any staging rows in a dev DB are test data, not something to preserve across the schema change below.

## Design

### Data model

New migration adds `facts JSONB NOT NULL DEFAULT '[]'` to both `history_dictionary` and `history_dictionary_staging`. Each element:

```json
{
  "id": 3,
  "text": "ھىجرىيە 915-يىلى (مىلادىيە 1509-1510) تۇغۇلغان.",
  "citations": [{"book_id": "...", "book_title": "...", "volume": 2, "pages": [343]}],
  "status": "active",
  "conflict_group": null
}
```

`status` is one of `active` (included in synthesis) / `rejected` (admin discarded) / `conflict` (blocks approval until resolved). `conflict_group` is a shared integer id across two or more facts flagged as contradicting each other.

The `sources` column is **removed** from both tables — "which books contributed to this term" is derived by aggregating `citations` across `active` facts when building an API response, replacing the two near-duplicate "find existing book_id entry, merge pages into it" blocks currently in `_stage_entity` (lines 334-342 and 375-383) with one code path.

`definition` stays as a column on both tables but becomes a cache: null (or stale) until synthesis runs; see "Synthesis" below.

Migration is a **clean cut-over**: `history_dictionary_staging` rows created under the old prose-only shape are not migrated — this feature is unreleased, so existing dev-DB staging rows are cleared and books are re-queued through the new extraction pipeline. Published `history_dictionary` rows (which do exist beyond this branch, or may by the time this ships) are **not** cleared — they keep their `definition`, gain `facts=[]`, and get lazily bootstrapped (below).

### Extraction: atomic facts, no window overlap

`EXTRACTION_PROMPT_TEMPLATE` changes so each entity's output is a `facts` array instead of one `definition` string — short, single-clause statements, each with its own `pages` (a window can legitimately cite different pages for different facts about the same entity):

```json
"facts": [
  {"text": "ياركەند خانلىقىنىڭ خانى، سۇلتان سەئىدخاننىڭ ئوغلى.", "pages": [40, 42]},
  {"text": "ھىجرىيە 915-يىلى تۇغۇلغان.", "pages": [343]}
]
```

The prompt instructs: state exactly one piece of information per fact; do not write a narrative paragraph; do not restate the same fact twice within your own output. This constrains within-window repetition, not just cross-window.

`process_book_pages`'s `overlap` parameter defaults to `0` (was `2`) — windows become `pages[0:15]`, `pages[15:30]`, ... instead of overlapping. With `overlap=2`, the two shared pages at each window boundary were independently re-extracted by two separate (non-deterministic-temperature) LLM calls, which could phrase the *same source sentence* two different ways — the exact scenario a downstream similarity filter finds hardest to catch. Removing the overlap eliminates that self-inflicted source of near-duplicates outright. Trade-off: a fact whose single source sentence spans exactly across a page break could be truncated in both adjacent windows; accepted, since a notable entity is virtually always discussed again elsewhere in the book. The parameter itself stays configurable (not hardcoded to 0) in case this trade-off needs revisiting.

### Merge pipeline

Runs in `_stage_entity`, replacing the current pairwise-prose merge (`_call_llm_enrichment`, `CONSOLIDATION_PROMPT_TEMPLATE`, `_merge_definitions`, `_clean_and_deduplicate_text` — all four deleted), whenever new candidate facts arrive for a term that already has existing facts (from a prior window, another book, or a live published entry). Three tiers, each candidate fact passing through until it's resolved:

1. **Deterministic (free, no API call).** Normalize both candidate and existing fact text with `normalize_uyghur_spelling` (same helper already used for term matching) and compare with a Python string-similarity ratio (`difflib.SequenceMatcher` — in-memory JSONB comparison, not a queryable column, so the SQL `pg_trgm`/`func.similarity` path used for term matching doesn't apply here). Above a high threshold (e.g. `>= 0.85`): auto-classify as duplicate, merge the citation into the existing fact, discard the candidate text. This directly fixes the reported bug (`تارىخى رەشىدى` vs `تارىخى رەشىدىي`) deterministically — no model involved, so it can't "miss it due to spelling issues" the way the current single LLM rewrite did.
2. **Embedding similarity (cheap).** Candidates tier 1 doesn't confidently resolve get embedded via the existing `GeminiEmbeddings` (already used for chunks/summaries) and compared by cosine similarity against existing facts. This catches semantic restatements that differ in wording rather than spelling (خان vs ھۆكۈمران). Candidates with low similarity to every existing fact are confidently new and skip tier 3 entirely — most facts are expected to resolve here or in tier 1, keeping tier 3 volume low.
3. **LLM classification (rare, structured, bounded).** Only candidates in the "related but not clearly resolved" similarity band go to one structured call per merge event: given the term, its existing active facts (numbered), and the remaining candidates, return per-candidate `{decision: new|duplicate|conflict, existing_fact_id, reason}`. This tier is required even with embeddings, because embeddings can't distinguish "duplicate" from "conflict" — two facts stating different birth years score as highly similar (same topic, same structure) but disagree; only a reasoning call can tell those apart. Replaces `CONSOLIDATION_PROMPT_TEMPLATE`; new prompt constant, structured JSON output (list of decisions), not a prose rewrite.

Applying decisions: `new` → append as an active fact. `duplicate` → merge citation into the target fact (same per-book page-union logic as today, now operating on one fact's citation list instead of the whole term's `sources`). `conflict` → both facts get the same new `conflict_group` id and flip to `status: "conflict"`, per your explicit choice to block auto-merge and require a human pick rather than silently keeping both.

If the tier-3 classification call fails (timeout, malformed JSON): candidates left unresolved are treated as `new` rather than dropped. Worst case is an extra fact a human prunes during curation — never silent data loss, and never corrupts existing facts, since facts are structurally isolated entries rather than a paragraph that gets rewritten in place.

### Synthesis

New `SYNTHESIS_PROMPT_TEMPLATE` (replacing the old merge-rewrite prompt's role): takes only `active` facts (excluding `rejected` and `conflict`-pending ones) and writes the final cohesive Uyghur prose `definition` in one shot, citing pages with the existing `[N]` convention. Unlike the old design, this call never chains against its own prior output — it always synthesizes fresh from the current curated fact set, so it cannot compound errors across repeated calls.

Explicitly triggered, never automatic — this sidesteps needing to track fact-set staleness at all:
- An admin clicks "Preview" to regenerate `definition` from whichever facts are `active` right now. Opening/expanding a staging item does not synthesize by itself; running Preview twice on an unchanged fact set just reproduces the same prose.
- Approve always re-runs synthesis unconditionally, so what goes live reflects the final, possibly human-edited, fact set — never a stale or skipped preview.

Terms that accumulate facts across many windows/books but are never opened for review never trigger a synthesis call — cost is paid only for terms a human actually looks at, unlike the old design where every single merge event triggered an LLM call regardless of whether anyone would ever see the result.

If synthesis fails at approve time: block the approve action with a clear error and leave facts untouched for retry, consistent with this codebase's existing circuit-breaker/no-silent-fallback convention (`/prompt-engineer` skill: "Do not add retry logic in service layer, breaker handles it") — no deterministic bullet-list fallback is written as if it were normal prose.

### Admin UI (`HistoryStagingQueuePanel.tsx`)

- The single `item.definition` paragraph block (lines 314-334) is replaced by a fact list: each `active` fact rendered as a short line with citation badges (`[book] page N`, replacing the current per-item `sources` footer at lines 337-349, which is deleted). `rejected` facts are collapsed under a "show rejected" toggle — kept for audit, not shown by default.
- `conflict` facts are grouped by `conflict_group` and visually flagged (distinct border color), with per-fact actions: keep this / keep other / keep both (admin can override the flagged conflict if they judge both are legitimately true) / edit text.
- A "Preview" action per item triggers on-demand synthesis. The existing enrichment side-by-side diff (`item.originalDefinition` vs `item.definition`, lines 316-330) is replaced with a fact-oriented summary line ("3 new facts, 2 merged as duplicates, 1 conflict") — informative given the new data shape, and cheaper than rendering two full paragraphs.
- The approve button (line 295-302) is disabled client-side while any fact in the item has `status="conflict"`, with an inline hint to resolve them first. Bulk-approve (lines 121-139) reports per-item results so items with unresolved conflicts are skipped and surfaced, not silently failed.

### API (`admin_history_dictionary_router.py`, `dictionary_staging_service.py`)

- New endpoint to resolve a single fact: `PATCH /history-dictionary/staging/{staging_id}/facts/{fact_id}` — body `{status: "active"|"rejected", text?: string}` (edit-and-accept in one call).
- New endpoint to trigger on-demand synthesis: `POST /history-dictionary/staging/{staging_id}/synthesize` — regenerates `definition` from current active facts, returns it without changing `status`.
- `approve_staging_term` (`dictionary_staging_service.py:20-84`) gains a guard: if any fact has `status="conflict"`, return a 409 (new `errors.staging_conflicts_unresolved` i18n key) instead of proceeding. On success, it unconditionally re-synthesizes `definition`, then copies both the curated `facts` and the fresh `definition` onto the target `HistoryDictionary` row.

### Live-entry enrichment & legacy data

Published `history_dictionary` rows gain `facts` (default `[]`). For a row published before this change (`facts=[]`, non-empty `definition`), the first time it's re-enriched by a later book's extraction run, the existing prose is opportunistically wrapped as a single "legacy fact" (`text: definition`, best-effort `citations` from the old `sources` list if present) so the merge pipeline has something to diff new facts against. This happens lazily, only when a term is actually touched again — no bulk backfill job. Rows with `is_ai_generated=False` are never touched by extraction at all (existing protection, unchanged), so they never need this bootstrap.

### Error handling summary

- Extraction call fails/returns malformed JSON → unchanged from today: log and skip that window (existing `_parse_json_object`/try-except pattern in `_call_llm_extraction`).
- Tier-3 classification call fails → unresolved candidates become `new` facts (see Merge pipeline above) — visible extra work for a human, never silent loss or corruption.
- Synthesis fails at approve time → block approve, surface the error, facts remain intact for retry (see Synthesis above).

### Testing

Per `/api-unit-tester` conventions (applied during implementation, not detailed here): unit tests for the tier-1 deterministic similarity filter (pure function, easy to exercise with known near-duplicate/distinct Uyghur fact pairs), tier-2/3 decision application given a mocked classification response, the approve-blocked-by-conflict guard, and legacy-fact bootstrapping for pre-existing live entries. The existing `history_extraction_service_test.py` and `history_extraction_job_test.py` need substantial rewrites since `CONSOLIDATION_PROMPT_TEMPLATE`, `_clean_and_deduplicate_text`, and `_merge_definitions` are deleted — scoped as implementation-phase work.

## Out of scope

- Bulk backfill/re-synthesis of already-published `history_dictionary` entries into fact form ahead of time — handled lazily on next enrichment instead (see Live-entry enrichment).
- Changing the term-level fuzzy matching (`find_matching_history_term`/`find_matching_staging_term`) — already correct, untouched by this design.
- A dedicated per-book review gate before facts can merge into a term's fact list — explicitly rejected in favor of extending the existing staging queue with fact-level curation, keeping one admin review surface instead of two.
