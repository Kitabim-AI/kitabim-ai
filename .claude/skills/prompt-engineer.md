# Prompt Engineer Skill — Kitabim AI

You are writing, editing, and reviewing prompts for the Kitabim AI system. All prompts are used with Google Gemini models via LangChain. The system serves Uyghur-language content — every prompt that touches text output must produce correct Perso-Arabic Uyghur script.

---

## Where Prompts Live

All production prompts are constants in `packages/backend-core/app/core/prompts.py`. This file is imported by both backend and worker — it is shared code.

```
packages/backend-core/app/core/prompts.py   ← all prompts defined here
packages/backend-core/app/langchain/models.py ← model construction + circuit breaker
packages/backend-core/app/services/rag/      ← RAG pipeline (uses RAG_PROMPT_TEMPLATE)
packages/backend-core/app/services/ocr_service.py ← uses OCR_PROMPT
packages/backend-core/app/services/rag/handlers/standard_rag.py ← builds final RAG prompt
```

---

## Current Prompts

| Constant | Used By | Purpose |
|----------|---------|---------|
| `OCR_PROMPT` | `ocr_service.py` + `generate_text_with_image()` | Vision OCR for scanned Uyghur book pages |
| `CATEGORY_PROMPT` | RAG category handler | Route user question to a book category |
| `BOOK_SUMMARY_PROMPT` | `summary_job.py` | Generate vector-indexed semantic summary in Uyghur |
| `RAG_PROMPT_TEMPLATE` | `standard_rag.py` | RAG chat: context + instructions + history + question |

---

## Model Config (DB-driven, hot-reloadable)

Model names come from `SystemConfigsRepository`, not hardcoded in prompts. Default seed values:

| Key | Default Value | Used For |
|-----|---------------|----------|
| `gemini_chat_model` | `gemini-3.1-flash-lite-preview` | RAG chat, summary generation |
| `gemini_categorization_model` | `gemini-3.1-flash-lite-preview` | Question categorization |
| `gemini_ocr_model` | `gemini-3.1-flash-lite-preview` | OCR vision calls |
| `gemini_embedding_model` | `models/gemini-embedding-001` | Chunk + summary embeddings (768 dim) |

**Never hardcode model names in prompts or services.** Always read from `SystemConfigsRepository`.

---

## Model Parameters by Use Case

| Use Case | `temperature` | `thinking_budget` | Notes |
|----------|--------------|-------------------|-------|
| OCR transcription | `0` | `1024` ("low") | Deterministic, no creativity needed |
| Chat / RAG | default | `None` | `include_thoughts=False` suppresses thought tokens from output |
| Summarization | default | `None` | Accuracy + density over creativity |
| Categorization | default | `None` | Structured output (list), low variance |

Set parameters in `_build_chat_model(model_name, temperature=..., thinking_budget=...)` — not inside prompts.

---

## How Prompts Are Called

### Plain text generation (backend or worker)
```python
from app.langchain.models import generate_text

text = await generate_text(prompt_string, model_name=gemini_chat_model)
```

### Vision OCR (worker only)
```python
from app.langchain.models import generate_text_with_image

text = await generate_text_with_image(OCR_PROMPT, image_bytes, model_name=gemini_ocr_model)
```

### RAG chat with streaming (backend only)
```python
from app.langchain.models import build_text_llm, ProtectedLLM

llm: ProtectedLLM = build_text_llm(model_name)
# Non-streaming:
result = await llm.ainvoke(prompt_string)
# Streaming:
async for chunk in llm.astream(prompt_string):
    yield chunk
```

### Embeddings (backend + worker)
```python
from app.langchain.models import GeminiEmbeddings

embeddings = GeminiEmbeddings(model_name=gemini_embedding_model)
doc_vecs = await embeddings.aembed_documents(texts)   # RETRIEVAL_DOCUMENT task type
query_vec = await embeddings.aembed_query(question)   # RETRIEVAL_QUERY task type
```

---

## Circuit Breaker Awareness

