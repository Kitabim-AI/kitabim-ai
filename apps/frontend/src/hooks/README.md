# Frontend Hooks

## Overview
Provides reusable React hooks encapsulating authentication, book lifecycle operations, interactive conversational AI, reader DOM manipulation, search debounce, Uyghur transliteration, and spell checking.

## Interface
- `[useAuth.tsx:AuthProvider]`: Context provider handling session recovery, token refresh, and OAuth redirect parameters.
- `[useAuth.tsx:useAuth]`: Hook accessing authentication status, login methods, and user profile data.
- `[useAuth.tsx:useHasRole]`: Hook evaluating whether the current user matches any specified role (`'admin'`, `'editor'`, `'reader'`).
- `[useAuth.tsx:useIsAdmin]`: Hook returning boolean flag indicating admin privileges.
- `[useAuth.tsx:useIsEditor]`: Hook returning boolean flag indicating editor or admin privileges.
- `[useAuth.tsx:useCanRead]`: Hook returning boolean flag indicating book reading permission.
- `[useBookActions.ts:useBookActions]`: Hook providing operational handlers for book upload, editing, deletion, reprocessing, and reader navigation.
- `[useBookmarks.ts:useBookmarks]`: Hook providing bookmark querying and toggling operations for books.
- `[useBooks.ts:useBooks]`: Hook managing paginated book lists, category filtering, shelf loading, and sorting state.
- `[useChat.ts:useChat]`: Hook managing book and global conversational sessions, message streaming, and assistant personas.
- `[useChat.ts:AgentStep]`: Interface representing granular agent execution steps during chat responses.
- `[useContentSearch.ts:useContentSearch]`: Hook providing debounced in-book text search queries.
- `[useLlmSpellCheckPreview.ts:useLlmSpellCheckPreview]`: Hook fetching and managing LLM-assisted spell checking candidate previews.
- `[useLlmSpellCheckPreview.ts:LlmSpellCheckPreview]`: Interface describing candidate LLM spell check replacements.
- `[useLookupSearch.ts:useLookupSearch]`: Generic debounced search hook for dictionaries and lexical entities.
- `[usePendingCorrections.ts:usePendingCorrections]`: Hook managing batch review, approval, and rejection of candidate spelling corrections.
- `[usePendingCorrections.ts:PendingCorrection]`: Interface representing a queued spelling correction candidate.
- `[usePendingCorrections.ts:ConfirmResult]`: Interface summarizing batch correction execution results.
- `[useQuoteHighlight.ts:useQuoteHighlight]`: Hook scanning reader DOM elements to highlight cited quotes.
- `[useScrollStabilizer.ts:useScrollStabilizer]`: Hook preserving reader scroll offsets across layout reflows and font adjustments.
- `[useScrollToPage.ts:useScrollToPage]`: Hook scrolling reader viewports to target page elements.
- `[useSpellCheck.ts:useSpellCheck]`: Hook executing page-level spell checking and word replacement operations.
- `[useSpellCheck.ts:SpellSuggestion]`: Interface representing dictionary correction suggestions.
- `[useSpellCheck.ts:SpellIssue]`: Interface representing detected spelling issues and candidates.
- `[useSpellingCheck.ts:useSpellingCheck]`: Hook for real-time single-word dictionary spell checking.
- `[useTextSelectionShare.ts:useTextSelectionShare]`: Hook computing coordinates and text for floating social share tooltips on text selection.
- `[useTextSelectionShare.ts:TextSelectionShare]`: Interface containing selected text content and bounding box coordinates.
- `[useUyghurInput.ts:useUyghurInput]`: Hook managing phonetic Uyghur keyboard transliteration and RTL input behavior on HTML inputs.

## Invariants
- `[useAuth.tsx:useAuth]`: Must be invoked inside `<AuthProvider>`, throwing an error if context is uninitialized.
- `[useBookActions.ts:useBookActions]`: Destructive actions (book deletion, reprocess) enforce modal confirmation before dispatching API requests.
- `[useScrollStabilizer.ts:useScrollStabilizer]`: Scroll stabilization is bypassed while explicit page navigation is running via `suppressedRef`.
- `[useUyghurInput.ts:useUyghurInput]`: Ignores keydown events with Ctrl, Meta, or Alt modifiers to prevent hijacking native shortcuts.

## Side Effects
- `[useAuth.tsx:AuthProvider]`: Reads query parameters from `window.location.search`; accesses and removes `sessionStorage` key `'kitabim_access_token_session'`; updates URL history via `window.history.replaceState`.
- `[useChat.ts:useChat]`: Issues HTTP requests and EventSource/ReadableStream calls to backend chat endpoints (`/api/chat/`).
- `[useQuoteHighlight.ts:useQuoteHighlight]`: Mutates DOM element styles and classes directly on reader page containers.
- `[useScrollStabilizer.ts:useScrollStabilizer]`, `[useScrollToPage.ts:useScrollToPage]`: Mutates `scrollTop` properties and invokes `scrollIntoView()` on DOM elements.
- `[useTextSelectionShare.ts:useTextSelectionShare]`: Registers global event listeners on `window` and `document` for selection and mouse/touch interactions.

## Verification
- Run: `npm test`
