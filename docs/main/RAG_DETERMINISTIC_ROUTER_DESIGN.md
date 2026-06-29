# RAG Deterministic Router — Design

**Status:** Proposal  
**Replaces:** `AgentRAGHandler._execute_workflow_stream` (ADK agent loop)  
**Files affected:** `packages/backend-core/app/services/rag/agent/handler.py`, `prompts.py`

---

## Problem

The current retrieval loop delegates all tool-call sequencing to an LLM (Google ADK agent). The agent interprets a 118-line natural language prompt to decide which tools to call and in what order. This means:

- Up to 6 LLM round-trips just for routing (before answer generation)
- Non-deterministic — the same question can take different paths across calls
- Hard to debug ("why did the agent call search_chunks before find_books_by_title?")
- The prompt encodes an **implicit decision tree** — we can just write the tree in code

The prompt review (`RAG_PROMPT_REVIEW.md`) found 11 logic issues in the current prompt — all of which are resolved by this design, since `AGENT_SYSTEM_PROMPT` is replaced entirely.

---

## Core Insight

The routing logic in `prompts.py` already *is* a decision tree — it's just written in English. Every step (1–6) is an `if/elif` branch. The only parts that genuinely require an LLM are:

| Step | Why LLM is needed |
|------|------------------|
| Coreference resolution | Resolving Uyghur pronouns against chat history |
| Intent classification | Distinguishing "who is X" (identity) vs "what did X do" (passage) |
| Query rewriting | Standalone question generation from a follow-up |
| Multi-question splitting | Already handled separately in `_llm_split` |

Everything else is deterministic given the signals already in `QueryContext`.

---

## Proposed Architecture

Replace the ADK agent loop with a three-stage pipeline:

```
[Question + QueryContext]
        │
        ├──► DB Check (fuzzy title/author)
        ▼
┌───────────────────────────┐
│  1. Unified Query Analyzer│  (structured JSON LLM call — extracts intent & signals)
└───────────────────────────┘  (resilient Python keyword fallback on error)
        │ signals: is_current_page_query, is_volume_shift, target_volume,
        │          needs_rewrite, catalog_subtype, intent
        ▼
┌───────────────────────────┐
│  2. Coreference Resolver  │  (conditional LLM — only when needs_rewrite=True)
└───────────────────────────┘
        │ possibly updates enriched_question
        ▼
┌───────────────────────────┐
│  3. Execution Router      │  (pure Python — picks and runs a fixed path A-H)
└───────────────────────────┘
        │ observations list (same format as today)
        ▼
[_grade_context → answer_builder]  (unchanged)
```

### Full Flow Diagram

```mermaid
flowchart TD
    Q(["Question + QueryContext"])

    Q --> S1_DB["**Stage 1a · DB Metadata Check** — fuzzy/exact DB lookup
    has_title · has_author"]

    S1_DB --> S1_LLM["**Stage 1b · Unified Query Analyzer** — structured LLM call
    extracts intent, volume shifts, page queries, & pronouns
    (resilient Python keyword fallback on exception)"]

    S1_LLM --> NR{needs_rewrite?}
    NR -- Yes --> S2["**Stage 2 · Coreference Resolver**
    gemini-3.5-flash
    updates enriched_question"]
    NR -- No --> MQ
    S2 --> MQ

    MQ{"multi-question?"}
    MQ -- Yes --> SPLIT["_llm_split · gemini-3.5-flash
    splits into ≤ 4 sub-questions"]
    MQ -- No --> PI
    SPLIT --> PI

    PI(["for each sub-question"])

    PI --> REUSE{"Reuse parent signals?<br/>(single sub-question &<br/>no rewrite)"}
    REUSE -- Yes --> SIG
    REUSE -- No --> S1_SUB["Sub-question LLM Signal Call"]
    S1_SUB --> SIG

    SIG{"signals & intent"}
    SIG -- "intent == catalog" --> PB["**Path B · Catalog**
    get_book_author /
    get_books_by_author /
    search_catalog"]
    SIG -- "top_intent == current_page" --> PA["**Path A · Current Page**
    get_current_page()"]
    SIG -- "has_author
    (no title)" --> PD["**Path D · Named Author**
    get_books_by_author → search_chunks"]
    SIG -- is_volume_shift --> PE["**Path E · Volume Shift**
    get_sister_volumes → search_chunks"]
    SIG -- "in_reader
    (no title / author)" --> PF["**Path F · In-Reader**
    search_chunks(current_book)"]
    SIG -- "content intents
    (has_title)" --> PC["**Path C · Named Title**
    find_books_by_title →
    summary / passage / relationship
    (intent-specific)"]
    SIG -- "content intents
    (has_context_books)" --> PG["**Path G · Prior Context**
    intent-specific tool sequence"]
    SIG -- "content intents
    (is_global)" --> PH["**Path H · Open Search**
    intent-specific tool sequence"]

    PA & PB & PD & PE & PF & PC & PG & PH --> MERGE

    MERGE["merge observations
    from all sub-questions"]

    MERGE --> UF{"search_chunks
    returned < 4?"}
    UF -- Yes --> FB["**Universal Fallback**
    search_chunks(global scope)"]
    UF -- No --> GC
    FB --> GC

    GC["_grade_context
    de-dup · score-filter · cap at 25 chunks"]
    GC --> ANS["**generate_answer_stream**
    gemini-3.5-flash / preview"]
    ANS --> OUT(["Answer stream"])
```

