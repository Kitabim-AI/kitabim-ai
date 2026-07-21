# RAG Deterministic Router — Design

`DeterministicRAGHandler` (`packages/backend-core/app/services/rag/agent/deterministic_handler.py`) is one of two RAG query handlers in the system. It replaces LLM-driven ADK ReAct tool-call sequencing (used by `LLMRoutedRAGHandler`, see `LLM_ROUTED_RAG_DESIGN.md`) with a deterministic Python decision tree built on extracted signals and conditional LLM intent classification.

Handler selection is controlled by the `use_deterministic_router` system config (default `false`): `HandlerRegistry` tries `DeterministicRAGHandler` first, and falls back to `LLMRoutedRAGHandler` (which always matches) otherwise. Toggling the config routes all chat traffic to one handler or the other without a deploy.

---

## Why a deterministic router

The alternative — `LLMRoutedRAGHandler` — delegates all tool-call sequencing to an LLM interpreting a natural-language system prompt (`AGENT_SYSTEM_PROMPT` in `prompts.py`). That means:

- Up to 6 LLM round-trips just for routing, before answer generation
- Non-deterministic — the same question can take a different tool-call path across calls
- Harder to debug ("why did the agent call search_chunks before find_books_by_title?")

`prompts.py`'s routing logic already *is* a decision tree written in English — every numbered step is effectively an `if/elif` branch. `DeterministicRAGHandler` writes that same tree directly in Python, using an LLM only where genuinely necessary: coreference resolution, intent classification, and multi-question splitting.

---

## Architecture

```
[Question + QueryContext]
        │
        ├──► DB Check (fuzzy title/author)
        ▼
┌───────────────────────────┐
│  1. Unified Query Analyzer│  (structured JSON LLM call — extracts intent & signals)
└───────────────────────────┘  (resilient Python keyword fallback on error)
        │ signals: is_current_page_query, is_volume_shift, target_volume,
        │          needs_rewrite, catalog_subtype, dictionary_subtype,
        │          quran fields, intent, is_composite/sub_questions
        ▼
┌───────────────────────────┐
│  2. Coreference Resolver  │  (conditional LLM — only when needs_rewrite=True)
└───────────────────────────┘
        │ possibly updates enriched_question
        ▼
┌───────────────────────────┐
│  3. Intent Classifier     │  (reads pre-extracted intent, or falls back to a
└───────────────────────────┘   dedicated classification LLM call)
        │
        ▼
┌───────────────────────────┐
│  4. Execution Router      │  (google.adk.workflow.Workflow — picks and runs
└───────────────────────────┘   one of 10 fixed path nodes)
        │ observations list (same format LLMRoutedRAGHandler produces)
        ▼
[_grade_context → answer_builder]  (shared with LLMRoutedRAGHandler)
```

---

## Stage 1: Unified Query Signal Analyzer

A hybrid stage combining a deterministic database-level metadata check with a single structured LLM call.

### 1a. DB Metadata Check (Deterministic)
`extract_signals()` checks the database for fuzzy/exact title matches (`has_title`, via `find_books_by_title_in_db`) and author matches (`has_author`, via `BooksRepository.find_books_by_author_in_question`).

### 1b. LLM Query Analysis (Semantic)
`_llm_analyze_query()` issues a structured LLM call (`GenerateContentConfig(response_mime_type="application/json")`) that extracts, in one round-trip:
- `is_current_page_query`, `is_volume_shift`, `target_volume`
- `needs_rewrite` / `rewritten_question`
- `catalog_subtype` (`author_of` | `books_by` | `general`)
- `dictionary_subtype` (`uyghur_definition` | `history_term` | `english_uyghur` | `spelling` | `names` | `proverbs` | `synonyms` | `general`) and `dictionary_term`
- `quran_surah`, `quran_ayah`, `quran_query`
- `intent` (`catalog` | `dictionary` | `identity` | `summary` | `relationship` | `passage` | `quran`)
- `is_composite` / `sub_questions` (multi-question decomposition, extracted directly here rather than via a separate split call)

**Resilient fallback:** if the LLM call fails, `extract_signals()` falls back to local Python keyword/regex heuristics (Quran keyword list, dictionary keyword heuristics, volume-shift keyword list with next/previous detection, Uyghur pronoun-token matching) so the handler stays available even if the LLM call errors.

