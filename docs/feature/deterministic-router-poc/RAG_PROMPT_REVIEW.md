# RAG Prompt Review — Findings & Proposals

> **Superseded:** All findings below are resolved by the deterministic router design in `RAG_DETERMINISTIC_ROUTER_DESIGN.md`, which replaces `AGENT_SYSTEM_PROMPT` entirely.

**Files reviewed:**
- `packages/backend-core/app/services/rag/agent/prompts.py` — retrieval agent system prompt
- `packages/backend-core/app/services/rag/answer_builder.py` — answer generation instructions

---

## Retrieval Agent (`prompts.py`)

---

### 1. Step 4h is orphaned — the agent may never reach it

Step 4h (knowledge graph for relationship queries in global mode) is placed after 4g. But 4b already handles the titled-book + relationship case. An agent that matches 4b and stops there will skip 4h entirely, even though 4h explicitly says "even if find_books_by_title was already called." The two rules contradict each other on when to combine knowledge graph with chunk search.

**Proposal:** Merge 4h into 4b as a named sub-condition rather than a separate lettered step. Make it explicit that the graph check is a modifier on *any* content retrieval path, not a fallback at the end of the list.

---

### 2. Steps 4d and 4f silently overlap

Both handle "no explicit title/author, but context has prior book IDs." The difference is: 4d is for the *current open book*, 4f is for *previous response book IDs*. But `context book_ids` and `current book_id` are never defined as mutually exclusive in the prompt. The agent can't know whether to apply 4d or 4f if both conditions are simultaneously true (user is reading a book, and prior turn returned results from that same book).

**Proposal:** Make the mutual exclusion explicit: "If [Context] provides a current_page/book_id (in-reader mode), skip 4f entirely and use 4d."

---

### 3. The exception clause in 4e is buried and duplicated

The exception ("EXCEPTION: If the question is a follow-up asking for details, specific events, historical facts…") appears mid-sentence in 4e, then is repeated again at the end of 4g's IMPORTANT clause. This is the same rule written twice in different words, which invites inconsistent interpretation.

**Proposal:** Extract this rule into a single named note at the top of Step 4 — "Character identity vs. detail questions: 'who is X / tell me about X' → summaries; specific events, facts, or passages about X → search_chunks." Then reference it by name in 4e and 4g rather than re-stating it.

---

### 4. Step 4i's retry logic has no decision criterion

"retry with a rephrased query OR broaden by calling search_chunks with empty book_ids" — the OR gives the agent a meaningless choice. There's no signal to choose between rephrasing (same scope) vs. broadening (global scope).

**Proposal:** Make it sequential: "First retry with a rephrased query in the same scope. If still fewer than 4 results, then broaden to empty book_ids."

---

### 5. The 6-tool hard limit conflicts with step 6 (multi-question) ⚠️

Step 6 requires separate tool calls for each sub-question. With 3 sub-questions, each needing a discovery call + chunk search, that's already 6 calls before any retry. The hard limit will silently truncate coverage of later sub-questions.

**Proposal:** Either raise the limit to 10 for multi-question turns, or add a clause: "For turns with [Sub-questions], the limit is raised to min(3 × sub-question count, 12)."

---

### 6. Step 4i's "does not apply after get_book_summary" carve-out is easy to miss

The carve-out is at the end of 4i as a short sentence after a paragraph of chunk-retry logic. An agent that calls get_book_summary in 4g and gets few results may still trigger the 4i retry logic.

**Proposal:** Move this carve-out to the *beginning* of 4i as an explicit guard: "Only applies to search_chunks calls. If you just called get_book_summary, stop — do not retry with search_chunks."

---

### 7. Step 1 coreference exception is embedded inside the trigger rule

The EXCEPTION clause is mid-paragraph in Step 1, making the rule harder to parse reliably: "call rewrite_query first… EXCEPTION: Do NOT call rewrite_query if…". A model skimming the trigger condition may miss the exception.

**Proposal:** Restructure as two bullets: "When to call rewrite_query: …" and "When NOT to call it: …" as a sibling bullet.

---

## Answer Builder (`answer_builder.py`)

---

### 8. `strict_no_answer` mode has no citation guidance ⚠️

When `strict_no_answer=True` (book-scope, strict), the prompt drops instructions 4–6 entirely — citation format, source structure, and link syntax are all absent. But chunks are still retrieved and passed as context. The LLM has context with `[BookID: …, Book: …, Page: N]` headers but no instruction on how to cite them.

**Proposal:** Add a condensed citation rule to the strict mode: "If you cite a passage, use the format [Book: title, Page: N](ref:book_id:page_number)."

---

### 9. Catalog tool results have no citation format

Instructions 4–6 define two citation URLs: `ref:book_id:page_number` and `ref:book_id:summary`. But `get_book_author`, `get_books_by_author`, and `search_catalog` return neither page numbers nor summaries. The LLM has no template for those cases and may hallucinate a `ref:` URL or skip the citation entirely.

**Proposal:** Add a third citation form: "For catalog/author results with no page or summary, omit the `ref:` link and cite inline as **مەنبە:** title (author)."

---

### 10. Instruction numbering collision when flags are combined

In the permissive mode, instruction 8 is "Respond only in Uyghur" and instruction 9 is the strict Uyghur rule. When `suppress_page_notice=True`, `extra_rules` appends as `"\n9. …"` — creating a second instruction 9. When `is_global=True` it adds `"\n10. …"`, which collides if `suppress_page_notice` already renumbered things. The numbering is assembled by string concatenation without accounting for flag combinations.

**Proposal:** Use unnumbered bullet points for the appended rules, or compute the next instruction number dynamically based on which flags are set.

---

### 11. "Markdown OK but only Uyghur text" is ambiguous

Instruction 9 says "Output ONLY Uyghur text. Do not include English words." But instruction 3 prescribes `**bold**`, `- ` bullet points, and `>` blockquotes, which are ASCII. Some models interpret "only Uyghur text" as prohibiting all ASCII including formatting syntax.

**Proposal:** Add a one-line clarification: "Markdown structural characters (`**`, `-`, `>`, `#`) are permitted as formatting; only *content words* must be Uyghur."

---

## Summary

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 5 | High | `prompts.py` | 6-tool limit breaks multi-question coverage |
| 8 | High | `answer_builder.py` | `strict_no_answer` has no citation guidance |
| 1 | Medium | `prompts.py` | Step 4h orphaned — graph queries may be skipped |
| 2 | Medium | `prompts.py` | Steps 4d/4f overlap creates ambiguous path |
| 3 | Medium | `prompts.py` | 4e exception duplicated in 4g |
| 9 | Medium | `answer_builder.py` | Catalog results have no citation format |
| 4 | Low | `prompts.py` | 4i retry choice has no decision criterion |
| 6 | Low | `prompts.py` | 4i carve-out buried, easy to miss |
| 7 | Low | `prompts.py` | Step 1 exception buried inside trigger |
| 10 | Low | `answer_builder.py` | Instruction numbering collision |
| 11 | Low | `answer_builder.py` | "Only Uyghur" vs markdown ASCII ambiguity |
