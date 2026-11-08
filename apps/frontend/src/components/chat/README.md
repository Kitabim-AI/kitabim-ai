# Chat Component (`chat`)

## Overview
Provides the conversational AI chat interface for book-specific and global multi-book RAG research, supporting streaming responses, agent reasoning step inspection, source citation verification via modals, conversation session history, and response feedback.

## Interface
- `[AgentThinkingSteps.tsx:AgentThinkingSteps]` — Memoized component rendering granular agent execution steps (planning, thinking, tool calls, decomposition, knowledge graph queries) with step status icons and admin-accessible query badges.
- `[ChatInterface.tsx:ChatInterface]` — Primary conversational AI interface supporting single-book or library-wide global RAG modes, streaming responses, character selection, conversation histories, citation links, feedback submissions, and quota displays.
- `[ReferenceModal.tsx:ReferenceModal]` — Portal-rendered modal displaying book citations, page texts, summaries, Quran ayah views, or embedded interactive knowledge graphs (`GraphView`).

## Invariants
- `[ChatInterface.tsx:usageStatus]` — Disables message sending when `usageStatus?.hasReachedLimit` is true, displaying usage quota limit notices.
- `[ReferenceModal.tsx:isGraphMode]` — Sets graph mode when `isGraph` is true or `bookId === 'graph' | 'knowledge_graph'`.
- `[ReferenceModal.tsx:useEffect]` — Locks `document.body.style.overflow = 'hidden'` when the reference modal is open and restores normal overflow on unmount/close.

## Side Effects
- `[ChatInterface.tsx:onSendMessage]` — Dispatches message generation callbacks to stream AI completions from backend endpoints.
- `[ChatInterface.tsx:submitFeedback]` — Submits positive or negative user feedback ratings on generated responses.
- `[ReferenceModal.tsx:PersistenceService.getBookById]`, `PersistenceService.getPageByNumber]`, `PersistenceService.getBookSummary]` — Fetches persisted book metadata, page texts, and summaries for citation display.

## Verification
- Run: `npm test`
