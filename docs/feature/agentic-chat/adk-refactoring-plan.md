# Chat Feature Refactoring Plan — Google ADK Native Rewrite

## Executive Summary

Rewrite the chat feature (reader + global) to use Google ADK as the **primary orchestration layer** rather than a tool bolted onto a custom Python pipeline. Today ADK is used narrowly — as a ReAct agent runner (`LLMRoutedRAGHandler`) or a Workflow graph router (`DeterministicRAGHandler`) — while everything else (streaming, context building, history, eval recording, sub-question decomposition, grading) is hand-rolled Python glue. This plan consolidates that into a single ADK-native architecture.

---

## Current Architecture (problems to solve)

```
Frontend (useChat) —SSE—► chat_router.py ──► RAGService
                           │                  │
                           ▼                  ▼
              DeterministicRAGHandler    LLMRoutedRAGHandler
              (ADK Workflow graph)       (ADK Agent ReAct)
                           │                  │
                           └────── 19 tools ──┘
                                      │
                              answer_builder.py
                              (manual LLM call)
```

### Pain points

| # | Problem | Impact |
|---|---------|--------|
| 1 | **Two parallel handlers** with overlapping logic (`_grade_context`, `_extract_used_book_ids`, `_populate_ctx_from_observations` duplicated or imported cross-handler) | Maintenance burden, divergent behavior |
| 2 | **Manual streaming plumbing** — custom SSE event types, manual `async for` wrappers, hand-stitched `data: {json}\n\n` framing in `chat_router.py` | Fragile, hard to extend |
| 3 | **No server-side conversation state** — history passed from frontend each request; no session persistence | Can't resume conversations, no backend analytics on conversation flow |
| 4 | **Sub-question decomposition** is a separate LLM call (`_llm_split`) outside the agent | Extra latency, could be an agent capability |
| 5 | **Answer generation** is a separate post-agent LLM call (`answer_builder.py`) — the agent retrieves but never answers | Two-hop LLM latency (agent loop + answer generation) |
| 6 | **Context grading** is a separate LLM call after retrieval | Third LLM hop |
| 7 | **Citation fixing** is a regex post-processor in the router | Fragile, band-aid |
| 8 | **QueryContext** is a mutable god-object threaded through everything | Hard to test, implicit state |

---

## Prerequisites — Verify Blocking Fixes

The `feature/adk-2-upgrade-v2` code review (2026-07-21) raised the blocking issues below. A review of the **current** codebase shows P.1, P.2, P.4, and P.5 are already remediated on the `rag/` layer (which the rewrite preserves); only **P.3** requires an actual change. Treat this section as a pre-flight verification checklist rather than a body of new work.

| # | File | Issue | Action |
|---|------|-------|--------|
| P.1 | `rag/agent/deterministic_handler.py` | `Content(role="tool")` is not a valid Gemini role (must be `"user"` for function-response turns). | Already `role="user"` in codebase — verify only. |
| P.2 | `rag/retrieval.py` | Ungated fuzzy-keyword fallback fabricating similarity scores and caching them as real results. | Already gated to non-production and excluded from the shared cache key — verify only. |
| P.3 | `rag/retrieval.py` | Fuzzy fallback scans every chunk for the given `book_ids` with no row cap. | Add a bounded `LIMIT` on rows fetched before `SequenceMatcher` scoring (the one outstanding item). |
| P.4 | `rag/agent/graph_router.py` | `_select_route` precedence of `has_title` vs. `intent == "catalog"`. | Already covered by `graph_router_test.py` precedence tests — verify only. |
| P.5 | `rag/agent/tools.py` | Duplicated fuzzy title/author matching. | Shared `fuzzy_token_similar()` already lives in `rag/utils.py` and both call sites use it — verify only. |

---

## Target Architecture

