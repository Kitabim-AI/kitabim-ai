# Share Component (`share`)

## Overview
Provides portal-rendered sharing modals and social icon primitives for exporting books, search excerpts, and conversational AI answers to the clipboard, Facebook Sharer, or X (formerly Twitter).

## Interface
- `[ShareIcons.tsx:FacebookIcon]` — SVG icon component for Facebook share action.
- `[ShareIcons.tsx:XIcon]` — SVG icon component for X / Twitter share action.
- `[ShareModal.tsx:ShareModal]` — Modal dialog for sharing book details and deep links to social platforms and clipboard.
- `[ShareChatModal.tsx:ShareChatModal]` — Modal dialog for sharing Q&A question/answer pairs with citation attribution.
- `[ShareSearchResultModal.tsx:ShareSearchResultModal]` — Modal dialog for sharing search passage snippets with volume and page citations.

## Invariants
- `[ShareModal.tsx:createPortal]`, `[ShareChatModal.tsx:createPortal]`, `[ShareSearchResultModal.tsx:createPortal]` — Renders into `document.body` via `createPortal`.
- `[ShareModal.tsx:buildSafeTweetText]` — Enforces character length constraints and hashtag formatting for Twitter intent URLs.

## Side Effects
- `[ShareModal.tsx:handleCopy]` — Writes formatted text or URL to `navigator.clipboard.writeText`.
- `[ShareModal.tsx:handleFacebook]` / `handleTwitter` — Opens external popup windows via `window.open` targeting Facebook and X sharing web endpoints.

## Verification
- Run: `npm test`
