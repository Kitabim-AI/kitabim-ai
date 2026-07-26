# API Code Review — 2026-07-25

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Request changes

## Issues

### `services/backend/api/endpoints/chat_router.py`

- **[blocking]** Line 140 — `config_repo.get_config("use_adk_chat_v2")` calls a method that does not exist on `SystemConfigsRepository` (it only defines `get_value`/`set_value`). This line runs unconditionally at the top of `event_generator()` for **every** `/chat/stream` request — the resulting `AttributeError` is caught by the broad `except Exception` at line 224 and surfaced to the user as a generic "system busy" error. As written, this change breaks chat entirely, not just the new v2 path. Fix: `config_rec = await config_repo.get_value("use_adk_chat_v2")` and compare `config_rec == "true"` (it returns the string value directly, not a record with `.value`).
- **[blocking]** Line 158 — `context_book_ids=req.context_book_ids` is passed straight through into `ChatRequestDTO`, and `is_global=req.is_global` is passed without normalizing the frontend's existing `bookId === "global"` sentinel. The legacy path (`rag_service.py:92`) does `is_global = req.book_id == "global"`; the frontend (`useChat.ts`/`geminiService.ts`) still only ever sends `bookId: "global"` and never sends `isGlobal`. Since `ChatRequest.is_global` defaults to `False`, every global-chat request entering the v2 path gets `is_global=False` and `book_id="global"`, which `ChatOrchestrator.stream_response` then treats as a literal book ID (no book with id `"global"` exists). Global chat is broken under the v2 orchestrator. Fix: normalize the same way the legacy path does, e.g. `is_global=req.is_global or req.book_id == "global"`.
- **[suggestion]** Lines 137, 219, 233, 251 — `ConversationRepository`/`SystemConfigsRepository`/DTO/orchestrator imports are repeated as local imports inside three separate endpoint functions. Hoist to module-level imports for consistency with the rest of the file and to avoid the (unlikely but real) per-request import overhead.

### `packages/backend-core/app/services/chat/orchestrator.py`

- **[blocking]** Lines 77–86 — `QueryContext(...)` is constructed with only 8 of the dataclass's required fields. `QueryContext` (`app/services/rag/context.py`) has **no defaults** for `history`, `book`, `persona_prompt`, `character_categories`, `rag_chain`, `rewrite_chain`, `embeddings`, `start_ts`, and `agent_model`. This raises `TypeError: QueryContext.__init__() missing 9 required positional arguments` on every call, immediately after entering `stream_response()`. Verified directly:
  ```
  TypeError: QueryContext.__init__() missing 9 required positional arguments: 'history', 'book',
  'persona_prompt', 'character_categories', 'rag_chain', 'rewrite_chain', 'embeddings', 'start_ts',
  and 'agent_model'
  ```
  Even once the `get_config` bug above is fixed, the v2 path cannot run a single request without crashing. Needs either a `QueryContext` constructor that supplies sane defaults for the orchestrator's stripped-down use case, or the missing fields need to be supplied here (e.g. `history=[]`, `book=None`, `persona_prompt=None`, `character_categories=[]`, `rag_chain=None`, `rewrite_chain=None`, `embeddings=None`, `start_ts=start_time`, `agent_model=model_name`).
- **[blocking]** Line 74 — `history_msgs[:-1] if history_msgs else []` drops the single most-recent message before formatting it for `DeterministicRAGHandler._llm_analyze_query`. `get_recent_messages` is called *before* the current turn is saved, so `history_msgs` already contains only prior turns — the last element is the most recent (and most relevant) prior message, e.g. the model's last answer that a follow-up question like "tell me more about that" would need. Slicing it off discards exactly the context needed for pronoun/follow-up resolution. Likely should be `format_history_for_analysis(history_msgs)`.
- **[blocking]** Related to the `QueryContext` gap above: `_llm_analyze_query` (in `deterministic_handler.py:144`) decides whether history exists via `has_history = len(ctx.history) > 0`, not via `ctx.chat_history_str`. `ChatRequestDTO` has no `history` field at all, and the orchestrator never populates `QueryContext.history`. Even after fixing the crash by passing `history=[]`, intent/signal analysis will always behave as if this is a brand-new conversation, ignoring the `chat_history_str` that was carefully assembled two lines above. Either populate `ctx.history` with the actual prior turns, or change the check to look at `chat_history_str`.

### `packages/backend-core/app/db/repositories/conversation_repository.py`

- **[suggestion]** Line 35 — `title=title or "Yangi suhbat"` hardcodes a user-visible Uyghur string in Python source instead of going through `t("...")` from `app.core.i18n`, per the project's non-negotiable i18n rule. Low impact today (title isn't yet surfaced anywhere in the reviewed frontend diff), but will need to move to the locale files before any UI displays conversation titles.

### `packages/backend-core/migrations/072_add_conversations.sql`

- **[suggestion]** Line 3/13 — `id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()` sets a DB-side default while the ORM models (`Conversation.id`, `ConversationMessage.id`) also set a Python-side `default=lambda: str(uuid.uuid4())`. Not incorrect (the extension is enabled in `001_initial_baseline.sql`), just redundant — every other `String(36)` PK table in this codebase relies solely on the app-side default. Consider dropping the DB default for consistency.

### Testing

- **[suggestion]** `packages/backend-core/tests/app/services/test_adk_orchestrator.py` — the three tests only check DTO immutability, agent-builder return values, and that `ChatOrchestrator.__init__` stores `session_service`. Nothing exercises `stream_response()`, which is where all three blocking bugs above live. A single test that calls `stream_response()` with a mocked `ConversationRepository`/session/runner would have caught the `QueryContext` crash immediately.
- **[suggestion]** `packages/backend-core/tests/app/db/conversation_repository_test.py` — the single test only asserts `hasattr(ConversationRepository, "create_conversation")` etc. It never instantiates the repo or calls a method against a session, so it verifies nothing about actual behavior (e.g. that `save_turn` writes two rows in the right order, that `delete_conversation` respects `user_id` ownership).

## Summary

The three blocking issues compound: the `SystemConfigsRepository.get_config` typo breaks the endpoint for every request regardless of the feature flag, and even with that fixed, `QueryContext` construction crashes immediately and global-chat scope is silently mis-detected. None of this is caught by the new tests, which check structure/existence rather than behavior. Recommend fixing the three blocking items and adding at least one behavioral test for `stream_response()` before merging.