---

## Stage 1: Unified Query Signal Analyzer

A hybrid stage combining deterministic database-level metadata check with a single structured LLM call to extract semantic intent and navigation properties.

### 1a. DB Metadata Check (Deterministic)
- Checks the database for fuzzy or exact matches of titles (`has_title`) and authors (`has_author`) mentioned in the query text.

### 1b. LLM Query Analysis (Semantic)
- Employs a structured LLM call (`_llm_analyze_query`) using `GenerateContentConfig(response_mime_type="application/json")` to extract:
  - `is_current_page_query` (boolean)
  - `is_volume_shift` (boolean)
  - `target_volume` (int | null)
  - `needs_rewrite` (boolean)
  - `catalog_subtype` ("author_of" | "books_by" | "general" | null)
  - `intent` ("catalog" | "identity" | "summary" | "relationship" | "passage")
- **Resilient Fallback:** If the LLM call fails, the signal analyzer automatically falls back to local Python keyword matching and defaults `intent` to `"passage"` to ensure 100% service uptime.

---

## Stage 2: Coreference Resolver

Coreference resolution is merged directly into **Stage 1b**'s unified query analyzer call. The LLM analyzes the chat history and resolves pronouns/coreferences in-place, returning the standalone question as `rewritten_question` in the structured JSON output (saving a separate LLM round-trip).

**Resilient Fallback:**
If the Stage 1b unified query analyzer fails, Stage 2 coreference resolution falls back to:
1. Running local Python keyword checks for Uyghur pronoun tokens.
2. Invoking the standalone `rewrite_query` LLM tool to resolve coreferences against conversation history.

---

## Stage 3: Intent Classifier

Because intent is pre-extracted during **Stage 1b**'s structured query analysis, the `classify_intent` step simply reads the intent from the signals dictionary directly (bypassing any extra LLM calls).

**Resilient Fallback:**
If the Stage 1b LLM query analysis fails, intent classification falls back to:
1. **Python Skip Heuristics:** Automatically routing queries with simple author, volume shift, or active reader signals to their respective default intents (e.g. `passage`).
2. **Intent Classification LLM Call:** Executing a fallback LLM prompt to classify the question's intent (only if the skip heuristics are not met).

---

## Stage 4: Execution Router

Pure Python. Given signals + intent, selects and executes a fixed path. Each path calls tools directly (same tool implementations in `tools.py`) and appends to an `observations` list — identical in format to what the ADK agent produces today.

**Observations envelope format** (must match what `_grade_context` and `_extract_used_book_ids` expect):
```python
observations.append({
    "tool": "search_chunks",          # tool name string
    "result": {
        "ok": True,                   # bool — False if the tool errored
        "data": {                     # tool-specific payload
            "chunks": [...],          # for search_chunks
        },
    },
})
```
Each path executor is responsible for wrapping tool return values in this envelope before appending. The ADK runner did this automatically via `function_responses`; in the router it must be explicit.

### Path A — Current Page
**Triggers:** `top_intent == current_page` AND `in_reader`
```
get_current_page()
```