Every LLM call goes through a circuit breaker (`_TEXT_BREAKER`, `_OCR_BREAKER`, `_EMBED_BREAKER`). If the breaker is open, `CircuitBreakerOpen` is raised immediately without hitting the API.

- **Streaming**: First-chunk timeout is 60s — if the model connects but never sends a token, the breaker trips.
- **Rate limit**: Global `RedisRateLimiter` caps at 20 Gemini RPM (quota is 25, using 20 for safety). `await _GEMINI_LIMITER.wait()` is called before every call — prompts must not retry in a tight loop without going through this path.
- **OCR retries**: `ocr_service.py` implements exponential backoff for 429/503 before the breaker trips.

**Do not add retry logic inside prompts or services** — the circuit breaker and rate limiter handle it.

---

## RAG_PROMPT_TEMPLATE — Structure

```python
RAG_PROMPT_TEMPLATE = """
[CONTEXT START]
{context}
[CONTEXT END]

{instructions}

[CHAT HISTORY START]
{chat_history}
[CHAT HISTORY END]

Question: {question}
"""
```

| Placeholder | What goes in |
|-------------|-------------|
| `{context}` | Retrieved page chunks — assembled by `standard_rag.py` with up to `rag_max_chars_per_book` chars |
| `{instructions}` | Per-book or global persona/instructions string (from book record or system config) |
| `{chat_history}` | Prior turns formatted as `User: ...\nAssistant: ...` |
| `{question}` | The current user question (possibly enriched by `follow_up` handler) |

The instructions block is where per-book persona, tone, and domain restrictions live — not embedded in the template constant.

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
A lookup table of common OCR mis-transcriptions. Add new entries when recurring errors are found in production. Format: `wrong -> correct | wrong -> correct` on a single line, space-separated with `|`.

---

## BOOK_SUMMARY_PROMPT — Structure and Rules

The summary is embedded as a vector — its quality directly determines book discoverability in semantic search.

### Five required sections (always in Uyghur)
1. **ئومۇمىي مەزمۇن** (Overview) — 200–300 word narrative
2. **ئاساسلىق ئۇقۇم ۋە تېمىلار** (Concepts & Themes) — explicit list
3. **كۆرۈنەرلىك شەخس ۋە جايلار** (Entities) — proper nouns, places, organizations
4. **تىپىك سوئاللار** (Hypothetical Queries) — 5–7 questions the book can answer
5. **ئاچقۇچلۇق سۆزلەر** (Keywords) — 15–20 specific terms

### Text sampling strategy (in `summary_job.py`)
The job can't send full book text to the model. It samples:
- First 40% of pages
- Middle 20% of pages
- Last 40% of pages

Respect `rag_max_chars_per_book` (from system config) as the character budget for the input text.

### Guidelines
- **Be specific**: proper nouns and technical terms, not general paraphrases.
- **Be dense**: no filler. Every token counts for vector quality.
- **Retrieval focus**: write to match what a user would type in a search box.

---

## CATEGORY_PROMPT — Structure and Rules

```python
CATEGORY_PROMPT = """You are a librarian efficiently categorizing a user's question...

Available Categories: {categories}
User's New Question: "{question}"

Task: Identify which of the available categories are most relevant...
{format_instructions}"""
```

| Placeholder | What goes in |
|-------------|-------------|
| `{categories}` | Comma-separated list of book category names available in the library |
| `{question}` | The raw user question |
| `{format_instructions}` | LangChain output parser instructions (list format) |

The model returns a list — empty list means "general question, no category match." This result drives the hierarchical RAG book selection in `standard_rag.py`.

---

## Prompt Engineering Rules for This Project

### 1. Language
- All prompts that produce Uyghur output must explicitly say "Write in Uyghur (Arabic/Perso-Arabic script)."
- Never assume the model defaults to Uyghur — state it explicitly.
- For prompts that accept Uyghur input (OCR, RAG), note the script name so the model doesn't transliterate.

### 2. Structure
- Use XML-style sections (`<rules>`, `<guidelines>`) for long prompts — they help the model weight sections correctly.
- Use `{placeholders}` for all dynamic values — never f-string interpolation inside the constant itself.
- Keep the constant pure: no runtime logic, no conditional sections, no Python expressions.

