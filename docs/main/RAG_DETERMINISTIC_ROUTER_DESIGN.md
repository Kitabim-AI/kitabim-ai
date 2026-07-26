# RAG Deterministic Router — Design

`DeterministicRAGHandler` (`packages/backend-core/app/services/rag/agent/deterministic_handler.py`) is one of two RAG query handlers in the system. It replaces LLM-driven ADK ReAct tool-call sequencing (used by `LLMRoutedRAGHandler`, see `LLM_ROUTED_RAG_DESIGN.md`) with a deterministic Python decision tree built on extracted signals and conditional LLM intent classification.

Handler selection is controlled by the `use_deterministic_router` system config (default `false`): `HandlerRegistry` tries `DeterministicRAGHandler` first, and falls back to `LLMRoutedRAGHandler` (which always matches) otherwise. Toggling the config routes all chat traffic to one handler or the other without a deploy — but only for requests dispatched through `HandlerRegistry` in the first place (see [SYSTEM_DESIGN.md §6B](SYSTEM_DESIGN.md) for the full routing picture).

Separately, `ChatOrchestrator` (`packages/backend-core/app/services/chat/orchestrator.py`, [QUESTION_ANSWERING_DIAGRAM.md](QUESTION_ANSWERING_DIAGRAM.md#chatorchestrator-pipeline)) calls this handler's `_llm_analyze_query()` directly as a plain signal-extraction utility on every request it serves, regardless of `use_deterministic_router` — that flag only controls whether `DeterministicRAGHandler` runs as a full handler on the `HandlerRegistry` path; it does not gate `ChatOrchestrator`'s use of the same signal extractor.

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
        ▼
┌───────────────────────────┐
│  1. Unified Query Analyzer│  (structured JSON LLM call, with title/author
└───────────────────────────┘   lookup tool calls — max 3 model turns)
        │ (resilient DB check + Python keyword fallback on error)
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

A single structured LLM call that resolves book titles/authors via tool calling instead of a separate deterministic DB pass.

### LLM Query Analysis with Tool Calling
`_llm_analyze_query()` gives the model two tools — `find_books_by_title(question)` and `get_books_by_author(question)`, both thin wrappers over `_dispatch_tool_with_retry` — and lets it call them (manual function-calling loop against `client.aio.models.generate_content`, `automatic_function_calling` disabled) to resolve `has_title`/`has_author`/`matched_books`/`matched_author_books` itself before producing the final JSON. This replaces the old always-run DB metadata check with an on-demand one the model only triggers when the question actually names a book or author.

**Iteration limit:** the loop runs for at most 3 turns. After the first turn in which the model invokes a tool, `config.tools` is set to `None` so the next turn is forced to return final JSON instead of chaining further tool calls — the prompt also tells the model to stop once it finds a match or comes up empty, but the turn cap is the hard backstop. Exhausting all 3 turns without a final JSON response raises `ValueError("Too many tool call iterations in query analysis")`.

In the same round-trip, the structured JSON response also extracts:
- `is_current_page_query`, `is_volume_shift`, `target_volume`
- `needs_rewrite` / `rewritten_question`
- `catalog_subtype` (`author_of` | `books_by` | `general`)
- `dictionary_subtype` (`uyghur_definition` | `history_term` | `english_uyghur` | `spelling` | `names` | `proverbs` | `synonyms` | `general`) and `dictionary_term`
- `quran_surah`, `quran_ayah`, `quran_query`
- `intent` (`catalog` | `dictionary` | `identity` | `summary` | `relationship` | `passage` | `quran`)
- `is_composite` / `sub_questions` (multi-question decomposition, extracted directly here rather than via a separate split call)

**Resilient fallback:** if the LLM call fails for any reason, `extract_signals()` falls back to the old deterministic DB check (`find_books_by_title_in_db`, `BooksRepository.find_books_by_author_in_question`) for `has_title`/`has_author`, plus local Python keyword/regex heuristics (Quran keyword list, dictionary keyword heuristics, volume-shift keyword list with next/previous detection, Uyghur pronoun-token matching) for everything else, so the handler stays available even if the LLM call errors.

---

## Stage 2: Coreference Resolver

Merged directly into Stage 1 — the same LLM call resolves pronouns/coreferences against chat history in-place and returns the standalone question as `rewritten_question`, saving a separate round-trip.

**Resilient fallback:** if Stage 1 fails, coreference detection falls back to local Python pronoun-token matching (`UYGHUR_PRONOUN_TOKENS`, punctuation-stripped word matching).

---

## Stage 3: Intent Classifier

`classify_intent()` returns the intent extracted in Stage 1 directly — no extra LLM call in the normal path.

**Resilient fallback** (only reached if Stage 1 failed and `intent` isn't already in `signals`): skip-heuristics resolve the common cases without a call (`has_author and not has_title` → `passage`; `is_volume_shift` → `passage`; `in_reader and not has_title and not has_author` → `passage`); anything else falls to a dedicated classification LLM call with few-shot Uyghur examples, defaulting to `passage` on failure.

---

## Stage 4: Execution Router

Pure Python route selection wrapped in a `google.adk.workflow.Workflow`, defined in `graph_router.py`. `execute_path()` calls `run_path_selection_workflow()`, which:

1. Computes the route via `_select_route(intent, signals)` — a plain Python precedence chain (no LLM/ADK involved in the decision itself):

   ```python
   if top_intent == "current_page" and signals["in_reader"]: return "current_page"
   if intent == "quran": return "quran"
   if intent == "dictionary": return "dictionary"
   if signals["has_title"]: return "named_title"
   if intent == "catalog": return "catalog"
   if signals["has_author"] and not signals["has_title"]: return "named_author"
   if signals["is_volume_shift"] and (signals["in_reader"] or signals["has_context_books"]): return "volume_shift"
   if signals["in_reader"] and not has_title and not has_author: return "in_reader_only"
   if signals["has_context_books"]: return "context_books"
   return "open"  # DEFAULT_ROUTE
   ```

   Note the precedence: a resolved `has_title` now wins over `catalog` intent even when the model classified the question as catalog-shaped ("who wrote «X»") — it routes to `named_title` instead, since a confirmed title match is a stronger signal than the catalog label alone.

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
| `quran` | `intent == "quran"` | `search_quran(surah, ayah, q)` — also returns surah metadata (verse count, names) |
| `dictionary` | `intent == "dictionary"` | One of 7 tools by `dictionary_subtype` (`lookup_uyghur_word`, `lookup_history_term` [+ `search_language_sources` if empty], `translate_english_to_uyghur`, `check_word_spelling`, `lookup_uyghur_name`, `lookup_proverbs`, `lookup_synonyms`, or `search_language_sources` for `general`); falls back to `search_chunks(book_ids=None)` if every dictionary tool found nothing |
| `catalog` | `intent == "catalog"` and not `has_title` | `catalog_subtype` picks `get_book_author` / `get_books_by_author` / `search_catalog`; if that strict lookup found nothing, falls back inline to `search_books_by_summary` → `search_chunks` → universal fallback |
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

### Retrieval Refinements

- **Multi-book minimum slice.** `vector_search()` in `retrieval.py` gives each named book (e.g. multi-title comparison questions) its own `similarity_search` call capped at `max(rag_top_k // n_books, 3)`, then merges and re-sorts, instead of ranking one global top-K across all books combined — otherwise the single highest-scoring book can crowd every other book out of the context entirely.
- **Multi-quoted-title matching.** `find_books_by_title_in_question()` now resolves every «quoted» title in the question, not just the first — so "«Book A» بىلەن «Book B» نى سېلىشتۇر" (compare Book A and Book B) matches both.
- **False-positive guard + fuzzy fallback in `find_books_by_title`.** A lone single-word title match is discarded when the question itself has 3+ significant words (likely an unrelated common word, not a real title hit); if strict matching finds nothing, a fuzzy keyword fallback (`fuzzy_token_similar`, edit-distance ≥ 0.85 over normalized Uyghur tokens) retries against title/author words before giving up.
- **Dev-only DB text fallback for missing embeddings.** When `vector_search()` gets zero hits and `settings.environment != "production"`, it fuzzy-matches the question's keywords directly against `Chunk.text` in Postgres as a stand-in for a missing embeddings backfill (common in local dev DB dumps). Never runs in production, and its results are never written to the vector-search cache key — a stale fallback entry must not shadow real embeddings once they're backfilled.
- **Quran surah metadata.** `search_quran()` now also returns `surah_metadata` (total ayah count, Uyghur/English/Arabic surah names) and prepends it to the RAG context, so questions like "how many verses in surah 2" don't require a separate lookup.

---

## Model Configuration

Both stages resolve the same `ctx.agent_model` `LLMRoutedRAGHandler` uses (`gemini_agent_loop_model` system config, falling back to `gemini_chat_model`; `gemini-3.1-flash-lite` by default). There is no separate model configured for this handler's LLM calls.

The intent-classification fallback still goes through `build_text_llm(ctx.agent_model)` (`ProtectedLLM`, behind the shared Gemini text circuit breaker). `_llm_analyze_query()` no longer does — its tool-calling loop needs raw access to `response.function_calls` and manual `contents` history management that `ProtectedLLM.ainvoke()` doesn't expose, so it calls `_get_text_client().aio.models.generate_content()` directly. This one call path is not covered by the text circuit breaker.

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
| Catalog question ("who wrote X") | 1–2 agent reasoning calls | 1 analyze call (2 model turns: resolve author via tool, then final JSON) |
| Current page question | 1–2 agent reasoning calls | 1 analyze call |
| Named title, clear passage | 2–3 agent reasoning calls | 1 analyze call (2 model turns: resolve title via tool, then final JSON) |
| Follow-up with pronoun + content | 3–5 agent reasoning calls | 1 analyze call |
| Multi-question (3 sub-questions) | 4–6 agent reasoning calls | 1 analyze call (sub-questions extracted in the same call; each sub-question may add 1 classification call only on Stage-1 failure) |

"1 analyze call" is one `extract_signals()` invocation — internally it may still cost up to 3 model turns against Gemini if `_llm_analyze_query` invokes the title/author tools (see Stage 1), all within the same `generate_content` billing/latency envelope as a single logical call.

---

## Known Limitations

- A wrong intent classification has no self-correction the way an LLM agent can sometimes recover mid-loop.
- Novel question types not covered by the fixed intent set default to `passage`, which is usually — but not always — the right retrieval shape.
- The universal fallback mitigates most misroutes by widening scope when results are thin, regardless of which path was taken.
