# Design Document: Reader Page & Quote Sharing

## Overview
Add social-media sharing (X/Twitter, Facebook, copy) to the reader view at two granularities: an entire page, and a user-highlighted quote within a page — extending the existing Q&A-share and book-share patterns (`ShareChatModal.tsx`, `ShareModal.tsx`) into the reader itself. Opening a shared link auto-scrolls the reader to the shared page and, for quote shares, highlights the shared text.

## Problem & Motivation
The reader today only supports sharing the whole book (`ReaderView.tsx:520-528`, opens `ShareModal`). There's no way to share a specific page or a specific passage. The i18n locale files already carry an unused `share.shareQuote` key ("Share Quote" / "ئىقتىباسنى ھەمبەھىرلەش") with no component using it — this feature was already anticipated but never built.

Separately, three near-identical share modals already exist (`ShareModal.tsx`, `ShareChatModal.tsx`, `ShareSearchResultModal.tsx`), each with its own copy-pasted `XIcon`/`FacebookIcon`, button styling, and tweet-text-building logic. `ShareChatModal.tsx`'s tweet-truncation safety check was recently fixed (it was double-`encodeURIComponent`-ing the URL when measuring length, causing severe over-truncation); `ShareModal.tsx` and `ShareSearchResultModal.tsx` still lack any byte-safe truncation (`ShareSearchResultModal.tsx:59` does a naive `content.slice(0, 160)`). Adding a fourth near-duplicate modal would make this worse, so this feature also extracts the shared logic and generalizes `ShareSearchResultModal` (its `title`/`subtitle`/`content`/`sourceLabel`/`url` shape already matches what a page or quote share needs) rather than writing new modals from scratch.

## Scope
- Share a whole page's text, or a user-selected quote from a page, via X, Facebook, or copy.
- Shared links deep-link to the exact page and auto-scroll to it.
- Shared quote links additionally highlight the matched text once the page renders.
- **Out of scope:** fuzzy/normalized text matching for highlighting (exact substring match only — if the page text has since been edited and no longer contains the quote verbatim, the link still opens and scrolls to the page, just without a highlight); persisting or analytics-tracking shares; sharing to platforms beyond X/Facebook (matches existing patterns).

## Access Control
Page/quote sharing is **public** — no login required to see the buttons, use them, or open a shared link — matching how the reader and the existing book-level share button already work today: `ReaderView.tsx:520-528`'s `ShareModal` button has no auth check (only `selectedBook.status === 'ready'`), `App.tsx:118` renders `ReaderView` unconditionally, and every book-read backend endpoint (`get_book`, `get_book_page`, etc. in `books_router.py`) uses `Depends(get_current_user_optional)`, which returns `None` for guests instead of rejecting them. This feature follows the same pattern: the new page/quote share buttons in `PageItem.tsx` (§4) get no auth check, and the new `/api/share/page/{book_id}/{page_number}` endpoint (§6) gets no auth dependency — same as `share_book`/`share_qa`. The existing `status == "ready"` / `visibility != "private"` gate (already in `share_book`, reused in §6) is the only access restriction, and it applies equally to guests and logged-in users.

Chat sharing (`ShareChatModal`, already shipped) needs no change here — it's already registered-user-only end-to-end, not by an explicit check on the Share button itself, but structurally: the chat input is hidden behind `isAuthenticated` (`ChatInterface.tsx:433/891`), so an anonymous user can never produce an answer to share, and the backend chat endpoints (`chat_router.py`) require `Depends(require_reader)`, which 401s guests. This is called out explicitly so the distinction is a documented decision rather than an accident of two features built at different times.

## Proposed Changes

### 1. `apps/frontend/src/utils/shareText.ts` (new)
Extract from `ShareChatModal.tsx`:
- `cleanShareText(text: string): string` — strips `[text](ref:...)`, `(ref:...)`, and `BookID:` fragments (current regexes, unchanged).
- `buildSafeTweetText(lines: string[], maxContentLineIndex: number, maxUrlLength = 10000): string` — generalized version of `ShareChatModal.tsx`'s `buildSafeTweetText`. Takes the full array of joinable lines (question/answer/source/footer, or title/content/source/footer) and the index of the one line allowed to shrink (the long free-text one), joins with `\n\n`, and does the binary-search truncation against the **real** `fullUrl.length` (not a second `encodeURIComponent` pass — this was the bug just fixed in `ShareChatModal.tsx`). Returns the full untruncated join when it already fits.

`ShareModal.tsx` and `ShareChatModal.tsx` are updated to import `cleanShareText`/`buildSafeTweetText` from here instead of keeping local copies. `ShareModal.tsx`'s tweet text (currently unbounded — just book title/author/link, always short) is left functionally identical, just routed through the shared builder for consistency.

