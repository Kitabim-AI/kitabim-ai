# Frontend Services

## Overview
Provides API client services communicating with backend REST endpoints, handling authenticated HTTP communications, token refresh cycles, client-side PDF rendering, streaming AI chat completions, full-text search, and admin user management.

## Interface
- `[authService.ts:initAppConfig]`: Asynchronously retrieves runtime application settings (`collectionPageSize`, `showChatCost`, `maxUploadMb`) from `/api/config`.
- `[authService.ts:getCollectionPageSize]`: Returns configured book collection page size.
- `[authService.ts:getShowChatCost]`: Returns boolean flag determining whether chat cost is displayed.
- `[authService.ts:getMaxUploadMb]`: Returns maximum file upload limit in megabytes.
- `[authService.ts:User]`: Interface representing authenticated user attributes (`id`, `email`, `displayName`, `avatarUrl`, `role`).
- `[authService.ts:AuthTokens]`: Interface representing token responses.
- `[authService.ts:AUTH_ERROR_CODES]` / `[authService.ts:AuthErrorCode]` / `[authService.ts:isAuthErrorCode]`: Closed 6-value OAuth callback error code allowlist and type guard.
- `[authService.ts:OAuthCallbackError]`: Error subclass carrying a validated `AuthErrorCode` from `BroadcastChannel` or `postMessage` OAuth error events.
- `[authService.ts:consumeRedirectAuthError]` / `[authService.ts:clearConsumedRedirectAuthError]`: Consumes, validates, caches (across React `<StrictMode>` double-mounts), and strips `?auth_error=` from Mobile Safari OAuth error redirects.
- `[authService.ts:getAccessToken]`: Returns active in-memory JWT access token.
- `[authService.ts:setAccessToken]`: Updates active in-memory JWT access token.
- `[authService.ts:clearAccessToken]`: Resets active in-memory JWT access token to `null`.
- `[authService.ts:recoverSessionToken]`: Reads and immediately removes one-time token from `sessionStorage` fallback.
- `[authService.ts:getAuthHeaders]`: Returns headers object containing `Authorization`, `X-Kitabim-App-Id`, and `Accept-Language`.
- `[authService.ts:authFetch]`: Fetch wrapper injecting auth headers and attempting automatic token refresh on 401 errors.
- `[authService.ts:AuthService]`: Service providing user profile retrieval, OAuth popup flows, and logout operations.
- `[authService.ts:refreshAccessToken]`: Dispatches refresh request to `/api/auth/refresh` using httpOnly cookie credentials.
- `[contactService.ts:ContactSubmission]`: Interface describing user contact form data.
- `[contactService.ts:ContactSubmissionResponse]`: Interface describing contact submission receipt.
- `[contactService.ts:submitContactForm]`: Submits contact messages to `/api/contact/submit`.
- `[geminiService.ts:extractUyghurText]`: Dispatches image data to `/api/ai/ocr/` with exponential retry on 429/503.
- `[geminiService.ts:chatWithBook]`: Submits conversational query against a book to `/api/chat/`.
- `[geminiService.ts:chatWithBookStream]`: Submits conversational streaming query with chunk and agent-step callbacks.
- `[geminiService.ts:ChatStreamParams]`: Interface defining streaming chat query options.
- `[geminiService.ts:ChatStreamCallbacks]`: Interface defining callbacks for chunks, thinking state, agent steps, and errors.
- `[geminiService.ts:getChatUsage]`: Retrieves current user chat token usage and limits.
- `[geminiService.ts:submitChatFeedback]`: Records user satisfaction feedback on chat responses.
- `[geminiService.ts:getUserConversations]`: Retrieves saved chat conversation threads.
- `[geminiService.ts:getConversationMessages]`: Retrieves messages for a specific conversation thread.
- `[geminiService.ts:createConversation]`: Creates a new conversation thread record.
- `[geminiService.ts:deleteConversation]`: Deletes an existing conversation thread record.
- `[pdfService.ts:getPageCount]`: Calculates total page count of a PDF file using client-side PDF.js.
- `[pdfService.ts:generateFileHash]`: Calculates SHA-256 hexadecimal checksum of a File buffer via `crypto.subtle`.
- `[pdfService.ts:convertPageToBase64Image]`: Renders a PDF page to canvas and outputs a base64 JPEG string.
- `[persistenceService.ts:PersistenceService]`: REST client handling books, page images, bookmarks, reading progress, and administrative triggers.
- `[searchTabsService.ts:SearchTabsService]`: REST client querying dictionaries, historical terms, proverbs, synonyms, and Quran ayahs.
- `[searchTabsService.ts:DictionaryEntry]`: Interface describing dictionary search results.
- `[searchTabsService.ts:NameEntry]`: Interface describing Uyghur name search results.
- `[searchTabsService.ts:HistoryTermEntry]`: Interface describing historical term definitions.
- `[searchTabsService.ts:ProverbEntry]`: Interface describing proverb records.
- `[searchTabsService.ts:EnglishUyghurEntry]`: Interface describing English-Uyghur glossary entries.
- `[searchTabsService.ts:SynonymEntry]`: Interface describing synonym dictionary entries.
- `[searchTabsService.ts:QuranAyah]`: Interface describing Quran ayah translation records.
- `[searchTabsService.ts:SpellingSuggestion]`: Interface describing spell check replacement suggestions.
- `[searchTabsService.ts:SpellingCheckResult]`: Interface describing word spell check query results.
- `[searchTabsService.ts:ContentSearchHit]`: Interface describing full-text in-book search hits.
- `[searchTabsService.ts:PaginatedContentHits]`: Interface describing paginated content search hit lists.
- `[userService.ts:UserPublic]`: Interface describing public user account data.
- `[userService.ts:PaginatedUsers]`: Interface describing paginated user administration listings.
- `[userService.ts:UserService]`: Admin service for listing users and modifying account roles or status flags.

## Invariants
- `[authService.ts:getAccessToken]`: Access token is held in memory only and is never stored in `localStorage`.
- `[authService.ts:authFetch]`: Retries at most one time upon receiving a 401 status; if renewal fails, it unsets in-memory authentication.
- `[geminiService.ts:extractUyghurText]`: Automatically retries with exponential backoff on HTTP 429 or 503, throwing immediately on other non-200 statuses.
- `[pdfService.ts:getPageCount]`: Singletons script loading promise so concurrent page rendering calls share one PDF.js load.

## Side Effects
- `[authService.ts:recoverSessionToken]`: Mutates `sessionStorage` by deleting `'kitabim_access_token_session'`.
- `[authService.ts:consumeRedirectAuthError]`: Strips `?auth_error=` from the browser URL bar via `window.history.replaceState` and caches the validated `AuthErrorCode` in module state.
- `[pdfService.ts:loadPdfJs]`: Appends `<script>` tags to `document.head` to fetch PDF.js from external CDN.
- `[pdfService.ts:convertPageToBase64Image]`: Instantiates off-screen `<canvas>` elements and invokes 2D rendering contexts.
- All service modules: Dispatch HTTP network requests across `/api/*` endpoints.

## Verification
- Run: `npm test`
