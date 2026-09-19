# LLM Token / Cost Optimization (TODOs)

**Branch:** `feature/surya-ocr-client`
**Date:** 2026-09-18
**Status:** Closed 2026-09-19 — TODO 1 and TODO 8 fixed (the two confirmed real bugs); TODO 6 completed separately; TODO 2/3/4(partial)/5/7 skipped by decision, reasoning kept below for anyone revisiting this later.

---

## 1. Background & Objective

Kitabim.AI makes Gemini LLM calls across the chat/RAG path (query-signal extraction, retrieval agent, reranker, answer agent, async judge), the worker pipeline (OCR, LLM spell-check, knowledge-graph extraction, history-dictionary extraction), and embedding ingestion. A codebase survey (2026-09-18) found zero use of Gemini explicit prompt caching anywhere, several sites with likely redundant token spend, and gaps in the cost instrumentation added in commit `554559a`. This doc tracks the investigation and fixes.

Existing cost instrumentation (`packages/backend-core/app/llm/cost_tracker.py`, migration `092_add_llm_cost_tracking_to_rag_evaluations.sql`) only covers the live chat/RAG turn + async judge — not OCR, spell-check, KG extraction, history extraction, or bulk embeddings.

---

## 2. Inventory of TODO Items

### TODO 1: Unbounded ADK session history replay on every chat turn — FIXED 2026-09-18
- **Target Files:**
  - [`services/backend/main.py:158-176`](file:///Users/Omarjan/Projects/kitabim-ai/services/backend/main.py) — `DatabaseSessionService` wired to the app's own Postgres engine (persistent, not `InMemorySessionService`)
  - [`packages/backend-core/app/services/chat/orchestrator.py:444-505`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/chat/orchestrator.py) — retrieval agent `Runner` uses `session_id=conv_id`
  - [`packages/backend-core/app/services/chat/orchestrator.py:660-687`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/chat/orchestrator.py) — answer agent `Runner`, same `session_id=conv_id`
  - [`packages/backend-core/app/services/chat/retrieval_agent.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/chat/retrieval_agent.py) / `answer_agent.py` — no `include_contents` override
- **Problem:**
  Both agents are built with `Agent.include_contents` left at its ADK default of `'default'`, which per `google/adk/flows/llm_flows/contents.py` means "include full conversation history" from `invocation_context.session.events`. Because the session is persistent and keyed by `conv_id` (not reset or scoped per turn), every retrieval-agent LLM call replays **all prior turns'** tool calls and tool responses (raw chunk-text observations) in that conversation, and every answer-agent call replays all prior turns **plus** re-stuffs the full current-turn RAG context (up to `rag_vector_top_k`=25 chunks) fresh into `instruction` on top of that. The app also constructs `Runner` directly rather than via an ADK `App(events_compaction_config=...)`, so ADK's own compaction feature (`runners.py`, `if self.app and self.app.events_compaction_config`) never engages — nothing bounds growth.

  This is confirmed from the ADK library source, not inferred — no code was found anywhere in `services/chat/` or `services/backend/` that sets `include_contents` or configures `events_compaction_config`.

  Real dev data (`conversation_messages`, queried 2026-09-18) shows conversations already reaching 5 turns (10 messages) locally with no cap in place; production conversations are not bounded either.
- **Fix applied:** `include_contents` stays at ADK's default (`'default'`) — the retrieval agent's `[Context]` line "Chat history: Available" and the answer agent's session-only memory both depend on real cross-turn replay, so switching to `'none'` would silently break that. Instead, bounded it using ADK's own first-class (non-experimental) mechanism: `RunConfig(get_session_config=GetSessionConfig(num_recent_events=N))`, passed to both `runner.run_async()` calls in `orchestrator.py`. `N` is DB-backed and tunable without a deploy:
  - `rag_agent_session_recent_events` (default 50) — retrieval agent, more events/turn due to tool-call loop
  - `rag_answer_session_recent_events` (default 12) — answer agent, no tools, far fewer events/turn
  - Seeded in `packages/backend-core/app/db/seeds.py`; fallback constants `_AGENT_SESSION_RECENT_EVENTS_DEFAULT` / `_ANSWER_SESSION_RECENT_EVENTS_DEFAULT` in `orchestrator.py` if the config row is missing/unparsable.
  - Two new tests added to `test_adk_orchestrator.py` verifying the config value reaches `RunConfig.get_session_config.num_recent_events` on both agents, and that bad config falls back to the hardcoded defaults. Full suite (44 tests) passes.
  - Verified locally: rebuilt backend, applied migration 092 (cost-tracking columns, was pending on the dev DB) and the new `system_configs` seeds, ran a real 4-turn conversation end-to-end through `ChatOrchestrator` against a real book/user in the dev DB — no errors, session windowing engaged as configured.

- **New finding surfaced while verifying (not yet triaged — see TODO 8):** turn 1 of that live smoke test — a *fresh* conversation with no prior turns to replay — already logged **1.4M input tokens** for the retrieval agent stage alone (`rag_evaluations.input_tokens`). Since there were no prior turns, this cannot be attributed to the cross-turn replay bug just fixed; it points to something else (likely growth *within* a single turn's tool-calling loop, or an oversized tool observation). This is a real, deployed-and-metered issue in current `main`, not a probe artifact — it likely dwarfs the cross-turn issue in $ terms and needs its own dedicated investigation.

---

### TODO 2: No cost tracking on bulk/batch embedding ingestion — SKIPPED 2026-09-19
- **Status:** Skipped for now, by decision, after re-scoping made clear it's not the small fix it looked like.
- **Target Files:**
  - [`packages/backend-core/app/llm/models.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/llm/models.py) — `GeminiEmbeddings.aembed_documents` (bulk path, no tracking) vs `aembed_query` (L691, tracked with an estimated `len(text)//4`)
  - [`packages/backend-core/app/llm/cost_tracker.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/llm/cost_tracker.py)
- **Problem:** The chunk-embedding ingestion path (used for every book's full chunk set) has zero cost visibility, unlike every other LLM call site.
- **Why the original proposed solution was wrong:** the original plan here ("copy `aembed_query`'s `cost_tracker.add()` pattern into `aembed_documents`") doesn't work — that pattern is gated by `if get_current_query_context() is not None`, which only ever succeeds inside a live chat turn. Checked every call site of `aembed_documents` (`embedding_job.py`, `summary_job.py`, `history_extraction_service.py`, `entity_resolution_service.py`, `books_router.py:2659`) — none run inside a chat turn's `QueryContext`, so copying the pattern would be dead code that never actually records anything.
- **Real scope, if picked up later:** this is the same underlying gap as TODO 3 (no persistence destination for worker/batch-context LLM cost — `rag_eval_job.py`'s async judge is the only precedent, and it bypasses `cost_tracker`/`QueryContext` entirely, computing `estimate_cost_usd()` directly and writing straight to its own row). Fixing TODO 2 properly means designing that persistence destination once and reusing it for TODO 3's jobs too, not solving it twice. Revisit together if either is picked back up.

---

### TODO 3: No cost visibility for worker-side jobs (OCR, spell-check, KG extraction, history extraction) — SKIPPED 2026-09-19
- **Status:** Skipped by decision. See TODO 2 — shares the same underlying design gap (no persistence destination for worker/batch-context LLM cost); revisit both together if picked back up.
- **Target Files:**
  - `services/worker/jobs/ocr_job.py`, `app/services/ocr_service.py`, `app/services/batch_ocr_service.py`
  - `services/worker/jobs/llm_spell_check_job.py`, `app/services/llm_spell_check_service.py`, `app/services/batch_llm_spell_check_service.py`
  - `services/worker/jobs/knowledge_graph_job.py`
  - `app/services/batch_history_extraction_service.py`, `app/services/batch_embedding_service.py`
- **Problem:** Only the live chat/RAG turn and async judge write to `rag_evaluations.input_tokens/output_tokens/cost_usd`. These worker jobs process whole books and are likely the largest aggregate token spend, but there's no per-book or per-job cost record anywhere in the schema.
- **Proposed Solution:** Design a lightweight per-job/per-book cost record (new migration — table or columns, needs `/database-designer` + `/api-designer` first per project convention) and wire `cost_tracker`-style logging into each of the above call sites.

---

### TODO 4: Zero Gemini prompt caching anywhere — re-scoped 2026-09-19, OCR ruled out, rest SKIPPED
- **Status:** OCR candidate closed, not viable. Retrieval/answer-agent candidates skipped by decision without running the confirmatory `client.caches.create()` test — genuinely unresolved (not ruled out, just not pursued), see below if picked back up.
- **Target Files:**
  - [`packages/backend-core/app/services/rag/agent/prompts.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/prompts.py) — `AGENT_SYSTEM_PROMPT`, measured 13,127 chars (~3,281 tokens), resent verbatim as the retrieval agent's `instruction` on every call within a turn (up to `rag_agent_max_llm_calls`=12). Per `retrieval_agent.py:56-97`, this is always a clean static **prefix** — any per-turn "Structured Intent Hints" are appended as a suffix, not interleaved — good shape for caching if the size clears the model's minimum.
  - `answer_agent.py` / `answer_prompts.py` — `build_answer_instructions()` output is one of a small enumerable set of variants (branches on `strict_no_answer`/`suppress_page_notice`/`is_global`/`has_categories`/`persona_prompt`), each smaller than the retrieval agent's prompt and appended as a prefix before the per-turn `graded_context` suffix (`answer_agent.py:19-29`) — same clean shape, but every variant is a weaker candidate size-wise than OCR's already-too-small prefix.
  - ~~OCR prompt (`OCR_PROMPT` static portion + `frequent_corrections` block)~~ — **ruled out, see below.**
- **OCR closed 2026-09-19:** measured `OCR_PROMPT`'s static text before the `{frequent_corrections}` placeholder at 2,567 chars (~640 tokens). Checked Google's current caching docs (`ai.google.dev/gemini-api/docs/generate-content/caching`, fetched 2026-09-19): explicit-caching minimum for `gemini-3.7-flash` (OCR's model) is **4,096 tokens** — OCR's cacheable prefix is ~6x too small, for both explicit and implicit caching (same 4,096 floor applies to implicit caching per `ai.google.dev/gemini-api/docs/caching`). The per-page image can't help clear that floor since it's different on every call and isn't part of what's cacheable — only the byte-identical static text counts, and that alone falls short. Decision: not worth a confirmatory live test, drop this candidate.
- **Retrieval/answer agents — still open, genuinely uncertain:** Google's caching docs table doesn't list Flash-Lite variants (`gemini-3.1-flash-lite`, used by both agents) at all — a documented gap other developers have also hit (see Google AI Developer Forum thread "docs list wrong minimum for Gemini 2.5 Flash; Flash-Lite missing entirely"). The retrieval agent's ~3,281 tokens would clear a 1,024–2,048 floor (the pre-2026 Flash-tier pattern) but not necessarily a 4,096 one if Flash-Lite follows the same floor as the base Flash tier in this model generation. The answer agent's prompt is smaller still and is the weaker of the two candidates.
- **Proposed Solution:** A live `client.caches.create()` test against `gemini-3.1-flash-lite` with the real `AGENT_SYSTEM_PROMPT` text is the only way to get a definitive answer (cache creation bills for storage duration, not per-token processing, so this is cheap) — not yet run, deferred pending prioritization against TODO 2/3/5.

---

### TODO 5: Spell-check prev/next-page windowing sends each page's text ~3x — SKIPPED 2026-09-19
- **Status:** Skipped by decision. Documented as an intentional design tradeoff in `docs/main/SPELLCHECK_DESIGN.md:477`, but its token-cost implication isn't quantified anywhere — still true if picked back up.
- **Target Files:**
  - `app/services/llm_spell_check_service.py` (`build_correction_prompt`, live path)
  - `app/services/batch_llm_spell_check_service.py` (same windowing, batch/JSONL path)
- **Problem:** For each page, the prompt includes prev + current + next page full text. Since jobs process contiguous page ranges, each page's body is sent up to 3 times per full-book pass (once as target, once as another page's `prev_context`, once as another page's `next_context`).
- **Proposed Solution:** Restructure to reuse decoded neighbor text from adjacent calls instead of resending, or batch a stride of pages per call the way `knowledge_graph_job.py` already batches `kg_chunk_batch_size` chunks per call.

---

### TODO 6: `history_gemini_model` defaults to a more expensive model than every other text stage
- **Status:** Completed.
- **Target Files:** `app/services/batch_history_extraction_service.py`, `system_configs` seed (`app/db/seeds.py`) for `history_gemini_model`
- **Resolution:** Switched default from `gemini-2.5-flash` to `gemini-3.5-flash-lite` with DB migration `093`.

---

### TODO 7: OCR retry cost check — SKIPPED 2026-09-19
- **Status:** Skipped by decision, low priority.
- **Target Files:** `services/worker/jobs/ocr_job.py`, `ocr_max_retry_count` (default 10) / `ocr_max_output_tokens` (default 4096, already guards runaway single-call billing)
- **Problem:** A persistently-failing page can cost up to 10x its own call before being skipped. Real-world retry rates unknown.
- **Proposed Solution:** Check retry-rate metrics (or add them) before deciding whether to lower the cap.

---

### TODO 8: Single-turn cost anomaly — FIXED 2026-09-19 (was a cost-tracking bug, not a real token-spend problem)
- **Status:** Fixed. Root cause was entirely different from what it looked like on discovery — see below.
- **Target Files:** `packages/backend-core/app/services/chat/orchestrator.py` (both `runner.run_async()` usage-recording blocks — retrieval agent and answer agent)
- **Discovered:** 2026-09-18, during live verification of the TODO 1 fix — a fresh single turn logged 1.4M input tokens / 47.5K output tokens ($0.17) in `rag_evaluations`.
- **Root cause (confirmed, not inferred):** A per-LLM-call breakdown probe (using `ctx.cost_tracker.entries`, which already tracks every call) showed the same input-token count repeated identically across dozens of entries, with output tokens climbing steadily then plateauing — the signature of one real call being counted many times, not many real calls. Traced into the installed `google-adk` package (`utils/streaming_utils.py`, `StreamingResponseAggregator`) and reproduced offline (no API calls) with synthetic chunks: with `PROGRESSIVE_SSE_STREAMING` enabled, ADK yields one `partial=True` event per raw streaming chunk — **each carrying that chunk's own cumulative `usage_metadata` snapshot** — then a single `partial=False` event with the call's true final totals. `orchestrator.py`'s usage-recording code (both the retrieval-agent and answer-agent `runner.run_async()` loops) called `ctx.cost_tracker.add()` on **every** event with `usage_metadata`, not just the final one — so a single real LLM call streamed across, say, 41 chunks got its usage summed 41 times. This is a bug in the cost-tracking feature added in commit `554559a`, not an actual excess token spend — the real Gemini API bill was never inflated by this, only what `rag_evaluations.cost_usd` and the chat UI's cost display (`rag_chat_cost_enabled`) reported was wrong, by up to ~33x on any stage that streams (retrieval agent, answer agent).
- **Fix:** Added `and not event.partial` to both usage-recording conditions in `orchestrator.py`, with a comment explaining why. Added `test_stream_response_only_records_cost_from_final_non_partial_event` to `test_adk_orchestrator.py`, verified it fails without the fix (3 entries instead of 1) and passes with it.
- **Verified live, same conversation setup as the original anomaly:** before → 1,508,102 input / 47,460 output tokens, $0.169794. After → 44,182 input / 2,001 output tokens, $0.005219. A ~33x reduction, matching the manual de-duplication estimate (~46K tokens) calculated from the per-call breakdown before the fix was even written.
- **Follow-up worth knowing:** every `cost_usd`/`input_tokens`/`output_tokens` value already recorded in `rag_evaluations` for turns that used streaming (essentially all of them) predates this fix and is inflated by a similar factor — any historical cost analytics or dashboards built on that table before 2026-09-19 should be treated as unreliable, not just future ones.

---

## 3. Reference: baseline per-call-site table (2026-09-18 survey)

| Stage | Model (default) | Caching | Prompt size | History | Call style |
|---|---|---|---|---|---|
| Retrieval agent | `gemini-3.1-flash-lite` | none | ~15KB static instruction, resent per call (up to 12/turn) | full session replay (TODO 1) | ADK `Agent` + `Runner`, 20 tools |
| Answer agent | `gemini-3.1-flash-lite` | none | ~10KB base + up to 25 graded chunks in `instruction` | full session replay (TODO 1) | ADK `Agent`, streaming |
| Query-signal extraction | agent_model | none | ~2-3KB + last 6 messages | truncated to 6 messages | raw `generate_content` |
| Reranker | `rag_gemini_reranker_model` | none | up to 50 candidate chunks | n/a | structured JSON |
| Judge (async) | `rag_gemini_judge_model` | none | question + full context + answer | n/a | structured JSON, post-turn |
| OCR (live/batch) | `ocr_gemini_model` = `gemini-3.7-flash` | none | ~1.8KB static + corrections block + 1 page image | n/a | vision |
| LLM spell-check (live/batch) | `gemini_llm_spell_check_model` | none | prev+current+next page full text (TODO 5) | n/a | structured |
| KG extraction | `kg_gemini_extraction_model` | none | 5 chunks/call | n/a | raw `generate_content` |
| History extraction | `history_gemini_model` = `gemini-3.5-flash-lite` | none | 15-page sliding window, 2-page overlap | n/a | Batch API / live |
| Embeddings | `embed_gemini_model` = `gemini-embedding-2` | n/a | batched, 50/job | n/a | REST batch |