### 2. `apps/frontend/src/components/share/ShareIcons.tsx` (new)
Extract the copy-pasted `XIcon`/`FacebookIcon` SVG components (currently duplicated verbatim in all three modals) into one file; all three existing modals plus the generalized modal import from here.

### 3. `apps/frontend/src/components/share/ShareSearchResultModal.tsx` (generalized)
Add optional props: `bookId?: string`, `pageNumber?: number`, `quote?: string`, `variant?: 'searchResult' | 'page' | 'quote'` (default `'searchResult'`, preserves the 3 existing callers' behavior unchanged).

When `bookId` and `pageNumber` are both present:
- `shareTargetUrl` becomes `${origin}/books/${bookId}/${pageNumber}${quote ? '?quote=' + encodeURIComponent(quote) : ''}` instead of falling back to the `url` prop.
- The Facebook button's crawler-preview URL becomes `${origin}/api/share/page/${bookId}/${pageNumber}${quote ? '?quote=' + encodeURIComponent(quote) : ''}` (new backend endpoint, §6) instead of `shareTargetUrl` directly — mirrors how `ShareModal.tsx` uses a separate `/api/share/book/{id}` URL for the OG-tagged crawler response vs. the plain deep link for copy/X.
- The X tweet text uses `buildSafeTweetText` (from §1) instead of the current hardcoded `content.slice(0, 160)`.
- Header label: `t('share.sharePage')` (new key) for `variant='page'`, `t('share.shareQuote')` (existing, finally-used key) for `variant='quote'`, unchanged `t('share.shareSearchResult')` otherwise.

The 3 existing callers (`QuranResultsList.tsx`, `LookupResultsList.tsx`, `ContentResultsList.tsx`) pass no `bookId`/`pageNumber`/`variant` and are unaffected.

### 4. `apps/frontend/src/components/reader/PageItem.tsx`
Add optional props: `bookId?: string`, `bookTitle?: string`, `bookAuthor?: string`, `highlightQuote?: string`, `onHighlightApplied?: () => void`.

**Whole-page share button:** new icon button in the header row (next to the page-number badge, `PageItem.tsx:123-130`), hover-revealed the same way the editor toolbar is (`isActive ? 'opacity-100' : 'opacity-0'} sm:group-hover:opacity-100`, but *not* gated on `isEditor` — this is a reader-facing action available to everyone). Clicking it sets local state `const [shareState, setShareState] = useState<{ content: string; quote?: string } | null>(null)` to `{ content: cleanShareText(page.text || '') }` and renders:

```tsx
{shareState && (
  <ShareSearchResultModal
    title={bookTitle || ''}
    subtitle={bookAuthor}
    content={shareState.content}
    sourceLabel={t('chat.pageNumber', { page: page.displayPageNumber || page.display_page_number || page.pageNumber })}
    bookId={bookId}
    pageNumber={page.pageNumber}
    quote={shareState.quote}
    variant={shareState.quote ? 'quote' : 'page'}
    onClose={() => setShareState(null)}
  />
)}
```

**Quote selection popover:** a new `useTextSelectionShare(containerRef)` hook (new file `apps/frontend/src/hooks/useTextSelectionShare.ts`), attached to a `contentRef` wrapping the non-editing `<MarkdownContent>` block (`PageItem.tsx:167-174`). Listens for `selectionchange` scoped to check `window.getSelection()` is non-collapsed and fully contained within `contentRef.current`; when true, returns `{ text: string, rect: DOMRect } | null` (rect from `range.getBoundingClientRect()`). `PageItem` renders a small fixed-position share-icon button at that rect when non-null (portal to `document.body`, same z-index tier as the modals), which on click calls `setShareState({ content: selection.text, quote: selection.text })` and clears the browser selection.

**Quote highlight-on-arrival:** new hook `useQuoteHighlight(contentRef, highlightQuote, onApplied)` (new file `apps/frontend/src/hooks/useQuoteHighlight.ts`), run in a `useEffect` keyed on `[highlightQuote, page.text]`. See §5 for the matching/wrapping algorithm. When `highlightQuote` is set and a match is found, it wraps the match in a `<mark className="bg-[#0369a1]/20 dark:bg-[#38bdf8]/30 rounded px-0.5">`, calls `scrollIntoView({ block: 'center', behavior: 'smooth' })` on it, then calls `onHighlightApplied?.()`. If no match is found, it calls `onHighlightApplied?.()` immediately with no visual change (silent fallback, per Scope).

### 5. `useQuoteHighlight` matching algorithm
Exact-substring match only (no whitespace/markdown normalization — the quote came from `window.getSelection().toString()` on this exact rendered DOM, so a byte-for-byte match against a freshly rendered identical page succeeds; scope explicitly excludes fuzzy matching for edited pages):

1. `TreeWalker` over `contentRef.current` with `NodeFilter.SHOW_TEXT`, collecting each text node plus its starting offset within a concatenated `fullText` string (raw concatenation, no normalization).
2. `const matchIndex = fullText.indexOf(highlightQuote)`. If `-1`, return `null`.
3. Map `[matchIndex, matchIndex + highlightQuote.length)` back to `(startNode, startOffset)` / `(endNode, endOffset)` by scanning the collected node-offset list.
4. If `startNode === endNode`: build a `Range` over just that node and `range.surroundContents(mark)` directly.
5. Otherwise (quote spans multiple text nodes, e.g. crossing a `<strong>`/paragraph boundary from markdown rendering): can't use `surroundContents` (throws when a range partially selects non-text-node boundaries). Instead:
   - `startNode.splitText(startOffset)` — the returned second half is the first fragment to wrap.
   - `endNode.splitText(endOffset)` — the *original* `endNode` (now truncated to `[0, endOffset)`) is the last fragment to wrap.
   - Any text nodes strictly between `startNode` and `endNode` in walker order are wrapped whole.
   - Wrap each fragment by inserting a `<mark>` before it in its parent and moving the text node inside: `node.parentNode.insertBefore(mark, node); mark.appendChild(node)`.
6. Return the first `<mark>` element (for `scrollIntoView`).

This is the fiddliest piece of the feature — it gets a dedicated unit test suite (§8) exercising single-node, multi-node, and no-match cases against real DOM fixtures (jsdom).

### 6. `services/backend/api/endpoints/share_router.py` — new `GET /page/{book_id}/{page_number}`
Modeled directly on the existing `share_qa` handler (lines 102-179):

```python
@router.get("/page/{book_id}/{page_number}")
async def share_page(
    book_id: str,
    page_number: int,
    request: Request,
    quote: str | None = Query(None, max_length=500),
    session: AsyncSession = Depends(get_session),
):
```

- Public, no auth dependency (matches `share_book`/`share_qa`).
- Same `_SCRAPER_AGENTS` gate; non-scrapers get a 302 to `{frontend_base_url}/books/{book_id}/{page_number}{'?quote='+quote if quote else ''}`.
- `BooksRepository.get(book_id)` — redirect (not error) if missing, `status != "ready"`, or `visibility == "private"` (same gate as `share_book`).
- `PagesRepository.find_one(book_id, page_number)` — redirect if the page doesn't exist. No new repository method needed; `find_one` already exists (`pages_repository.py:189-194`).
- `og:description`: if `quote` provided, HTML-escape + whitespace-collapse it (same as `share_qa`'s `q`/`a` handling) and use directly. Otherwise, derive from `page.text`: strip the same markdown/ref patterns `cleanShareText` strips client-side (small Python port of those 3 regexes), then truncate using the exact snippet pattern already used in `pages_repository.py`'s `search_content_pages` (cut to length, back off to last space, append `"..."`).
- `og:title`: `"{book.title} — {page_number}-بەت"` (HTML-escaped book title).
- `og:image`: same cover URL pattern as `share_book` (`{base_url}/api/covers/{book_id}.jpg`).
- Same `twitter:card`/`summary_large_image` block as the other two handlers.

### 7. `apps/frontend/src/context/AppContext.tsx`
- `parsePath` (lines 64-92): extend the `books` branch to also read `parts[2]` as a page number and `window.location.search` for `quote`:
  ```ts
  else if (viewPortion === 'books' && parts[1]) {
    view = 'library';
    bookId = parts[1];
    if (parts[2] && /^\d+$/.test(parts[2])) pageNumber = parseInt(parts[2], 10);
    const params = new URLSearchParams(window.location.search);
    quote = params.get('quote') || undefined;
  }
  ```
  Return type gains `pageNumber?: number` and `quote?: string`.
- New state: `const [pendingQuoteHighlight, setPendingQuoteHighlight] = useState<string | null>(null)`, exposed on the context (`pendingQuoteHighlight`, `setPendingQuoteHighlight`).
- The existing deep-link effect (lines 173-183) additionally calls `setCurrentPage(initialRoute.pageNumber ?? null)` and `setPendingQuoteHighlight(initialRoute.quote ?? null)` alongside the existing `setSelectedBook`/`setViewInternal('reader')`. This doesn't conflict with `useBookActions.ts:243`'s `setCurrentPage(initialPage)` — that only runs from the in-app "open book" action, not this URL-driven path.

### 8. `apps/frontend/src/components/reader/ReaderView.tsx` and `VirtualScrollReader.tsx`
Thread the new static props to every `PageItem` render site (both the non-virtual list at `ReaderView.tsx:645-673` and `VirtualScrollReader.tsx:303+`, mirroring exactly how `onSetStartPage`/`onToggleToc` are already threaded through both):
- `bookId={selectedBook.id}`, `bookTitle={selectedBook.title}`, `bookAuthor={selectedBook.author}` — passed to every `PageItem` unconditionally.
- `highlightQuote={currentPage === page.pageNumber ? (pendingQuoteHighlight ?? undefined) : undefined}` and `onHighlightApplied={() => setPendingQuoteHighlight(null)}` — only the page matching `currentPage` receives a non-undefined `highlightQuote`, so the highlight effect only fires once, on the correct page, and clears itself from context afterward.

### 9. i18n — `apps/frontend/src/locales/en.json` and `ug.json`
Add `share.sharePage` ("Share Page" / matching Uyghur). `share.shareQuote` already exists in both files.

## Data Flow Summary
1. **Whole-page share:** hover page → click share icon → modal (`variant='page'`) with full cleaned page text → Copy/X use the deep link `/books/{id}/{page}`; Facebook uses `/api/share/page/{id}/{page}` for its crawler preview.
2. **Quote share:** select text in a page → floating popover appears at the selection → click → modal (`variant='quote'`) with just the selection → same link pattern, plus `?quote=` on both.
3. **Arrival:** open `/books/{id}/{page}?quote=...` → `AppContext` loads the book, sets `selectedBook`, `view='reader'`, `currentPage={page}`, `pendingQuoteHighlight={quote}` → `VirtualScrollReader` scrolls to `initialPage={currentPage}` (existing mechanism, unchanged) → once the matching `PageItem` is active and rendered, `useQuoteHighlight` finds and highlights the quote, then clears `pendingQuoteHighlight`.

## Testing
- **`shareText.test.ts`** (new): `cleanShareText` (already-covered patterns, moved), `buildSafeTweetText` — untruncated short input, truncation of a long single content line while preserving surrounding lines, and a regression test for the double-encoding bug (assert the returned text's real encoded URL length, not a doubly-encoded one, drives the truncation decision).
- **`useQuoteHighlight.test.ts`** (new, jsdom): single-text-node match wraps and scrolls; match spanning a `<strong>` boundary (multi-node) wraps correctly and preserves surrounding text/structure; no match calls `onHighlightApplied` without throwing or mutating the DOM.
- **`PageItem.test.tsx`** (extend existing): share button renders and opens the modal with cleaned page text; selecting text within the page's content shows the popover at the expected position and opens the modal with the selection as `quote`; `highlightQuote` prop triggers the highlight hook.
- **`ShareSearchResultModal.test.tsx`** (extend existing): `variant='page'`/`'quote'` build the `/books/{id}/{page}` and `/api/share/page/{id}/{page}` URLs correctly with and without `quote`; existing 3-caller behavior (no `bookId`/`pageNumber`) unchanged.
- **Backend** (`services/backend/tests/api/endpoints/`, wherever `share_router` is tested — likely a new or extended file next to `share_book`/`share_qa` tests): scraper vs. non-scraper redirect behavior; missing/private/non-ready book redirects instead of erroring; missing page redirects; `quote` param takes precedence over derived page-text snippet in `og:description`; snippet truncation matches the existing `search_content_pages` cut-to-last-space pattern.
- **`AppContext` deep-link parsing** (wherever `parsePath`/the deep-link effect is currently tested, or new if untested): `/books/{id}` (no page) still works as today; `/books/{id}/{page}` sets `currentPage`; `/books/{id}/{page}?quote=...` sets `pendingQuoteHighlight`; non-numeric `parts[2]` is ignored rather than crashing.

## Verification Plan
1. Backend: `pytest` for the new/extended `share_router` tests.
2. Frontend: `npm test` inside `apps/frontend/` for all new/extended test files above.
3. Manual: rebuild via `./deploy/local/rebuild-and-restart.sh all`; open a book in the reader; hover a page and click the share icon, confirm the modal shows the full page text and posting to X opens a compose window with the full (untruncated, for a normal-length page) text and a `/books/{id}/{page}` link; select a sentence, confirm the floating popover appears and opens the quote-variant modal; copy the generated link and open it in a new tab (logged out, to also sanity-check the public backend endpoint), confirm it lands on the correct page auto-scrolled and, for the quote link, the selected sentence is highlighted; check both light and dark mode for the highlight and popover styling; check on mobile viewport width that the popover doesn't overflow the screen edge.