```
Frontend (useChat) —SSE—► chat_router.py ──► ChatOrchestrator
                                                   │
                           ┌───────────────────────┴───────────────────────┐
                           ▼                                               ▼
                    Retrieval Agent                                   Answer Agent
                    ├─ model: gemini                                  ├─ model: gemini
                    ├─ retrieval prompt                               ├─ answer prompt
                    ├─ 19 tools                                       │  (strict/permissive,
                    └─ stops after                                    │   citation, persona,
                       gathering context                              │   Uyghur-only rules)
                               │                                      └─ streams final answer
                               ▼
                       graded observations
                     (passed to Answer Agent)
                               │
                               ▼
                     Conversation persistence
                     (ADK DatabaseSessionService, session_id = conversation_id
                      — native multi-turn history, no manual injection —
                      + ConversationRepository for app-level fields/frontend)
                               │
                               ▼
                     Streaming via ADK events ➔ SSE
```

### Key design decisions

1. **Two-agent pipeline with Signal Pre-Processing** — a **Retrieval Agent** (focused on tool selection and evidence gathering, keeps current `AGENT_SYSTEM_PROMPT`) hands graded observations to an **Answer Agent** (focused on synthesis, keeps current `answer_builder` instructions). To preserve domain lookup precision (exact dictionary headwords, Quran surah/ayah, catalog queries), `ChatOrchestrator` preserves `_llm_analyze_query` as a fast pre-processing step to pass structured intent hints (`dictionary_subtype`, `quran_surah/ayah`, `catalog_subtype`, `target_volume`) to the Retrieval Agent.
2. **Reader Mode Scope Enforcement** — when `is_global=False` (reader mode), tool parameters (`search_chunks`, `get_book_summary`) are strictly bound to `book_ids=[active_book_id]` via the `ToolDependencies` wrapper, preventing cross-book context leaks (recalling the Reader Page Book Scope fix).
3. **Concurrent Sub-Question Handling** — if pre-processing detects a composite question (`is_composite=True`), `ChatOrchestrator` dispatches sub-question retrieval concurrently (reusing `_merge_sub_question_streams` logic) before aggregating context for the Answer Agent, preventing p95 latency spikes.
4. **Conversation persistence via ADK's built-in `DatabaseSessionService`** — `google.adk.sessions.DatabaseSessionService` is constructed once at backend startup (`lifespan`), pointed at the app's existing `AsyncEngine` (`app.db.session.engine`, no second connection pool), and stored on `app.state`. `session_id` is set to `conversation_id` and **reused across every turn** of a conversation, for both the retrieval-app and answer-app namespaces. ADK reconstructs conversation context natively from the session's own accumulated `events` — there is no `history=` parameter on `Runner.run_async()` (checked against the pinned `google-adk==2.5.0`; it doesn't exist in this or any released version) and no manual `types.Content` list to build or pass. `Runner` is constructed with `auto_create_session=True` so the first turn of a conversation transparently creates the session and later turns reuse it — no explicit get-or-create branching needed in `ChatOrchestrator`.
   - **`ConversationRepository` / `Conversation` + `ConversationMessage` tables are still needed**, but scoped down: they hold app-level fields ADK's session store doesn't (`used_book_ids`, `eval_id`, `current_page`, per-turn agent step summaries) and back the frontend's conversation-list/resume endpoints (Phase 2.3/2.4). They are **not** the source of truth the model reads from — ADK's own session/event store is.
   - **Accepted deviation from "migration file first"**: `DatabaseSessionService` self-manages its own schema (`sessions`, `events`, `app_states`, `user_states`, `adk_internal_metadata` tables, on its own private SQLAlchemy `Base`) and auto-creates it at runtime via `metadata.create_all()` the first time it's used (`prepare_tables()`), versioned internally by ADK — it does not go through `packages/backend-core/migrations/`. This is a deliberate, documented exception: these tables are framework-owned runtime state, not application business data, so they're exempt from the migration-first rule the way third-party library-managed schemas generally are. Call `prepare_tables()` once during backend `lifespan` startup (after `init_db()`) so first-request latency isn't spent creating tables.
5. **ADK native streaming & Citation Safety Net** — use `Runner.run_async()` event streams directly for both agents. Retain `fix_malformed_citations` in `chat_router.py` on stream completion as a non-blocking safety net to guarantee citation tag format compliance for frontend pill rendering.
6. **DTO boundary first, tool migration later** — introduce the immutable `ChatRequestDTO` + `ToolDependencies` at the *orchestrator boundary* in Phase 1 (low-risk, no tool changes; orchestrator constructs a backward-compatible `QueryContext`). Migrating the 19 tools off `tool_context.state["query_context"]` is a separate, more invasive step in Phase 1.1b.
7. **Sub-agents deferred** — domain sub-agents (dictionary, Quran, catalog) are a future consideration, not a planned phase. Revisit only if the Retrieval Agent demonstrably struggles with domain-specific tool selection after the refactoring is live.

