# UI Code Review — 2026-07-25

**Branch:** feature/adk-2-upgrade-v2
**Verdict:** Approve with suggestions

## Issues

### `packages/shared/src/types.ts`

- **[suggestion]** Lines 76–84 — The new `ChatRequest` interface uses snake_case field names (`book_id`, `is_global`, `character_id`, `conversation_id`), but the actual request body built in `geminiService.ts` (`chatWithBookStream`) sends camelCase (`bookId`, `characterId`, `conversationId`). Nothing in the frontend currently imports or uses `ChatRequest`, `Conversation`, or `ConversationMessage` — grep across `apps/frontend/src` finds zero references. If these are meant to describe the wire format for future UI work, `ChatRequest` should match the camelCase convention the rest of `types.ts` and the actual fetch call use, otherwise it will mislead whoever wires it up next.

### `apps/frontend/src/hooks/useChat.ts`

- **[suggestion]** Line 34 — `conversationId` is `useState` but never reset in `abortOngoingChat()` or `clearChat()`. When a user switches books/views, the `view !== 'reader'` branch at line 132 calls `clearChat()` (clearing messages) but leaves `conversationId` pointing at the old conversation; the next message sent from a *different* book context will still be appended to the previous conversation (server-side `conversation_id` is honored as-is by the orchestrator, which reuses `conversation.book_id` from the original creation). Consider clearing `conversationId` alongside `clearChat()`.
- **[suggestion]** No test coverage was added for the new `conversationId` state or its round-trip through `chatWithBookStream`/`onConversationId`. Given `useChat.ts` already has non-trivial async logic, a test asserting that a returned `conversationId` is passed back on the next call would guard against regressions here.

### `apps/frontend/src/services/geminiService.ts`

- **[suggestion]** `chatWithBookStream` now takes 16 positional parameters (two new ones — `conversationId`, `onConversationId` — added at the end). This was already a large positional-parameter list before this change; adding to it makes call-site correctness (as seen in `useChat.ts:197-257`, where every argument is a bare value or inline callback matched only by position and a comment) increasingly easy to get wrong silently. Not blocking for this change, but worth flagging before the next addition — an options-object parameter would be safer going forward.

## Summary

The frontend changes themselves are small and consistent with existing patterns (SSE event handling, ref-based accumulation). The main gaps are unused/mismatched new shared types and no test coverage for the new conversation-id plumbing; neither is blocking, but the mismatched `ChatRequest` casing is worth fixing before it's picked up by future code.