---

### Path B — Catalog
**Triggers:** `intent == "catalog"`

| Subtype | Tool sequence |
|---------|--------------|
| `author_of` ("who wrote X") | `get_book_author(question)` |
| `books_by` ("what books does author X") | `get_books_by_author(question)` |
| `general` | `search_catalog(question)` |

**Note:** `handlers/catalog.py` (`CatalogHandler._build_catalog_context`) already implements the DB queries for all three subtypes (title match → author info, author match → book list, fallback → full catalog). Path B's tool implementations should delegate to or inline this logic rather than re-implementing it.

---

### Path C — Named Title
**Triggers:** `has_title == True`

| Intent | Tool sequence |
|--------|--------------|
| `identity` | `find_books_by_title → get_book_summary(book_ids)` (falls back to `search_chunks(book_ids)` if summary does not contain info) |
| `summary` | `find_books_by_title → get_book_summary(book_ids)` [fallback if `book_ids` empty] |
| `passage` | `find_books_by_title → search_chunks(book_ids)` → [fallback if <4] |
| `relationship` AND `graph_available` | `find_books_by_title → query_knowledge_graph(book_ids) → search_chunks(book_ids)` |
| `relationship` AND NOT `graph_available` | `find_books_by_title → search_chunks(book_ids)` → [fallback if <4] |

**Note on Fallbacks & Changes:**
- **`summary` Fallback:** If `find_books_by_title` returns an empty list, fall back to `search_books_by_summary(question) → get_book_summary(top_ids, max=5)`.
- **Knowledge Graph Scope:** The implementation `_run_query_knowledge_graph` in `tools.py` must be modified to read and apply the optional `book_ids` parameter from tool arguments, rather than relying solely on `ctx.book_id`.

---

### Path D — Named Author (no explicit title)
**Triggers:** `has_author == True` AND NOT `has_title`
```
get_books_by_author(question) → search_chunks(returned_book_ids)
```
Fallback if <4 results: widen to `search_chunks(book_ids=None)`.

---

### Path E — Volume Shift
**Triggers:** `is_volume_shift == True` AND (`in_reader` OR `has_context_books`)
```
get_sister_volumes(current_book_id or context_book_ids[0])
→ search_chunks(target_volume_id)  # derived from volume number in question
```

---

### Path F — In-Reader, No Title/Author
**Triggers:** `in_reader == True` AND NOT `has_title` AND NOT `has_author` AND NOT `is_volume_shift`
```
search_chunks(current_book_id)
→ [if <4 results]: search_books_by_summary(question) → search_chunks(new_book_ids)
```

---

### Path G — Prior Context, No Title/Author
**Triggers:** `has_context_books == True` AND NOT `in_reader` AND NOT `has_title` AND NOT `has_author`

| Intent | Tool sequence |
|--------|--------------|
| `identity` | `search_books_by_summary(question, book_ids=context_book_ids)` → if results: `get_book_summary(verified_ids, max=5)` else: fall to G-passage |
| `passage` | `search_chunks(context_book_ids)` → [if <4: `search_books_by_summary → search_chunks(new_ids)`] |
| `relationship` AND `graph_available` | `query_knowledge_graph → search_chunks(context_book_ids)` |
| `summary` | `get_book_summary(context_book_ids, max=5)` |

---

### Path H — Open / No Context
**Triggers:** `is_global == True` AND NOT `has_title` AND NOT `has_author` AND NOT `has_context_books`

| Intent | Tool sequence |
|--------|--------------|
| `identity` | `search_books_by_summary(question) → get_book_summary(top_ids, max=5)` |
| `passage` | `search_books_by_summary(question) → search_chunks(book_ids)` |
| `relationship` | `query_knowledge_graph → search_books_by_summary(question) → search_chunks(book_ids)` |
| `summary` | `search_books_by_summary(question) → get_book_summary(top_ids, max=5)` |

---

### Universal Fallback

Any path that ends with `search_chunks` and returns <4 results:
1. Re-run `search_books_by_summary(question)` to rediscover books (SKIP this step if `search_books_by_summary` was already called in the primary execution path, e.g., Path H, Path F/G fallbacks).
2. Re-run `search_chunks(new_book_ids)` with the new IDs (SKIP if step 1 was skipped).
3. If still <4 (or if steps 1-2 were skipped): run `search_chunks(book_ids=None)` (global scope)

