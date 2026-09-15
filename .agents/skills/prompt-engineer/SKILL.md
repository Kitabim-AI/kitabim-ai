---
name: prompt-engineer
description: "Use when writing or editing LLM prompts in kitabim-ai for OCR, RAG or chat, or summarization, to ensure correct Uyghur script output."
---

You are writing, editing, and reviewing prompts for the Kitabim AI system. All prompts are used with Google Gemini models via the Google GenAI SDK (`google-genai`) or Google ADK (`google-adk`). The system serves Uyghur-language content — every prompt that touches text output must produce correct Perso-Arabic Uyghur script.

---

## Where Prompts Live

Two different mechanisms, depending on the task:

1. **Static string constants** in `packages/backend-core/app/core/prompts.py` — OCR, book summaries, LLM-judge scoring, reranking, entity resolution, query rewriting, history-term extraction. Formatted with `.format(...)` and sent via `generate_text()` / `generate_text_with_image()` / `build_text_llm()`.
2. **ADK agent instructions** for RAG chat — built by Python functions (not flat constants), because the chat pipeline is two ADK `Agent`s chained by `ChatOrchestrator`, not a single templated prompt.

```
packages/backend-core/app/core/prompts.py                    ← OCR, summary, judge, rerank, entity-resolution, query-rewrite, history-extraction prompts
packages/backend-core/app/llm/models.py                      ← model construction + circuit breaker (generate_text, generate_text_with_image, build_text_llm, GeminiEmbeddings)
packages/backend-core/app/services/rag/agent/prompts.py      ← AGENT_SYSTEM_PROMPT — retrieval agent's tool-calling instructions
packages/backend-core/app/services/chat/answer_prompts.py    ← build_answer_instructions() — final-answer synthesis instructions
packages/backend-core/app/services/chat/orchestrator.py      ← ChatOrchestrator.stream_response — the sole chat pipeline, chains both agents
packages/backend-core/app/services/chat/retrieval_agent.py   ← builds the retrieval Agent (AGENT_SYSTEM_PROMPT + intent-signal hints + tools)
packages/backend-core/app/services/chat/answer_agent.py      ← builds the answer Agent (build_answer_instructions + graded context, no tools)
packages/backend-core/app/services/ocr_service.py            ← uses OCR_PROMPT
services/worker/jobs/summary_job.py                          ← uses BOOK_SUMMARY_PROMPT
```

There is **no** `services/rag/handlers/standard_rag.py` and no single `RAG_PROMPT_TEMPLATE`-driven RAG chain in the live path — that was the legacy single-shot RAG pipeline, deleted when the codebase consolidated onto `ChatOrchestrator`'s two-agent ADK design (see `docs/superpowers/plans/2026-08-12-adk-chat-consolidation.md`). `RAG_PROMPT_TEMPLATE` and `CATEGORY_PROMPT` still exist as constants in `core/prompts.py` but are effectively dead — see the note in the table below before touching either.

---

## Current Prompts

| Constant / builder | Used by | Purpose |
|---|---|---|
| `OCR_PROMPT` | `ocr_service.py`, `batch_ocr_service.py` via `generate_text_with_image()` | Vision OCR for scanned Uyghur book pages |
| `BOOK_SUMMARY_PROMPT` | `summary_job.py` | Generate vector-indexed semantic summary in Uyghur |
| `RAG_JUDGE_PROMPT` | `services/rag/judge.py` (`score_answer`) | LLM-judge scoring of a chat turn (faithfulness / answer_relevance / context_precision) |
| `RAG_RERANK_PROMPT` | `services/rag/agent/reranker.py` (`rerank_context`) | LLM reranking of retrieved chunks before answer synthesis |
| `ENTITY_RESOLUTION_JUDGE_PROMPT` | `entity_resolution_service.py` | Same/different verdict for candidate duplicate knowledge-graph entities |
| `QUERY_REWRITE_PROMPT` | `rewrite_query` agent tool (co-reference resolution) | Rewrite a pronoun-dependent follow-up into a standalone question |
| `EXTRACTION_PROMPT_TEMPLATE` / `FACT_CLASSIFICATION_PROMPT_TEMPLATE` / `SYNTHESIS_PROMPT_TEMPLATE` | `HistoryExtractionService` | AI-driven history-dictionary term/fact extraction pipeline |
| `AGENT_SYSTEM_PROMPT` (`services/rag/agent/prompts.py`) | `build_retrieval_agent()` → `KitabimRetrievalAgent` (ADK `Agent`) | Retrieval-agent tool-calling policy — which tool to call for which question shape, hard limits on tool-call count |
| `build_answer_instructions()` (`services/chat/answer_prompts.py`) | `build_answer_agent()` → `KitabimAnswerAgent` (ADK `Agent`) | Final-answer synthesis: citation format, Uyghur-only output, persona injection |