### 3. Output format
- If the output must be parseable (list, JSON, table), specify the exact format and provide an example.
- For structured output, use LangChain output parsers — pass `{format_instructions}` as a placeholder and inject at call time.
- Never ask the model to "try to" follow a format — state it as a hard requirement.

### 4. Negative instructions
- Explicitly state what NOT to do (e.g., "Do NOT translate", "Do NOT add commentary").
- The OCR `<critical_rules>` block is a proven pattern — use it for any safety-critical constraint.

### 5. Length and density
- OCR prompts: include all character accuracy rules even if long — precision beats brevity for transcription.
- Summary prompts: specify word counts per section so the model doesn't write one-liners.
- RAG instructions: keep the `{instructions}` block concise — it's injected at runtime per-book; avoid token bloat.

### 6. Embedding-optimized text
- Summaries and indexed text are embedded as vectors — they must be **information-dense**.
- Avoid meta-commentary ("This book is about...") — use direct, noun-heavy phrasing.
- Include hypothetical queries: they align the document vector with real user query vectors.

### 7. Thinking models
- OCR uses `thinking_budget=1024` (low) — fast, deterministic, acceptable for structured transcription.
- `include_thoughts=False` is set globally — thinking tokens are suppressed from output but still influence quality.
- Do not reference "think step by step" or chain-of-thought in prompts — the model handles this internally.

---

## Adding or Editing a Prompt

### Editing an existing prompt
1. Read the current constant in `prompts.py`.
2. Understand which use case and model it targets (see table above).
3. Make the change — test with a representative input before committing.
4. If the edit changes output format, update any downstream parsers or text-cleaning logic (`ocr_service.py` cleans Uyghur text post-OCR; `answer_builder.py` post-processes RAG output).

### Adding a new prompt
1. Add the constant to `prompts.py` — uppercase name, e.g. `MY_TASK_PROMPT`.
2. Use `{placeholders}` for all dynamic values — format at call time with `.format(key=value)`.
3. Document which model/temperature/thinking_budget it expects (in a comment above the constant).
4. Call it through `generate_text()`, `generate_text_with_image()`, or `build_text_llm()` — never call the Gemini SDK directly.
5. If it's a new worker task, read the model name from `SystemConfigsRepository` at job startup.
6. If it produces structured output, write a LangChain output parser and inject `{format_instructions}`.
7. Add the system config key + default value to `packages/backend-core/app/db/seeds.py`.

### Testing a prompt change
- For OCR: run `manual_scan.py` with `run_ocr_scanner` to requeue pages and inspect OCR output.
- For summaries: run `summary_job` manually against a known book and inspect `book_summaries.text`.
- For RAG: use the chat endpoint directly and compare responses before/after.
- For categorization: test with questions from known categories and verify the returned list.

---

## Common Mistakes

| Mistake | Why It's Wrong | What to Do Instead |
|---------|---------------|-------------------|
| Hardcoding model name in prompt constant | Model changes require code deploy | Read from `SystemConfigsRepository` at call time |
| f-string interpolation in the constant | Dynamic content mixes with static template | Use `{placeholder}` + `.format()` at call time |
| Calling Gemini SDK directly | Bypasses circuit breaker and rate limiter | Use `generate_text()` / `build_text_llm()` |
| Asking for Uyghur without specifying the script | Model may output Latin-script transliteration | Always say "Perso-Arabic script" |
| Adding retry logic in the service layer | Conflicts with circuit breaker state | Let `ocr_service.py` backoff + breaker handle it |
| Removing `<critical_rules>` for brevity | OCR accuracy degrades on Uyghur characters | Keep all character accuracy rules |
| Omitting negative instructions | Model fills gaps with unwanted behavior | Explicitly state what NOT to output |
| Writing embedding text with filler phrases | Dilutes vector with low-signal tokens | Use noun-heavy, information-dense phrasing |
| Adding instructions block inside `RAG_PROMPT_TEMPLATE` | Template is shared; per-book instructions vary | Inject via `{instructions}` placeholder at runtime |