---

## Phased Implementation

### Phase 0 — Preparation & Foundation (1 week)

**Goal**: Set up infrastructure without changing any user-facing behavior.

| Task | Files | Details |
|------|-------|---------|
| 0.1 | `packages/backend-core/app/services/chat/` | Create new `chat/` package alongside existing `rag/` |
| 0.2 | `packages/backend-core/app/db/models.py` | Add `Conversation` model (id, user_id, book_id, is_global, created_at, updated_at) |
| 0.3 | `packages/backend-core/app/db/models.py` | Add `ConversationMessage` model (id, conversation_id FK, role, content, agent_steps JSON, used_book_ids JSON, current_page, eval_id FK nullable, created_at) |
| 0.3b | `packages/backend-core/app/db/models.py` | Update `RAGEvaluation` model: add `conversation_id` FK (nullable) to track evaluation metrics across multi-turn sessions |
| 0.4 | `packages/backend-core/migrations/` | Migration for `conversations` + `conversation_messages` tables and `rag_evaluations.conversation_id` FK |
| 0.5 | `packages/backend-core/app/db/repositories/` | `ConversationRepository` — extends `BaseRepository[ConversationMessage]` (matching `RAGEvaluationsRepository` and other existing repos), exposed via a `get_conversation_repository(session)` factory. CRUD for conversations + messages — app-level fields only (`used_book_ids`, `eval_id`, `current_page`, agent step summaries); not the source of the model's conversation context. |
| 0.6 | `services/backend/main.py` (lifespan) | Construct `DatabaseSessionService(db_engine=app.db.session.engine)` once at startup (after `init_db()`), call `await session_service.prepare_tables()` so schema creation happens at boot rather than on first chat request, store on `app.state.adk_session_service`. `packages/backend-core/app/services/chat/history.py` is no longer needed to build `types.Content` history for the `Runner` — ADK owns that natively via `session_id = conversation_id` reuse (see design decision 4). Repurpose it (or fold into `orchestrator.py`) to format `ConversationMessage` rows for the frontend's history endpoints only. |
| 0.7 | `packages/shared/src/types.ts` | Add `Conversation`, `ConversationMessage` TS types |
| 0.8 | `packages/backend-core/app/services/rag/context.py` | Audit `QueryContext` — identify fields to split into immutable `ChatRequestDTO` vs. `ToolDependencies` (prep for Phase 1) |

**Migration SQL sketch** (matches codebase conventions — `VARCHAR(36)` ids via the `uuid-ossp` extension, not native `UUID`/`gen_random_uuid()`; string `book_id` FK to `books`; `is_global` flag for global chat):
```sql
CREATE TABLE conversations (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    book_id VARCHAR(64) REFERENCES books(id) ON DELETE SET NULL, -- NULL for global chat
    is_global BOOLEAN NOT NULL DEFAULT FALSE,
    title VARCHAR(200), -- auto-generated from first message
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE conversation_messages (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id VARCHAR(36) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL, -- 'user' | 'model'
    content TEXT NOT NULL,
    agent_steps JSONB,
    used_book_ids JSONB, -- list of book_ids cited in this turn
    current_page INTEGER, -- page active when turn was asked
    eval_id INTEGER REFERENCES rag_evaluations(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_conversation_messages_role CHECK (role IN ('user', 'model'))
);

-- Link multi-turn sessions to evaluation tracking
ALTER TABLE rag_evaluations
ADD COLUMN conversation_id VARCHAR(36) REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC);
CREATE INDEX idx_conv_msg ON conversation_messages(conversation_id, created_at);
CREATE INDEX idx_eval_conv ON rag_evaluations(conversation_id);
```

### Phase 1 — Two-Agent Pipeline & QueryContext Split (2 weeks)