The transparent context-switch logic already in `_run_search_chunks` stays unchanged and handles topic-shift silently within step 1.

---

### Multi-Question

The existing `_llm_split` decomposition stays unchanged. For multi-question turns, the router is applied **independently per sub-question**, then all observations are merged before `_grade_context`. No more injecting sub-questions into an agent prompt.

**Ordering:** Coreference resolution (Stage 2) runs on the **original question** before splitting. If `needs_rewrite=True`, the rewritten `ctx.enriched_question` is what gets split by `_llm_split`. Sub-questions inherit the resolved context — each sub-question is NOT independently checked for `needs_rewrite`.

```
# Stage 2: rewrite original question first (if needed)
if needs_rewrite:
    await resolve_coreference(ctx)          # updates ctx.enriched_question

question = ctx.enriched_question or ctx.question

# Multi-question split on the rewritten question
if is_multi_question(question):
    sub_questions = await _llm_split(question, ctx.agent_model)
else:
    sub_questions = [question]

# Stage 3+4: classify and route each sub-question independently
for sub_q in sub_questions:
    signals = extract_signals(sub_q, ctx)   # needs_rewrite always False here
    intent = await classify_intent(signals, sub_q)
    sub_observations = await execute_path(intent, sub_q, ctx)
    all_observations.extend(sub_observations)

graded_context = _grade_context(all_observations)  # unchanged
```

---

## Model Assignments

| Role | Model | Reason |
|------|-------|--------|
| Coreference resolution (Stage 2) | `gemini-3.5-flash` | Simple rewrite, needs Uyghur support |
| Signal extraction / Intent classification | `gemini-3.5-flash` | Fast JSON classification, needs Uyghur support |
| Multi-question split (`_llm_split`) | `gemini-3.5-flash` | Simple extraction, needs Uyghur support |
| Answer generation (`generate_answer_stream`) | `gemini-3-flash-preview` | Best Uyghur output quality for final answer |

All three simple-call roles use the same model, so a single `SIMPLE_LLM_MODEL` env var (defaulting to `gemini-3.5-flash`) covers them all. The answer generation model is already governed by `ctx.rag_chain`, which is built upstream from a separate env var.

**Note on the existing `AGENT_MODEL` env var:** This currently defaults to `gemini-2.5-flash` and drives the ADK agent. In `DeterministicRAGHandler`, `ctx.agent_model` is reused for `_llm_split` — it should be updated to `gemini-3.5-flash` (or remapped to `SIMPLE_LLM_MODEL`).

---

## What Stays Unchanged

| Component | Status |
|-----------|--------|
| All tool implementations in `tools.py` | Unchanged |
| `_grade_context` | Unchanged |
| `_extract_used_book_ids` | Unchanged |
| `_populate_ctx_from_observations` | Unchanged |
| `answer_builder.py` | Unchanged |
| `QueryContext` | Unchanged |
| Event protocol (`planning`, `tool_call`, `tool_result`, `result`) | Same shape, emitted by router |
| `_llm_split` multi-question decomposition | Unchanged |
| Transparent context-switch in `_run_search_chunks` | Unchanged |

---

## What Is Removed

| Component | Replaced by |
|-----------|-------------|
| `AGENT_SYSTEM_PROMPT` (118-line prompt) | Signal extractor + classifier prompt (~10 lines) |
| Google ADK `InMemoryRunner` + `build_rag_agent` | Direct async tool calls |
| Agent loop (up to 6 LLM-driven tool call decisions) | Fixed path execution |
| `adk_agent.py` | Can be deleted |
| `agent/state.py`, `agent/graph.py` | Empty stub files — can be deleted |

Google ADK becomes an optional dependency — can be removed or kept for future experimentation.

**Note on `handlers/` pycache:** There are compiled `.pyc` files for 9 handler modules (author_by_title, books_by_author, capabilities, current_page, current_volume, follow_up, identity, standard_rag, volume_info) with no corresponding source files — a prior partial implementation was cleaned up. The `.pyc` files are safe to ignore; they will be evicted on the next clean build. `DeterministicRAGHandler` starts fresh from this design.

---

## LLM Call Budget Comparison