**Dead constants — do not build new features on these without checking they're actually wired up first:**
- `CATEGORY_PROMPT` — defined in `core/prompts.py` but not imported anywhere. The category-based book pre-filter it served was part of the deleted legacy pipeline; book/author discovery is now the retrieval agent's own job via `find_books_by_title`, `search_books_by_summary`, `get_books_by_author`, `search_catalog` tools.
- `RAG_PROMPT_TEMPLATE` — still built into a LangChain chain by `llm_resources.get_rag_chain()` and stored on `QueryContext.rag_chain` every request, but nothing ever calls `.rag_chain` — grep confirms zero consumers. If you're tempted to edit this to change chat behavior, edit `AGENT_SYSTEM_PROMPT` or `build_answer_instructions()` instead — this constant has no effect on live chat.

---

## Model Config (DB-driven, hot-reloadable)

Model names come from `SystemConfigsRepository`, not hardcoded in prompts. Seed defaults (`app/db/seeds.py`):

| Key | Default Value | Used For |
|-----|---------------|----------|
| `rag_gemini_chat_model` | `gemini-3.1-flash-lite` | Answer-agent synthesis (reader chat and global chat); also the fallback for `gemini_agent_loop_model` |
| `gemini_agent_loop_model` | *(unset → falls back to `rag_gemini_chat_model`)* | Retrieval-agent tool-calling loop — set separately if you want a cheaper/faster model for retrieval vs. synthesis |
| `ocr_gemini_model` | `gemini-3.5-flash` | OCR vision calls |
| `embed_gemini_model` | `gemini-embedding-2` | Chunk + summary embeddings (3072-dim — do not assume 768, that's stale from an earlier model) |
| `rag_gemini_reranker_model` | `gemini-3.1-flash-lite` | `RAG_RERANK_PROMPT` |
| `rag_gemini_judge_model` | `gemini-3.1-flash-lite` | `RAG_JUDGE_PROMPT` |
| `rag_agent_max_llm_calls` | `12` | Code-enforced cap (`RunConfig.max_llm_calls`) on the retrieval agent's ADK LLM-call loop — backstops `AGENT_SYSTEM_PROMPT`'s own prose-only "at most 6 tool calls" limit, which the model can and does ignore in production |

There is no `gemini_categorization_model` — that belonged to the dead `CATEGORY_PROMPT` path and was never seeded as a live key.

**Never hardcode model names in prompts or services.** Always read from `SystemConfigsRepository`.

---

## Model Parameters by Use Case

There is no shared `_build_chat_model()` helper — each call site sets its own `GenerateContentConfig` (or, for ADK agents, ADK's own defaults apply since `Agent(...)` isn't given an explicit `GenerateContentConfig`).

| Use Case | `temperature` | Thinking | Notes |
|----------|--------------|----------|-------|
| OCR transcription (`generate_text_with_image`) | `0.0` | **Disabled** via `disabled_thinking_config(model_name)` in `llm/models.py` — `thinking_level="MINIMAL"` for Gemini 3.x+ models (they reject `thinking_budget=0` outright), `thinking_budget=0` for older models | Deterministic, no reasoning needed; without this, models can silently burn the whole output budget on hidden thinking and return empty text |
| Retrieval agent / Answer agent (ADK `Agent`) | model default | model default | No explicit `GenerateContentConfig` override — behavior comes from `AGENT_SYSTEM_PROMPT` / `build_answer_instructions()` content, not sampling params |
| Judge / Reranker (`build_text_llm` + `ProtectedLLM`) | model default | model default | No override; correctness comes from the prompt's "return only JSON" instruction |
| Summarization | model default | model default | Accuracy + density over creativity |

If you need deterministic OCR-style behavior for a new prompt, follow the `disabled_thinking_config()` pattern rather than inventing a new one.

---

## How Prompts Are Called

### Plain text generation (backend or worker) — static prompts
```python
from app.llm.models import generate_text

text = await generate_text(prompt_string, model_name=rag_gemini_chat_model)
```

### Vision OCR (worker only)
```python
from app.llm.models import generate_text_with_image

text = await generate_text_with_image(OCR_PROMPT.format(...), image_bytes, model_name=ocr_gemini_model)
```

### Judge / reranker calls — static prompts via ProtectedLLM
```python
from app.llm.models import build_text_llm, ProtectedLLM

llm: ProtectedLLM = build_text_llm(model_name)
result = await llm.ainvoke(prompt_string)   # RAG_JUDGE_PROMPT, RAG_RERANK_PROMPT use this path
```

### RAG chat — ADK agents, not a flat prompt string
```python
from google.adk.runners import Runner
from app.services.chat.retrieval_agent import build_retrieval_agent
from app.services.chat.answer_agent import build_answer_agent

retrieval_agent = build_retrieval_agent(model=agent_model, intent_signals=signals)
runner = Runner(agent=retrieval_agent, app_name="kitabim-retrieval", session_service=..., auto_create_session=True)
async for event in runner.run_async(user_id=..., session_id=..., new_message=..., run_config=RunConfig(...)):
    ...  # tool_call / tool_result / agent_thinking events

answer_agent = build_answer_agent(model=chat_model, graded_context=graded_context, persona_prompt=..., is_global=..., has_categories=...)
# run via a second Runner the same way — see ChatOrchestrator.stream_response for the full two-stage flow
```
Editing chat behavior means editing `AGENT_SYSTEM_PROMPT` (what to retrieve and when to stop) or `build_answer_instructions()` (how to cite and format the final answer) — never the constant string of a prompt template.

### Embeddings (backend + worker)
```python
from app.llm.models import GeminiEmbeddings

embeddings = GeminiEmbeddings(model_name=embed_gemini_model)
doc_vecs = await embeddings.aembed_documents(texts)   # RETRIEVAL_DOCUMENT task type
query_vec = await embeddings.aembed_query(question)   # RETRIEVAL_QUERY task type
```

---

## Circuit Breaker Awareness

Every `generate_text` / `generate_text_with_image` / `ProtectedLLM` call goes through a circuit breaker (`_TEXT_BREAKER`, `_OCR_BREAKER`, `_EMBED_BREAKER`). If the breaker is open, `CircuitBreakerOpen` is raised immediately without hitting the API. ADK `Agent`/`Runner` calls (retrieval + answer agents) go through ADK's own model client, not this breaker.

- **Streaming**: First-chunk timeout applies — if the model connects but never sends a token, the breaker trips.
- **Rate limit**: prompts must not retry in a tight loop outside the breaker/rate-limiter path.
- **OCR retries**: `ocr_service.py` implements exponential backoff for 429/503 before the breaker trips.
- **Retrieval-agent loop**: bounded by `rag_agent_max_llm_calls` (ADK's `RunConfig.max_llm_calls`), not the circuit breaker — a separate mechanism, see Model Config above.

**Do not add retry logic inside prompts or services** — the circuit breaker and rate limiter handle it.

---

## RAG Chat — Two-Stage ADK Pipeline Structure

`ChatOrchestrator.stream_response` (`services/chat/orchestrator.py`) runs two ADK agents in sequence per turn, each with its own instruction builder:

**1. Retrieval agent** (`AGENT_SYSTEM_PROMPT`, `services/rag/agent/prompts.py`) — tool-calling only, must not write the final answer. Structured as numbered steps the model follows in order: co-reference resolution → current-page short-circuit → Quran → dictionary/language tools → catalog/metadata tools → content retrieval (with sub-cases for book title, author, current book, prior context, general search) → stop condition → multi-sub-question handling → hard limits (tool-call cap, no-repeat-query, no-empty-book-search-first). `build_retrieval_agent()` in `retrieval_agent.py` appends "Structured Intent Hints" (dictionary subtype/term, Quran surah/ayah, catalog subtype) extracted upstream by `analyze_query_signals` — if the analyzer already resolved a value (e.g. an exact dictionary term), forward it as a hint rather than making the retrieval agent re-derive it from the raw question; re-derivation is how spelling drift and extra tool calls creep in.

**2. Answer agent** (`build_answer_instructions()`, `services/chat/answer_prompts.py`) — pure synthesis, zero tools, given the retrieval agent's graded/reranked context as a block of text appended to its instructions. Governs citation format (`ref:book_id:page`, `ref:quran:surah:ayah`, `ref:graph:book_id:page`, inline citations for catalog/dictionary results), markdown formatting, Uyghur-only output, and the "no relevant documents found" fallback message (`strict_no_answer` mode uses a shorter instruction set for book-scoped chat).

When editing either: keep the numbered/enumerated structure (both are model-readable checklists, not prose paragraphs) and re-test with representative Uyghur questions covering each branch you touched — these prompts are large enough that a change to one step's wording can shift which branch the model picks for an unrelated question.

---

## OCR_PROMPT — Structure and Rules

The OCR prompt uses XML-style sections to organize rules for the model. When editing it:

### `<critical_rules>` — Non-negotiable
- Output Uyghur text only — no translation, no commentary, no placeholders.
- Empty output for blank/non-text pages — never `N/A`, `[blank]`, etc.

### `<formatting_guidelines>` — Output format
- Continuous paragraphs (no artificial line breaks to match page width).
- Poems: preserve original line breaks exactly.
- Headings: standard Markdown (`#`, `##`).
- Page headers/footers: prefix with `[Header]` / `[Footer]`.
- TOC: pipe table with data rows only — **no** Markdown header row or separator.

### `<character_accuracy>` — Uyghur-specific
These rules exist because Gemini confuses visually similar Perso-Arabic letters. Do not remove or soften them — they directly impact OCR quality:
- Waw-family vowels: و / ۇ / ۆ / ۈ / ۋ (diacritics must be distinguished)
- ڭ vs ك, ر vs ز, ە vs ھ, ف vs ق
- Arabic-only letters (ع, ح) are not in the Uyghur alphabet — almost always غ or خ with a dot

### `<frequent_corrections>` — Common errors
A lookup table of common OCR mis-transcriptions, injected at call time from `AutoCorrectRulesRepository` (not hardcoded in the constant — it's a `{frequent_corrections}` placeholder). Add new entries via that repository when recurring errors are found in production, not by editing the prompt constant.

---

## BOOK_SUMMARY_PROMPT — Structure and Rules

The summary is embedded as a single vector — its quality directly determines book discoverability in semantic search. It has **seven** required sections (always in Uyghur):

1. **تۈرى** (Domain) — 1–3 categories from a fixed list, most relevant first
2. **ئومومى بايان** (Overview) — 400–600 word narrative covering subject, plot/arguments, key developments, conclusions
3. **ئاساسلىق ئۇقۇم ۋە تېمىلار** (Concepts & Themes) — exhaustive list, not just major themes
4. **شەخسلەر، ئورۇنلار، تەشكىلاتلار ۋە ۋەقەلەر** (Entities) — people/places/organizations that appear as content subjects; explicitly excludes the book's own author/translator/editor/publisher (already in metadata)
5. **مەزمون دائىرىسى** (Topic Coverage) — dense paragraph of every subject/issue/event the book addresses, for "does this book cover X?" queries
6. **تىپىك سوئاللار** (Hypothetical Queries) — 20–30 realistic search-style questions, covering every major topic/person/theme
7. **ئاچقۇچلۇق سۆزلەر** (Keywords) — 25–40 specific terms and proper nouns

### Text sampling strategy (`_sample_text()` in `summary_job.py`)
Only kicks in above the character budget — most books fit whole. When it doesn't fit, it samples:
- First 40% of the budget
- Middle 20% of the budget
- Last 40% of the budget

The budget itself is `settings.summary_max_chars` (env-based `SUMMARY_MAX_CHARS`, default a 3M-char safety ceiling for outlier books), further capped to 100k chars when a smaller/older model with a limited context window is detected. This is a `settings.*` value, not a `system_configs` DB row — don't confuse it with the DB-driven keys in the Model Config table above.

### Guidelines
- **Be specific**: proper nouns and technical terms, not general paraphrases.
- **Be exhaustive, not dense-for-its-own-sake**: the current prompt explicitly favors comprehensive coverage over brevity — a richer summary means better search recall.
- **No hallucination**: every name, claim, and entity must appear in the provided text.
- **Ignore production metadata**: skip publisher/copyright/ISBN/printing details — index content only.

---

## Prompt Engineering Rules for This Project

### 1. Language
- All prompts that produce Uyghur output must explicitly say "Write in Uyghur (Arabic/Perso-Arabic script)."
- Never assume the model defaults to Uyghur — state it explicitly.
- For prompts that accept Uyghur input (OCR, RAG), note the script name so the model doesn't transliterate.

### 2. Structure
- Use XML-style sections (`<rules>`, `<guidelines>`) or numbered steps for long prompts — they help the model weight and follow sections in order. `AGENT_SYSTEM_PROMPT` and `build_answer_instructions()` both use numbered-step structure for this reason.
- Use `{placeholders}` for all dynamic values in `core/prompts.py` constants — never f-string interpolation inside the constant itself. The ADK agent instruction builders (`retrieval_agent.py`, `answer_prompts.py`) are Python functions, not `.format()` templates — they build the string directly with f-strings/concatenation, which is the correct pattern for them specifically since they're never reused as a shared template.
- Keep `core/prompts.py` constants pure: no runtime logic, no conditional sections, no Python expressions.

### 3. Output format
- If the output must be parseable (list, JSON, table), specify the exact format and provide an example.
- For structured JSON output (judge, reranker, entity resolution, extraction prompts), state the exact schema inline in the prompt and explicitly forbid markdown fences/commentary around it — these are parsed with plain `json.loads`, not a schema-enforcing SDK feature.
- Never ask the model to "try to" follow a format — state it as a hard requirement.

### 4. Negative instructions
- Explicitly state what NOT to do (e.g., "Do NOT translate", "Do NOT add commentary").
- The OCR `<critical_rules>` block is a proven pattern — use it for any safety-critical constraint.
- For agent tool-calling prompts specifically, negative instructions are what prevent runaway loops — e.g. `AGENT_SYSTEM_PROMPT`'s "Do not repeat the same query twice — this includes retrying under an alternate spelling." A model left to its own judgment on when to stop will keep calling tools past any prose-only limit; pair every "call X" instruction with an explicit stop condition.

### 5. Length and density
- OCR prompts: include all character accuracy rules even if long — precision beats brevity for transcription.
- Summary prompts: specify word/item counts per section so the model doesn't write one-liners.
- Agent instructions: length is fine if every step is decision-relevant — `AGENT_SYSTEM_PROMPT` is long by design because each step disambiguates one question shape. Bloat to avoid is repeating the same guidance in multiple steps, not overall length.

### 6. Embedding-optimized text
- Summaries and indexed text are embedded as vectors — they must be **information-dense**.
- Avoid meta-commentary ("This book is about...") — use direct, noun-heavy phrasing.
- Include hypothetical queries: they align the document vector with real user query vectors.

### 7. Agent loops need a code-enforced backstop, not just a prompt limit
- A prose instruction like "at most N tool calls" is advisory — the model can and does exceed it (e.g. retrying a failed dictionary lookup under an alternate spelling instead of stopping on a miss). Where an ADK `Agent` runs in a tool-calling loop, pair the prompt's stated budget with a real `RunConfig.max_llm_calls`, sourced from `system_configs` so it's tunable without a redeploy (see `rag_agent_max_llm_calls`). Catch `LlmCallsLimitExceededError` around the `Runner.run_async` loop and degrade gracefully (proceed with partial results) rather than letting it fail the whole turn.

---

## Adding or Editing a Prompt

### Editing an existing static prompt (`core/prompts.py`)
1. Read the current constant.
2. Understand which use case and model it targets (see Current Prompts table above).
3. Make the change — test with a representative input before committing.
4. If the edit changes output format, update any downstream parsers or text-cleaning logic (`utils/text.py::clean_uyghur_text` post-processes OCR output; `citation_fixer.py::fix_malformed_citations` post-processes the answer agent's citation links in `orchestrator.py`).

### Editing the RAG chat agents
1. Decide which stage owns the behavior you're changing: retrieval policy (what to call, when to stop) → `AGENT_SYSTEM_PROMPT`; answer formatting/citation/tone → `build_answer_instructions()`.
2. Keep the numbered-step structure; insert new steps rather than overloading an existing one with unrelated conditions.
3. If the change should only apply given information already known before the agent runs (e.g. a resolved dictionary term, a Quran reference), forward it as a "Structured Intent Hint" from `intent_signals` in `retrieval_agent.py` rather than asking the agent to re-derive it.
4. Test via the chat endpoint directly with representative Uyghur questions across the branches you touched, and check the resulting tool-call trace in logs (`app.rag.agent.tools` / `google_adk.google.adk.models.google_llm` loggers) for unexpected extra calls.

### Adding a new static prompt
1. Add the constant to `core/prompts.py` — uppercase name, e.g. `MY_TASK_PROMPT`.
2. Use `{placeholders}` for all dynamic values — format at call time with `.format(key=value)`.
3. Document which model/temperature/thinking config it expects (in a comment above the constant, following the `# Used by: ... / Model: ...` convention already used for the history-extraction prompts).
4. Call it through `generate_text()`, `generate_text_with_image()`, or `build_text_llm()` — never call the Gemini SDK directly.
5. If it's a new worker task, read the model name from `SystemConfigsRepository` at job startup.
6. If it produces structured output, define the exact JSON schema inline in the prompt (see judge/rerank/entity-resolution prompts for the pattern) since there's no SDK-level schema enforcement on this path.
7. Add the system config key + default value to `packages/backend-core/app/db/seeds.py`.

### Testing a prompt change
- For OCR: run `manual_scan.py` with `run_ocr_scanner` to requeue pages and inspect OCR output.
- For summaries: run `summary_job` manually against a known book and inspect `book_summaries.summary`.
- For RAG chat: use the chat endpoint directly and compare responses before/after; check tool-call counts in logs, not just the final answer.
- For judge/reranker/entity-resolution: unit-test with a fixed input and assert the parsed JSON shape, since these are consumed programmatically.

---

## Common Mistakes

| Mistake | Why It's Wrong | What to Do Instead |
|---------|---------------|-------------------|
| Editing `RAG_PROMPT_TEMPLATE` or `CATEGORY_PROMPT` to change chat behavior | Both are dead code — built/defined but never invoked in the live chat path | Edit `AGENT_SYSTEM_PROMPT` (retrieval) or `build_answer_instructions()` (synthesis) |
| Hardcoding model name in prompt constant or agent builder | Model changes require code deploy | Read from `SystemConfigsRepository` at call time |
| f-string interpolation inside a `core/prompts.py` constant | Dynamic content mixes with static template | Use `{placeholder}` + `.format()` at call time |
| Calling Gemini SDK directly for a static prompt | Bypasses circuit breaker and rate limiter | Use `generate_text()` / `build_text_llm()` |
| Asking for Uyghur without specifying the script | Model may output Latin-script transliteration | Always say "Perso-Arabic script" |
| Adding retry logic in the service layer for static prompts | Conflicts with circuit breaker state | Let `ocr_service.py` backoff + breaker handle it |
| Trusting a prose "stop after N tool calls" limit alone in an agent prompt | Models exceed prose-only budgets under retry pressure (e.g. spelling-variant retries) | Pair it with a real `RunConfig.max_llm_calls`, sourced from `system_configs` |
| Removing `<critical_rules>` for brevity | OCR accuracy degrades on Uyghur characters | Keep all character accuracy rules |
| Omitting negative instructions | Model fills gaps with unwanted behavior | Explicitly state what NOT to output |
| Writing embedding text with filler phrases | Dilutes vector with low-signal tokens | Use noun-heavy, information-dense phrasing |