**Goal**: Replace both handlers with a Retrieval Agent + Answer Agent pipeline. Refactor `QueryContext` so tools no longer depend on a mutable god-object.

| Task | Files | Details |
|------|-------|---------|
| 1.1 | `chat/context.py` | Introduce the immutable `ChatRequestDTO` (question, book_id, is_global, user_id, current_page, character_id, conversation_id, history, context_book_ids) and a `ToolDependencies` container (session, embeddings, chains) as the **orchestrator boundary**. This is low-risk and touches no tools. |
| 1.1b | `rag/agent/tools.py` (+ callers) | **Separate, invasive step:** migrate the 19 tools off `tool_context.state["query_context"]` to explicit `ToolDependencies` injection. May be deferred past initial rollout — until then the orchestrator builds a `QueryContext` from the DTO so the existing tools keep working unchanged. |
| 1.2 | `chat/retrieval_agent.py` | `build_retrieval_agent()` — ADK `Agent` using current `AGENT_SYSTEM_PROMPT` (retrieval-focused, tool-selection only). Keeps existing 19 tools. Stops after gathering context, does NOT generate the answer. |
| 1.3 | `chat/answer_agent.py` | `build_answer_agent()` — ADK `Agent` or direct `generate_content` call using current `answer_builder.py` instructions (strict/permissive mode, multi-volume synthesis, citation format, persona injection, Uyghur-only output rules). Receives graded observations as context, streams the final answer. |
| 1.4 | `chat/orchestrator.py` | `ChatOrchestrator` class. **Stage A (low-risk):** wrap the existing streaming pipeline (`RAGService.answer_question_stream`) to add conversation persistence — load PRIOR history *before* persisting the current user turn (so it isn't duplicated in the history window), stream, then persist the model turn with its `eval_id`. **Stage B (gated by Phase 1.5):** swap the internals to the Retrieval Agent ➔ grade ➔ Answer Agent pipeline. Deriving `is_first_turn` from the loaded server-side history comes for free in Stage A. |
| 1.5 | `chat/orchestrator.py` | Preserve the `str \| dict` SSE event contract of `RAGService.answer_question_stream` so the router swaps pipelines behind the flag with no SSE-handling changes. For Stage B, reuse the ADK event extraction logic from `LLMRoutedRAGHandler._execute_workflow_stream` (`function_call`/`function_response`/text ➔ `tool_call`/`tool_result`/`chunk`). No separate `streaming.py` needed. |
| 1.6 | `chat/orchestrator.py` | Audit `_llm_analyze_query`'s signal extraction from `DeterministicRAGHandler` — decide which signals (`dictionary_subtype`, `quran_surah/ayah`, `catalog_subtype`, `is_composite`, `sub_questions`) should feed into the Retrieval Agent's prompt context or become structured pre-processing. The intent taxonomy is valuable for eval metadata even if routing is now implicit. |

**Two-agent behavior flow:**
- Step 0: Fast signal pre-processing (`_llm_analyze_query`, using recent turns from `ConversationRepository`) ➔ intent hints (`dictionary_subtype`, `quran_surah/ayah`, `catalog_subtype`, `is_composite`, `sub_questions`)
- Step 1: Retrieval Agent runs via `Runner.run_async(session_id=conversation_id, ...)` — reusing the same `session_id` across turns lets ADK's `DatabaseSessionService` reconstruct multi-turn context from its own accumulated events natively (tool calls with enforced reader scoping, observations collected) ➔ stops
- Step 2: Context grading (`_grade_context` from current handlers) ➔ graded observations
- Step 3: Answer Agent runs via ADK `Runner` (same `session_id`, separate `app_name`) ➔ generates + streams the answer
- Step 4: Terminal citation safety check (`fix_malformed_citations`) + app-level message persistence (`used_book_ids`, `eval_id`) & eval recording — the raw conversational turns themselves are already persisted by ADK via the `Runner` calls above, this step only writes the fields ADK's session store doesn't track

**ChatOrchestrator pseudocode:**
```python
class ChatOrchestrator:
    def __init__(self, session_service: DatabaseSessionService, conversation_repo: ConversationRepository):
        # session_service is constructed ONCE in backend lifespan (DatabaseSessionService(db_engine=...),
        # pointed at the existing app engine) and injected — not created per request/per instance.
        self.session_service = session_service
        self.conversation_repo = conversation_repo

    async def stream_response(self, conv_id, question, user_id, book_id, is_global, db_session):
        # 1. Fast pre-processing: extract query intent signals. Recent turns come from our own
        #    ConversationRepository (needed anyway for the frontend's history endpoints) — this
        #    is NOT how conversation context reaches the agents below; that's handled by ADK
        #    natively via session_id reuse (see step 2).
        history_rows = await self.conversation_repo.get_recent_messages(conv_id, db_session)
        signals = await llm_analyze_query(question, history_rows, is_global, book_id)

        # 2. Retrieval Agent — gather evidence with strictly scoped tool dependencies.
        #    session_id = conv_id, reused across every turn: ADK reconstructs conversation
        #    context itself from the session's own accumulated events. There is no `history=`
        #    kwarg on Runner.run_async (checked against the pinned google-adk==2.5.0 — it
        #    doesn't exist in any released version) and none is needed with this design.
        tool_deps = ToolDependencies(db_session=db_session, active_book_id=book_id if not is_global else None)
        retrieval_agent = build_retrieval_agent(model, intent_signals=signals)
        retrieval_runner = Runner(
            agent=retrieval_agent,
            app_name="kitabim-retrieval",
            session_service=self.session_service,
            auto_create_session=True,  # first turn creates the session; later turns reuse it
        )

        observations = []
        async for event in retrieval_runner.run_async(
            user_id=str(user_id),
            session_id=conv_id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=question)]),
        ):
            yield translate_event(event)  # tool_call / tool_result SSE events
            observations.extend(extract_observations(event))

        # 3. Context Grading
        graded_context, kept, total = grade_context(observations)
        yield {"type": "grading", "before": total, "after": kept}

        # 4. Answer Agent — generate and stream synthesis from graded context.
        #    Separate app_name ("kitabim-answer") but the SAME session_id=conv_id and SAME
        #    session_service, so the answer agent's own turn history also accumulates natively.
        yield {"type": "answer_start"}
        answer_agent = build_answer_agent(model, persona_prompt, graded_context)
        answer_runner = Runner(
            agent=answer_agent,
            app_name="kitabim-answer",
            session_service=self.session_service,
            auto_create_session=True,
        )

        accumulated_text = ""
        async for event in answer_runner.run_async(
            user_id=str(user_id),
            session_id=conv_id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=question)]),
        ):
            chunk = extract_text_chunk(event)
            if chunk:
                accumulated_text += chunk
                yield {"type": "chunk", "text": chunk}

        # 5. Safety check & Persistence — app-level fields only. ADK already persisted the raw
        #    turns in its own `sessions`/`events` tables via the Runner calls above.
        fixed_text = fix_malformed_citations(accumulated_text)
        used_book_ids = extract_used_book_ids(observations)
        eval_id = await record_eval(question, fixed_text, observations, conv_id, db_session)
        await self.conversation_repo.save_turn(conv_id, question, fixed_text, used_book_ids, eval_id, db_session)
```

### Phase 1.5 — Eval Baseline & Regression Testing (3 days)

**Goal**: Establish a quality baseline and verify the two-agent pipeline matches current answer quality before wiring it to the frontend.

| Task | Files | Details |
|------|-------|---------|
| 1.5.1 | `tests/` | Run existing eval suite (`deterministic_eval/test_deterministic_router.py` with `AgentEvaluator`) against the current pipeline to capture baseline scores (faithfulness, answer relevance, context precision). |
| 1.5.2 | `tests/` | Run the same eval suite against the new `ChatOrchestrator` two-agent pipeline. Compare retrieval quality (tool calls, chunk counts) and answer quality (eval scores) side-by-side. |
| 1.5.3 | `tests/` | Verify all 10 intent categories produce equivalent-quality answers: `current_page`, `quran`, `dictionary`, `catalog`, `named_title`, `named_author`, `volume_shift`, `in_reader`, `context_books`, `open/general`. |
| 1.5.4 | `tests/` | Benchmark p50/p95 latency of the two-agent pipeline vs. current pipeline. Two-agent should be comparable (Retrieval Agent replaces ReAct loop; Answer Agent replaces `answer_builder` LLM call — same number of LLM hops, but with focused prompts). |

**Gate**: Do NOT proceed to Phase 2 unless eval scores are ≥ current baseline. If scores regress, iterate on Retrieval Agent prompt or Answer Agent instructions before moving on.

**Test environment**: The repo has no local Python dependencies — the backend runs only in Docker. Run unit tests and the eval suite inside the backend container (`./deploy/local/rebuild-and-restart.sh backend`, then `python -m pytest ...`), not against a host `.venv`. Editor/Pylance static analysis validates types but cannot execute the suite.

---

### Phase 2 — Frontend & API Integration (1 week)

**Goal**: Wire the new backend to the existing frontend with minimal UI changes.

| Task | Files | Details |
|------|-------|---------|
| 2.1 | `services/backend/api/endpoints/chat_router.py` | Add `use_adk_chat_v2` feature flag check (from `system_configs`). When enabled, the existing `POST /api/chat/stream` endpoint routes to `ChatOrchestrator` instead of `RAGService`. No URL-level version bump — the frontend is a single SPA with no third-party consumers. |
| 2.2 | `services/backend/api/endpoints/chat_router.py` | `POST /api/chat/conversations` — create conversation, returns `conversation_id` |
| 2.3 | `services/backend/api/endpoints/chat_router.py` | `GET /api/chat/conversations` — list user's conversations (for future sidebar) |
| 2.4 | `services/backend/api/endpoints/chat_router.py` | `GET /api/chat/conversations/{id}/messages` — load conversation history |
| 2.5 | `apps/frontend/src/hooks/useChat.ts` | Update to create/resume conversations via API. Send optional `conversation_id` alongside existing params. When `conversation_id` is present, omit `history[]` (server-side history takes over). |
| 2.6 | `apps/frontend/src/services/geminiService.ts` | Update `chatWithBookStream()` to accept optional `conversationId` parameter. Same SSE parsing, same endpoint URL. |
| 2.7 | `packages/shared/src/types.ts` | Add optional `conversation_id` to `ChatRequest`. Add `Conversation`, `ConversationMessage` types. |
| 2.8 | Feature flag | `system_configs` key `use_adk_chat_v2` (default `false`) — backend checks this per-request to route to v1 or v2 pipeline |

**SSE protocol stays identical** — the frontend doesn't need to change its event parsing. The request shape change (adding optional `conversation_id`) is backward-compatible. When `conversation_id` is absent, the backend falls back to `history[]`-based behavior (v1 compatibility). The only additive delta is a new optional `conversationId` field on the terminal `done` event, so the client can capture and resume the server-side conversation; older clients simply ignore it.

**Migration path:**
1. Deploy with `use_adk_chat_v2=false` — everything uses old pipeline
2. Enable for testing: `use_adk_chat_v2=true`
3. Once validated, remove v1 code and feature flag

---

### Phase 3 — Cleanup & Deprecation (1 week)

| Task | Details |
|------|---------|
| 3.1 | Remove `use_adk_chat_v2` feature flag, make v2 the default |
| 3.2 | Delete `rag/agent/deterministic_handler.py` |
| 3.3 | Delete `rag/agent/llm_routed_handler.py` |
| 3.4 | Delete `rag/agent/graph_router.py` |
| 3.5 | Delete `rag/registry.py` (no more handler dispatch) |
| 3.6 | Delete `rag/base_handler.py` |
| 3.7 | Keep `rag/answer_builder.py` — instructions are reused by the Answer Agent; refactor into `chat/answer_prompts.py` and delete the original |
| 3.8 | Keep `rag/retrieval.py`, `rag/agent/tools.py` (tools are reused as-is) |
| 3.9 | Delete old `rag/context.py` (replaced by `chat/context.py`'s `ChatRequestDTO` + `ToolDependencies`) |
| 3.10 | Update `rag_service.py` to delegate to `ChatOrchestrator` (or remove entirely) |
| 3.11 | Remove `history` field from `ChatRequest` schema (history is server-side now) |
| 3.12 | Update all tests |
| 3.13 | Update design docs |

---

### Future Consideration — Sub-Agents & Advanced Features

> **Status**: Deferred. Do not plan or implement until the two-agent pipeline (Phases 0–3) is live and validated. Revisit only if the Retrieval Agent demonstrably struggles with domain-specific tool selection in production.

The ideas below are preserved for future evaluation:

| Idea | Details |
|------|---------|
| F.1 | **DictionaryAgent** — sub-agent with only dictionary tools. Parent delegates dictionary questions to it. Risk: adds inter-agent delegation latency; current tools already handle this domain via prompt routing. |
| F.2 | **QuranAgent** — sub-agent with `search_quran` tool. Isolated prompt tuned for Quran Q&A. |
| F.3 | **CatalogAgent** — sub-agent with catalog tools. |
| F.4 | **Conversation title generation** — after first model response, auto-generate conversation title via lightweight LLM call |
| F.5 | **Conversation sidebar UI** — list past conversations, click to resume |
| F.6 | **Multi-turn context window management** — token budget pruning on conversation history |

---

## File Impact Map

### New files
```
packages/backend-core/
  app/services/chat/
    __init__.py
    context.py            # ChatRequestDTO (immutable) + ToolDependencies (injected via closure)
    retrieval_agent.py    # build_retrieval_agent() — focused ADK agent for evidence gathering
    answer_agent.py       # build_answer_agent() — ADK agent/call for synthesis from graded context
    answer_prompts.py     # Answer generation instructions (migrated from answer_builder.py)
    orchestrator.py       # ChatOrchestrator — replaces RAGService + registry
    history.py            # Format ConversationMessage rows for the frontend history endpoints
                           # and for _llm_analyze_query context — NOT for feeding the ADK Runner
                           # (ADK owns model-facing history natively via session_id reuse)
  app/db/repositories/
    conversation_repository.py
  migrations/
    XXXX_add_conversations.sql   # app tables only — ADK's own sessions/events/app_states/
                                 # user_states tables are auto-created by DatabaseSessionService
                                 # at runtime, not via this migration (documented exception)
```

### Modified files
```
packages/backend-core/app/db/models.py                   # +Conversation, +ConversationMessage
services/backend/main.py                                 # lifespan: construct DatabaseSessionService
                                                           # (db_engine=app.db.session.engine), call
                                                           # prepare_tables(), store on app.state
services/backend/api/endpoints/chat_router.py            # feature flag routing (same URL, v1 vs v2 pipeline)
apps/frontend/src/hooks/useChat.ts                        # optional conversation_id support
apps/frontend/src/services/geminiService.ts               # optional conversationId param (same endpoint)
packages/shared/src/types.ts                             # +Conversation types, optional conversation_id in ChatRequest
packages/backend-core/app/services/rag/agent/tools.py   # adapt to ToolDependencies injection
```

### Deleted files (Phase 3)
```
packages/backend-core/app/services/rag/agent/deterministic_handler.py
packages/backend-core/app/services/rag/agent/llm_routed_handler.py
packages/backend-core/app/services/rag/agent/graph_router.py
packages/backend-core/app/services/rag/answer_builder.py   # migrated to chat/answer_prompts.py
packages/backend-core/app/services/rag/registry.py
packages/backend-core/app/services/rag/base_handler.py
packages/backend-core/app/services/rag/context.py          # replaced by chat/context.py
```

### Preserved files (tools & retrieval stay)
```
packages/backend-core/app/services/rag/agent/tools.py         # 19 tools reused (adapted for ToolDependencies)
packages/backend-core/app/services/rag/agent/adk_agent.py      # replaced by chat/retrieval_agent.py; delete after migration
packages/backend-core/app/services/rag/agent/prompts.py        # retrieval prompt reused by retrieval_agent.py
packages/backend-core/app/services/rag/retrieval.py            # vector search logic reused by tools
packages/backend-core/app/services/rag/keywords.py             # regex patterns reused
packages/backend-core/app/services/rag/utils.py                # shared helpers (+ new fuzzy_word_match)
```

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| **Answer quality regression** — two-agent handoff may lose context nuance compared to current grading + answer_builder flow | Answer Agent reuses exact `answer_builder` instructions (proven prompts); Phase 1.5 eval gate blocks rollout until scores match baseline |
| **Retrieval quality regression** — removing deterministic handler's structured signal extraction may degrade routing for edge-case intents (volume_shift, catalog_subtype) | Preserve `_llm_analyze_query` fast pre-processing stage to pass structured intent signals (`quran_surah/ayah`, `dictionary_subtype`, `catalog_subtype`) to Retrieval Agent prompt context |
| **Reader Mode scope leak** — retrieval agent searches across all books when user is reading a specific book | Strictly enforce `book_ids=[active_book_id]` in `ToolDependencies` wrapper when `is_global=False` |
| **Latency change** — two-agent sequential pipeline & sub-question processing adds overhead | Fast pre-processing dispatches sub-question retrieval concurrently (`_merge_sub_question_streams`); two-agent loop maintains same LLM hop count. Benchmark in Phase 1.5. |
| **QueryContext refactor breaks tools** — all 19 tools currently pull `ctx` from `tool_context.state["query_context"]` | Decouple boundary: Phase 1 orchestrator builds backward-compatible `QueryContext` from DTO so existing tools work unchanged; invasive tool signature migration deferred to Phase 1.1b |
| **Streaming format change** — reusing `_execute_workflow_stream`'s event extraction may miss edge cases when running under a different Runner configuration | Reuse proven extraction logic, add integration tests against real ADK events in Phase 1.5 |
| **Feature flag complexity** — running two pipelines in parallel | Time-box: remove v1 within 2 weeks of v2 launch |
| **Citation formatting errors** — LLM occasionally outputs unparsed citation tag variants | Retain `fix_malformed_citations` in `chat_router.py` stream completion as a non-blocking safety net for frontend pill rendering |
| **Fuzzy fallback in retrieval.py** — currently ungated and caches fabricated scores alongside real results | Fix in Prerequisites (P.2/P.3) before refactoring begins |
| **ADK-owned session schema bypasses migration-first convention** — `DatabaseSessionService` auto-creates its own `sessions`/`events`/`app_states`/`user_states` tables via `metadata.create_all()` at runtime, not through `packages/backend-core/migrations/` | Accepted as a documented exception (framework-owned runtime state, not app business data); call `prepare_tables()` once during backend `lifespan` startup so schema creation happens at boot, not on the first chat request; re-verify table names/shape don't collide with app tables on every `google-adk` version bump |

---

## Success Criteria

1. **Functional parity**: All 10 intent categories (current_page, quran, dictionary, catalog, named_title, named_author, volume_shift, in_reader, context_books, open/general) produce equivalent-quality answers
2. **Latency**: p50 ≤ current pipeline; p95 within 20% of current
3. **Streaming UX**: Agent thinking steps, tool calls, and answer chunks render identically in `AgentThinkingSteps` component
4. **Conversation persistence**: Users can see conversation history and resume past chats
5. **Eval scores**: Faithfulness, answer relevance, context precision scores ≥ current baseline (measured via existing `RAGEvaluation` infrastructure). **Gated at Phase 1.5.**
6. **Code reduction**: ≥30% fewer lines in the RAG/chat backend code (revised from 40% — two-agent approach retains more structure than a single-agent would)
7. **No prerequisite regressions**: All blocking issues from Prerequisites (P.1–P.5) are resolved and covered by tests before Phase 0 begins

---

## Execution Order

```
Prerequisites (fix blockers)
      │
      ▼
Phase 0 (DB + history helpers)
      │
      ▼
Phase 1 (two-agent pipeline + QueryContext split)
      │
      ▼
Phase 1.5 (eval baseline — GATE: scores ≥ baseline)
      │
      ▼
Phase 2 (API + frontend, feature flag rollout)
      │
      ▼
Phase 3 (cleanup & deprecation)
```

Each phase can be tested independently. Phase 1.5 is a hard gate — do not proceed to Phase 2 if eval scores regress.

Sub-agents and advanced features (conversation sidebar, title generation, token pruning) are deferred to a future cycle — see "Future Consideration" section above.