---

## Stage 2: Coreference Resolver

Merged directly into Stage 1b — the same LLM call resolves pronouns/coreferences against chat history in-place and returns the standalone question as `rewritten_question`, saving a separate round-trip.

**Resilient fallback:** if Stage 1b fails, coreference detection falls back to local Python pronoun-token matching (`UYGHUR_PRONOUN_TOKENS`, punctuation-stripped word matching).

---

## Stage 3: Intent Classifier

`classify_intent()` returns the intent extracted in Stage 1b directly — no extra LLM call in the normal path.

**Resilient fallback** (only reached if Stage 1b failed and `intent` isn't already in `signals`): skip-heuristics resolve the common cases without a call (`has_author and not has_title` → `passage`; `is_volume_shift` → `passage`; `in_reader and not has_title and not has_author` → `passage`); anything else falls to a dedicated classification LLM call with few-shot Uyghur examples, defaulting to `passage` on failure.

---

## Stage 4: Execution Router

Pure Python route selection wrapped in a `google.adk.workflow.Workflow`, defined in `graph_router.py`. `execute_path()` calls `run_path_selection_workflow()`, which:

1. Computes the route via `_select_route(intent, signals)` — a plain Python precedence chain (no LLM/ADK involved in the decision itself):

   ```python
   if top_intent == "current_page" and signals["in_reader"]: return "current_page"
   if intent == "quran": return "quran"
   if intent == "dictionary": return "dictionary"
   if intent == "catalog": return "catalog"
   if signals["has_title"]: return "named_title"
   if signals["has_author"] and not signals["has_title"]: return "named_author"
   if signals["is_volume_shift"] and (signals["in_reader"] or signals["has_context_books"]): return "volume_shift"
   if signals["in_reader"] and not has_title and not has_author: return "in_reader_only"
   if signals["has_context_books"]: return "context_books"
   return "open"  # DEFAULT_ROUTE
   ```

2. Builds a `Workflow` graph with one node per route, each wrapping the corresponding `DeterministicRAGHandler._path_*()` method, and runs it through `google.adk.runners.Runner` + `InMemorySessionService`. This is the ADK layer this handler shares with `LLMRoutedRAGHandler` — here it executes a fixed graph rather than letting an LLM pick the next node.
3. Six of the ten route nodes carry an unconditional graph edge into a shared `universal_fallback_node` (see below); `catalog` has its own inline conditional fallback instead, since it only widens scope when the strict catalog lookup found nothing.
4. Tool-call lifecycle events (`tool_call`/`tool_result`) are wrapped as `types.Content` to survive ADK's one-output-per-node constraint, then unwrapped back into the same dict shape the frontend already expects.

**Observations envelope format** (must match what `_grade_context` and `_extract_used_book_ids` expect — identical to what `LLMRoutedRAGHandler` produces):
```python
observations.append({
    "tool": "search_chunks",
    "args": {...},
    "result": {"ok": True, "found_count": N, "chunks": [...], ...},
})
```

### The 10 routes

| Route | Triggers | Tool sequence |
|-------|----------|----------------|
| `current_page` | `top_intent == "current_page"` and `in_reader` | `get_current_page()` |
| `quran` | `intent == "quran"` | `search_quran(surah, ayah, q)` |
| `dictionary` | `intent == "dictionary"` | One of 7 tools by `dictionary_subtype` (`lookup_uyghur_word`, `lookup_history_term` [+ `search_language_sources` if empty], `translate_english_to_uyghur`, `check_word_spelling`, `lookup_uyghur_name`, `lookup_proverbs`, `lookup_synonyms`, or `search_language_sources` for `general`); falls back to `search_chunks(book_ids=None)` if every dictionary tool found nothing |
| `catalog` | `intent == "catalog"` | `catalog_subtype` picks `get_book_author` / `get_books_by_author` / `search_catalog`; if that strict lookup found nothing, falls back inline to `search_books_by_summary` → `search_chunks` → universal fallback |
| `named_title` | `has_title` | `find_books_by_title` (reused if already called this turn), then intent-specific: `summary`/`identity` → `get_book_summary` (+ `search_chunks` fallback if empty); `relationship`/`passage` → `search_chunks` |
| `named_author` | `has_author` and not `has_title` | `get_books_by_author` (reused if already called) → `search_chunks(author_book_ids)` |
| `volume_shift` | `is_volume_shift` and (`in_reader` or `has_context_books`) | `get_sister_volumes(source_book_id)` → `search_chunks(target_volume_id or all_sister_ids)` |
| `in_reader_only` | `in_reader` and not `has_title` and not `has_author` | `search_chunks(current_book_id)` |
| `context_books` | `has_context_books` | intent-specific over `context_book_ids`: `identity` → `search_books_by_summary` (verify) → `get_book_summary`; `summary` → `get_book_summary` (+ `search_chunks` fallback if empty); `relationship`/`passage` → `search_chunks` |
| `open` (default) | none of the above matched | intent-specific, global scope, capped to top 5 books for chunk search: `identity`/`summary` → `search_books_by_summary` → `get_book_summary`; `relationship` → `search_books_by_summary` → `search_chunks`; `passage` → `search_chunks(book_ids=None)` |

### Universal Fallback

Applies automatically after `named_title`, `named_author`, `volume_shift`, `in_reader_only`, `context_books`, and `open` (and inline after `catalog` when its strict lookup found nothing). Triggers when the last `search_chunks` call returned fewer than 4 chunks or its top score is below `CONTEXT_SWITCH_SCORE_THRESHOLD` (0.72):
1. If `search_books_by_summary` hasn't already run this turn, run it to rediscover candidate books, then re-run `search_chunks` with the new book IDs.
2. If still thin (or summary search already ran), run `search_chunks(book_ids=None)` — global scope.

### Multi-Question

`_run_sub_question` runs Stages 3+4 per sub-question with an isolated `observations` list (avoids dedup races between concurrently-running sub-questions). When more than one sub-question is present, `_merge_sub_question_streams` runs them **concurrently** via an `asyncio.Queue` fan-in, interleaving progress events by arrival order rather than sequentially. All sub-question observations are merged before `_grade_context`.

Coreference resolution (Stage 2) runs on the original question before splitting — sub-questions inherit the already-resolved context and are not independently checked for `needs_rewrite`.

---

## Model Configuration

`_llm_analyze_query()` and the intent-classification fallback both call `build_text_llm(ctx.agent_model)` — the same `ctx.agent_model` resolution `LLMRoutedRAGHandler` uses (`gemini_agent_loop_model` system config, falling back to `gemini_chat_model`; `gemini-3.1-flash-lite` by default). There is no separate model configured for this handler's LLM calls.

---

## Shared with `LLMRoutedRAGHandler`

| Component | Notes |
|-----------|-------|
| `_grade_context`, `_extract_used_book_ids`, `_populate_ctx_from_observations` | Imported from `llm_routed_handler.py` — identical post-processing for both handlers. |
| `answer_builder.py` (`generate_answer_stream`) | Same answer synthesis and citation instructions. |
| `QueryContext` | Same request-scoped context object. |
| Event protocol (`planning`, `decompose`, `tool_call`, `tool_result`, `grading`, `answer_start`, `chunk`, `answer_end`) | Same shape, so the frontend doesn't need to know which handler is active. |
| Tool implementations in `tools.py` | Both handlers call the same underlying `_run_*` functions. |

---

## LLM Call Comparison

| Scenario | `LLMRoutedRAGHandler` (agent decides each call) | `DeterministicRAGHandler` |
|----------|--------------------------------------------------|----------------------------|
| Catalog question ("who wrote X") | 1–2 agent reasoning calls | 1 analyze call |
| Current page question | 1–2 agent reasoning calls | 1 analyze call |
| Named title, clear passage | 2–3 agent reasoning calls | 1 analyze call |
| Follow-up with pronoun + content | 3–5 agent reasoning calls | 1 analyze call |
| Multi-question (3 sub-questions) | 4–6 agent reasoning calls | 1 analyze call (sub-questions extracted in the same call; each sub-question may add 1 classification call only on Stage-1 failure) |

---

## Known Limitations

- A wrong intent classification has no self-correction the way an LLM agent can sometimes recover mid-loop.
- Novel question types not covered by the fixed intent set default to `passage`, which is usually — but not always — the right retrieval shape.
- The universal fallback mitigates most misroutes by widening scope when results are thin, regardless of which path was taken.