Proposed simple calls use `gemini-3.5-flash`.

| Scenario | Current ADK Agent Loop | Unified Query Analyzer Router |
|----------|------------------------|-------------------------------|
| Catalog question ("who wrote X") | 1–2 agent calls | 1 analyze call |
| Current page question | 1–2 agent calls | 1 analyze call |
| Named title, clear passage | 2–3 agent calls | 1 analyze call |
| Follow-up with pronoun + content | 3–5 agent calls | 1 analyze call |
| Multi-question (3 sub-questions) | 4–6 agent calls | 1 analyze + 1 split + 1 analyze per sub-q = 5 calls |
| Complex relationship + title | 3–4 agent calls | 1 analyze call |

---

## Risks and Trade-offs

**What we lose:**
- The agent can reason about edge cases that fall between categories. A deterministic router with a wrong-intent classification has no self-correction.
- Novel question types not covered by the intent set default to `passage`, which may not be optimal.

**Mitigations:**
- The intent classifier's fallback is `passage` — the most commonly correct path. Wrong identity→passage is recoverable (passages contain character descriptions too).
- The universal fallback ensures we always retry with broader scope if results are thin.
- The current prompt already has gap cases where the agent picks the wrong path anyway — and those are resolved by this design.

**Rollout approach:**
- Implement the router as a new class `DeterministicRAGHandler`
- Keep `AgentRAGHandler` in place
- Toggle via a feature flag (e.g. `settings.use_deterministic_router`) for A/B comparison
- Evaluate on the existing `rag_evaluations` table

---

## Open Questions & Resolved Solutions

1. **Intent classifier model & few-shot examples (Resolved):**
   Standard model classification (Haiku/Flash level) works very well. To make it highly robust in Uyghur, we will utilize **few-shot prompt examples** within the classification prompt, defining exact sample Uyghur inputs mapping to each of the four target intents (`identity`, `summary`, `relationship`, `passage`).

2. **`identity` vs `passage` boundary (Resolved):**
   Few-shot examples mapping explicit Uyghur lookups (e.g. comparing `"زوردۇن سابىر كىم؟"` -> `identity` vs `"زوردۇن سابىر ئانا يۇرت رومانىنى قاچان يېزىلغان؟"` -> `passage`) will be built directly into the system prompt configuration.

3. **`needs_rewrite` pronoun detection (Resolved):**
   To catch all Uyghur inflected/suffixed forms of pronouns reliably without false-positive matches, the Signal Extractor will tokenize the input, strip standard punctuation boundary characters (`_PUNCT = '«»،؟!()[]{}"' "''"`), and check the clean words against `UYGHUR_PRONOUN_TOKENS`. The set includes base pronouns, inflected case forms, and topic-shift clitics:
   ```python
   UYGHUR_PRONOUN_TOKENS = {
       "ئۇ", "بۇ", "شۇ", 
       "ئۇنىڭ", "بۇنىڭ", "شۇنىڭ",
       "ئۇنى", "بۇنى", "شۇنى",
       "ئۇنىڭغا", "بۇنىڭغا", "شۇنىڭغا",
       "ئۇنىڭدا", "بۇنىڭدا", "شۇنىڭدا",
       "ئۇنىڭدىن", "بۇنىڭدىن", "شۇنىڭدىن",
       "ئۇلار", "بۇلار", "شۇلار",
       "ئۇلارنىڭ", "بۇلارنىڭ", "شۇلارنىڭ",
       "ئۇلارنى", "بۇلارنى", "شۇلارنى",
       "ئۇلارغا", "بۇلارغا", "شۇلارغا",
       "ئۇلاردا", "بۇلاردا", "شۇلاردا",
       "ئۇلاردىن", "بۇلاردىن", "شۇلاردىن",
       "ئۇچۇ", "بۇچۇ", "شۇچۇ",
       "ئۇلارچۇ", "بۇلارچۇ", "شۇلارچۇ"
   }
   ```

4. **Graph scope in Path C (relationship) (Resolved):**
   The `query_knowledge_graph` tool in `tools.py` must be updated to accept `book_ids` inside its input dictionary `args`. If passed, `_run_query_knowledge_graph` will narrow the query subgraph to the matched book volumes, falling back to global scope or `ctx.book_id` if omitted.
