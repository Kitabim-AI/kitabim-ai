# Reader Page & Quote Sharing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let readers share a whole page or a highlighted quote from the reader to X/Facebook/copy, with shared links deep-linking to the exact page (and highlighting the quote, for quote shares) — publicly, no login required, matching the existing reader/book-share access pattern.

**Architecture:** Extract the tweet-truncation/icon logic that's currently copy-pasted across three share modals into shared `utils/shareText.ts` + `ShareIcons.tsx`, generalize `ShareSearchResultModal` to also serve page/quote shares (new `bookId`/`pageNumber`/`quote`/`variant` props), add a new public backend OG-preview endpoint modeled on the existing `share_qa` handler, extend the existing `/books/<id>` deep-link parsing to carry a page number and quote, and add a DOM `TreeWalker`/`Range`-based hook that finds and highlights the shared quote once its page renders.

**Tech Stack:** React 19 + TypeScript (frontend), FastAPI + SQLAlchemy async (backend), Vitest + @testing-library/react (frontend tests), pytest + unittest.mock (backend tests).

**Spec:** `docs/superpowers/specs/2026-08-16-reader-page-quote-share-design.md`

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)`.
- No `os.environ.get()` in application code — use `settings.*` from `core/config.py`.
- No hardcoded user-visible strings — use `t("errors.key")` (backend) / `t('key')` (frontend); every new i18n key added to **both** `en.json` and `ug.json`.
- No raw SQL with user input — SQLAlchemy bound parameters / repository methods only.
- The new `/api/share/page/{book_id}/{page_number}` endpoint is **intentionally public** (no auth dependency) — matches the existing `share_book`/`share_qa` endpoints in the same file, and matches the fact that the reader itself and its existing book-share button are already public end-to-end (see spec's Access Control section).
- Quote highlighting uses **exact substring matching only** — no fuzzy/normalized text matching. If no match is found, fail silently (no error UI), just scroll to the page.
- `buildSafeTweetText`'s truncation budget is measured against the real single-encoded URL length (`fullUrl.length`), never a second `encodeURIComponent` pass — that double-encoding was the bug already fixed in `ShareChatModal.tsx` on this branch; do not reintroduce it while generalizing.
- Frontend tests: always assert against i18n **keys** (the test mock returns the key as-is), never translated strings.
- Backend endpoint tests: call the router function directly with mocked args (per `api-unit-tester` skill) — this codebase does not use `TestClient`/`AsyncClient` for endpoint tests.

---

### Task 1: Shared tweet-text utilities (`shareText.ts`)

**Files:**
- Create: `apps/frontend/src/utils/shareText.ts`
- Create: `apps/frontend/src/tests/utils/shareText.test.ts`

**Interfaces:**
- Produces: `cleanShareText(text: string): string`
- Produces: `interface SafeTweetInput { headLines: string[]; contentPrefix: string; contentText: string; contentSuffix?: string; tailLines: string[]; maxUrlLength?: number }`
- Produces: `buildSafeTweetText(input: SafeTweetInput): string`

- [ ] **Step 1: Write the failing tests**

```typescript
// apps/frontend/src/tests/utils/shareText.test.ts
import { describe, expect, test } from 'vitest';
import { cleanShareText, buildSafeTweetText } from '@/src/utils/shareText';

describe('cleanShareText', () => {
  test('strips markdown ref links, leaving the link text', () => {
    expect(cleanShareText('ئەلۋەتتە **مەنبە:** [باھادىرنامە](ref:427a5621d325:summary)')).toBe(
      'ئەلۋەتتە **مەنبە:** باھادىرنامە'
    );
  });

  test('strips bare (ref:...) fragments', () => {
    expect(cleanShareText('some text (ref:abc123:1,2,3) more text')).toBe('some text  more text');
  });

  test('strips BookID fragments', () => {
    expect(cleanShareText('answer text (BookID: abc-123)')).toBe('answer text');
  });

  test('trims surrounding whitespace', () => {
    expect(cleanShareText('  hello world  ')).toBe('hello world');
  });

  test('returns empty string for falsy input', () => {
    expect(cleanShareText('')).toBe('');
  });
});

describe('buildSafeTweetText', () => {
  test('returns the full untruncated join when it already fits', () => {
    const result = buildSafeTweetText({
      headLines: ['سوئال: What is the key takeaway?'],
      contentPrefix: 'زېرەكچاق: ',
      contentText: 'Knowledge is power.',
      tailLines: ['— Source: Sample Book', '-- كىتابىم تورى\nhttps://kitabim.ai'],
    });

    expect(result).toBe(
      'سوئال: What is the key takeaway?\n\nزېرەكچاق: Knowledge is power.\n\n— Source: Sample Book\n\n-- كىتابىم تورى\nhttps://kitabim.ai'
    );
  });

  test('omits the content line entirely when contentText is empty (no stray prefix/suffix)', () => {
    const result = buildSafeTweetText({
      headLines: ['📌 A Proverb'],
      contentPrefix: '"',
      contentText: '',
      contentSuffix: '"',
      tailLines: ['https://kitabim.ai'],
    });

    expect(result).toBe('📌 A Proverb\n\nhttps://kitabim.ai');
  });

  test('does not truncate long Uyghur content that still fits the real (single-encoded) URL budget — regression test for the double-encoding bug', () => {
    // 1500 Uyghur characters encode to ~9000 chars in a real single-encodeURIComponent
    // pass, comfortably under the default 10000 maxUrlLength. A buggy implementation
    // that measures a SECOND encodeURIComponent pass over the already-encoded URL would
    // inflate this by ~1.6x and truncate it unnecessarily — this test fails on that bug.
    const longContent = 'پەرزەنت تەربىيەسىدە ئائىلە، ئەخلاق ۋە مىللىي كىملىك ئاساسىي ئورۇندا تورىدۇ. '.repeat(20);
    const result = buildSafeTweetText({
      headLines: ['سوئال: قىسقا سوئال'],
      contentPrefix: 'زېرەكچاق: ',
      contentText: longContent,
      tailLines: ['https://kitabim.ai'],
    });

    expect(result).toContain(longContent.trim());
    expect(result).not.toContain('…');
  });

  test('truncates content that exceeds the real URL budget, preserving head/tail lines', () => {
    const veryLongContent = 'پەرزەنت تەربىيەسىدە ئائىلە، ئەخلاق ۋە مىللىي كىملىك ئاساسىي ئورۇندا تورىدۇ. '.repeat(120);
    const result = buildSafeTweetText({
      headLines: ['سوئال: قىسقا سوئال'],
      contentPrefix: 'زېرەكچاق: ',
      contentText: veryLongContent,
      tailLines: ['https://kitabim.ai'],
      maxUrlLength: 2000,
    });

    expect(result).toContain('سوئال: قىسقا سوئال');
    expect(result).toContain('https://kitabim.ai');
    expect(result).toContain('…');
    expect(result.length).toBeLessThan(veryLongContent.length);

    const realUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(result)}`;
    expect(realUrl.length).toBeLessThanOrEqual(2000);
  });

  test('caps an overly long head line to 80 chars when truncation is triggered', () => {
    const longHead = 'سوئال: ' + 'ئۇيغۇرچە سوئال سۆزى '.repeat(20);
    const veryLongContent = 'جاۋاب مەزمۇنى '.repeat(200);
    const result = buildSafeTweetText({
      headLines: [longHead],
      contentPrefix: 'زېرەكچاق: ',
      contentText: veryLongContent,
      tailLines: ['https://kitabim.ai'],
      maxUrlLength: 1500,
    });

    const headLineInResult = result.split('\n\n')[0];
    expect(headLineInResult.length).toBeLessThanOrEqual(81); // 80 chars + ellipsis
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/utils/shareText.test.ts`
Expected: FAIL with "Failed to resolve import" / "Cannot find module '@/src/utils/shareText'"

- [ ] **Step 3: Write the implementation**

```typescript
// apps/frontend/src/utils/shareText.ts

/** Strips markdown ref-links, bare (ref:...) fragments, and BookID fragments from
 * shareable text — keeps the visible label of `[text](ref:...)` links, drops
 * everything else that's an internal reference artifact, not meant for readers. */
export const cleanShareText = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/\[([^\]]+)\]\(ref:[^)]+\)/g, '$1')
    .replace(/\(ref:[^)]+\)/g, '')
    .replace(/\s*\(?BookID:\s*[a-zA-Z0-9-]+\)?/gi, '')
    .trim();
};

export interface SafeTweetInput {
  /** Fixed short lines before the content line (already formatted, e.g. `سوئال: ${q}`);
   * '' entries are dropped. Capped to 80 chars (last-space-safe) if truncation is needed. */
  headLines: string[];
  /** Prepended to the (possibly truncated) content text, e.g. 'زېرەكچاق: ' or '"'. */
  contentPrefix: string;
  /** The long free-text line that gets binary-searched down when the tweet doesn't fit. */
  contentText: string;
  /** Appended after the (possibly truncated) content text, e.g. closing '"'. */
  contentSuffix?: string;
  /** Fixed lines after the content line (source, footer); '' entries dropped, never shrunk. */
  tailLines: string[];
  /** Real single-encoded URL length budget. Default 10000 — comfortably under
   * browser/server URL-length limits, generous enough for multi-citation RAG answers. */
  maxUrlLength?: number;
}

const capHeadLine = (line: string): string => {
  if (line.length <= 80) return line;
  const truncated = line.slice(0, 80);
  const lastSpace = truncated.lastIndexOf(' ');
  return (lastSpace > 50 ? truncated.slice(0, lastSpace) : truncated).trim() + '…';
};

export const buildSafeTweetText = ({
  headLines,
  contentPrefix,
  contentText,
  contentSuffix = '',
  tailLines,
  maxUrlLength = 10000,
}: SafeTweetInput): string => {
  const join = (head: string[], content: string) => {
    const contentLine = content ? `${contentPrefix}${content}${contentSuffix}` : '';
    return [...head, contentLine, ...tailLines].filter(Boolean).join('\n\n');
  };

  const fullText = join(headLines, contentText);
  const fullUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(fullText)}`;
  if (fullUrl.length <= maxUrlLength) {
    return fullText;
  }

  const cappedHeadLines = headLines.map(capHeadLine);

  let low = 0;
  let high = contentText.length;
  let bestText = join(cappedHeadLines, contentText);

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const rawSub = contentText.slice(0, mid);
    const lastSpace = rawSub.lastIndexOf(' ');
    const candContent =
      (lastSpace > mid * 0.6 ? rawSub.slice(0, lastSpace) : rawSub).trim() +
      (mid < contentText.length ? '…' : '');

    const candText = join(cappedHeadLines, candContent);
    const candUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(candText)}`;

    if (candUrl.length <= maxUrlLength) {
      bestText = candText;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return bestText;
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/utils/shareText.test.ts`
Expected: PASS — all 9 tests green

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/utils/shareText.ts apps/frontend/src/tests/utils/shareText.test.ts
git commit -m "$(cat <<'EOF'
feat: extract shared cleanShareText/buildSafeTweetText utilities

Generalizes ShareChatModal's tweet-truncation logic (with the
already-fixed double-encoding bug preserved) so it can be reused by
ShareModal and the generalized ShareSearchResultModal instead of
each modal carrying its own copy.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Shared `ShareIcons.tsx` + migrate `ShareChatModal`/`ShareModal` to shared utils

**Files:**
- Create: `apps/frontend/src/components/share/ShareIcons.tsx`
- Modify: `apps/frontend/src/components/share/ShareChatModal.tsx`
- Modify: `apps/frontend/src/components/share/ShareModal.tsx`

**Interfaces:**
- Consumes: `cleanShareText`, `buildSafeTweetText`, `SafeTweetInput` from Task 1 (`apps/frontend/src/utils/shareText.ts`)
- Produces: `XIcon`, `FacebookIcon` React components from `apps/frontend/src/components/share/ShareIcons.tsx`

- [ ] **Step 1: Create the shared icons file**

```tsx
// apps/frontend/src/components/share/ShareIcons.tsx
import React from 'react';

export const FacebookIcon: React.FC = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
  </svg>
);

export const XIcon: React.FC = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);
```

- [ ] **Step 2: Migrate `ShareChatModal.tsx` to shared icons + shared utils**

Replace the local icon definitions and imports:

```tsx
// apps/frontend/src/components/share/ShareChatModal.tsx
// Remove these lines:
//   import { Check, ClipboardPaste, Copy, X } from 'lucide-react';
//   const FacebookIcon = () => ( ... );
//   const XIcon = () => ( ... );
// Replace the top of the file with:

import { Check, ClipboardPaste, Copy, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { cleanShareText, buildSafeTweetText } from '../../utils/shareText';
import { FacebookIcon, XIcon } from './ShareIcons';
```

Replace the local `cleanShareText` function and `buildSafeTweetText` function bodies with calls into the shared module:

```tsx
  const safeQ = cleanShareText(question || '');
  const safeA = cleanShareText(answer || '');

  const shareUrl = window.location.origin;

  const footerText = `-- كىتابىم تورى\n${shareUrl}`;
  const qaText = [
    safeQ ? `سوئال: ${safeQ}` : '',
    safeA ? `زېرەكچاق: ${safeA}` : '',
    bookTitle ? `— Source: ${bookTitle}` : '',
    footerText
  ].filter(Boolean).join('\n\n');

  const handleCopy = async () => {
    await navigator.clipboard.writeText(qaText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTwitter = () => {
    const tweetText = buildSafeTweetText({
      headLines: [safeQ ? `سوئال: ${safeQ}` : ''],
      contentPrefix: 'زېرەكچاق: ',
      contentText: safeA,
      tailLines: [
        bookTitle ? `— Source: ${bookTitle}` : '',
        footerText,
      ],
    });
    const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
    window.open(twitterUrl, '_blank', 'noopener,noreferrer,width=550,height=420');
  };
```

Delete the now-unused local `cleanShareText` function and the entire local `buildSafeTweetText` function body (the `MAX_URL_LENGTH` constant, the binary search loop, everything between the old `const buildSafeTweetText = (q, a) => {` and its closing `};`) — they're replaced by the two blocks above. Leave `handleFacebook` and the rest of the component (JSX, `fbClicked`, etc.) unchanged.

- [ ] **Step 3: Migrate `ShareModal.tsx` to shared icons + shared utils**

```tsx
// apps/frontend/src/components/share/ShareModal.tsx
// Replace the top of the file:

import { Book } from '@shared/types';
import { Check, Copy, ExternalLink, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { buildSafeTweetText } from '../../utils/shareText';
import { FacebookIcon, XIcon } from './ShareIcons';
```

Remove the local `FacebookIcon`/`XIcon` definitions. Replace `handleTwitter`:

```tsx
  const handleTwitter = () => {
    const tweetText = buildSafeTweetText({
      headLines: [],
      contentPrefix: '📖 ',
      contentText: `${titleWithVolume}${displayAuthor ? ` - ${displayAuthor}` : ''}`,
      tailLines: [deepLink],
    });
    const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
    window.open(twitterUrl, '_blank', 'noopener,noreferrer,width=550,height=420');
  };
```

Note: `titleWithVolume`/`displayAuthor` are defined *after* `handleTwitter` in the current file (lines 48-52) — leave their declaration order as-is (JS function bodies don't evaluate until called, so this already works in the current file and continues to work). This changes the tweet's internal line break from a single `\n` to `\n\n` between the title/author line and the link — cosmetic only, matches the paragraph spacing every other share modal already uses, and no test asserts the exact separator.

- [ ] **Step 4: Run the existing test suites to confirm no regressions**

Run: `cd apps/frontend && npx vitest run src/tests/components/share/ShareChatModal.test.tsx src/tests/components/share/ShareModal.test.tsx`
Expected: PASS — all existing tests in both files still green (behavior-preserving refactor)

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/share/ShareIcons.tsx apps/frontend/src/components/share/ShareChatModal.tsx apps/frontend/src/components/share/ShareModal.tsx
git commit -m "$(cat <<'EOF'
refactor: dedupe share-modal icons and tweet-building via shared utils

ShareChatModal and ShareModal now import XIcon/FacebookIcon and
buildSafeTweetText/cleanShareText from the shared modules instead of
each carrying its own copy-pasted version.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: i18n — add `share.sharePage`

**Files:**
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Produces: `t('share.sharePage')` translation key, consumed by Task 5's generalized `ShareSearchResultModal`.

- [ ] **Step 1: Add the key to `en.json`**

In the `"share"` block (currently lines 1005-1021), add `sharePage` right after `shareBook`:

```json
  "share": {
    "shareBook": "Share Book",
    "sharePage": "Share Page",
    "shareQA": "Share Answer",
    "shareQuote": "Share Quote",
```

- [ ] **Step 2: Add the key to `ug.json`**

In the `"share"` block (currently lines 1025-1041), add `sharePage` right after `shareBook`:

```json
  "share": {
    "shareBook": "كىتابنى ھەمبەھىرلەش",
    "sharePage": "بەتنى ھەمبەھىرلەش",
    "shareQA": "جاۋابنى ھەمبەھىرلەش",
    "shareQuote": "ئىقتىباسنى ھەمبەھىرلەش",
```

- [ ] **Step 3: Verify both files are still valid JSON**

Run: `cd apps/frontend && node -e "JSON.parse(require('fs').readFileSync('src/locales/en.json')); JSON.parse(require('fs').readFileSync('src/locales/ug.json')); console.log('valid')"`
Expected: prints `valid`

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "$(cat <<'EOF'
feat: add share.sharePage i18n key

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Backend `/api/share/page/{book_id}/{page_number}` endpoint

**Files:**
- Modify: `services/backend/api/endpoints/share_router.py`
- Create: `services/backend/tests/api/endpoints/share_router_test.py`

**Interfaces:**
- Consumes: `BooksRepository.get(book_id) -> Optional[Book]` (existing, `packages/backend-core/app/db/repositories/base_repository.py`), `PagesRepository.find_one(book_id, page_number) -> Optional[Page]` (existing, `packages/backend-core/app/db/repositories/pages_repository.py:189-194`), `settings.frontend_base_url` (existing, `packages/backend-core/app/core/config.py:180`).
- Produces: `GET /api/share/page/{book_id}/{page_number}?quote=<optional>` — public endpoint, redirects non-scrapers to `{frontend_base_url}/books/{book_id}/{page_number}[?quote=...]`, serves OG-tagged HTML to scrapers.

- [ ] **Step 1: Write the failing tests**

```python
# services/backend/tests/api/endpoints/share_router_test.py
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)
for _p in (BACKEND_CORE_DIR, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.config import settings  # noqa: E402 — needs the sys.path insert above


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def make_request(user_agent: str, url: str = "https://kitabim.ai/api/share/page/b1/5"):
    request = MagicMock()
    request.headers = {"user-agent": user_agent}
    request.url = url
    return request


def make_book(status="ready", visibility="public", title="Test Book"):
    return SimpleNamespace(status=status, visibility=visibility, title=title)


def make_page(text="Some page content."):
    return SimpleNamespace(text=text)


@pytest.mark.asyncio
async def test_share_page_redirects_non_scraper():
    setup_paths()
    from api.endpoints.share_router import share_page

    result = await share_page(
        book_id="b1",
        page_number=5,
        request=make_request("Mozilla/5.0"),
        quote=None,
        session=MagicMock(),
    )

    assert result.status_code == 302
    assert result.headers["location"] == f"{settings.frontend_base_url}/books/b1/5"


@pytest.mark.asyncio
async def test_share_page_redirects_non_scraper_with_quote():
    setup_paths()
    from api.endpoints.share_router import share_page

    result = await share_page(
        book_id="b1",
        page_number=5,
        request=make_request("Mozilla/5.0"),
        quote="a highlighted quote",
        session=MagicMock(),
    )

    assert result.status_code == 302
    assert (
        result.headers["location"]
        == f"{settings.frontend_base_url}/books/b1/5?quote=a%20highlighted%20quote"
    )


@pytest.mark.asyncio
async def test_share_page_scraper_returns_og_html_from_page_text():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book()

    async def fake_find_one(*args, **kwargs):
        return make_page("Answer text [link](ref:427a5621d325:summary) (BookID: abc-123)")

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get
    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = fake_find_one

    with patch("api.endpoints.share_router.BooksRepository", return_value=mock_books_repo), \
         patch("api.endpoints.share_router.PagesRepository", return_value=mock_pages_repo):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("facebookexternalhit/1.1"),
            quote=None,
            session=MagicMock(),
        )

    body = result.body.decode()
    assert "og:title" in body
    assert "Test Book" in body
    assert "link" in body
    assert "ref:427a5621d325" not in body
    assert "BookID" not in body


@pytest.mark.asyncio
async def test_share_page_quote_overrides_page_text_in_description():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book()

    async def fake_find_one(*args, **kwargs):
        return make_page("This is the full page text, not the quote.")

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get
    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = fake_find_one

    with patch("api.endpoints.share_router.BooksRepository", return_value=mock_books_repo), \
         patch("api.endpoints.share_router.PagesRepository", return_value=mock_pages_repo):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("twitterbot"),
            quote="a specific highlighted quote",
            session=MagicMock(),
        )

    body = result.body.decode()
    assert "a specific highlighted quote" in body
    assert "This is the full page text" not in body


@pytest.mark.asyncio
async def test_share_page_redirects_when_book_private():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book(visibility="private")

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get

    with patch("api.endpoints.share_router.BooksRepository", return_value=mock_books_repo):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("facebookexternalhit/1.1"),
            quote=None,
            session=MagicMock(),
        )

    assert result.status_code == 302


@pytest.mark.asyncio
async def test_share_page_redirects_when_page_missing():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book()

    async def fake_find_one(*args, **kwargs):
        return None

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get
    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = fake_find_one

    with patch("api.endpoints.share_router.BooksRepository", return_value=mock_books_repo), \
         patch("api.endpoints.share_router.PagesRepository", return_value=mock_pages_repo):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("facebookexternalhit/1.1"),
            quote=None,
            session=MagicMock(),
        )

    assert result.status_code == 302
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd services/backend && pytest tests/api/endpoints/share_router_test.py -v`
Expected: FAIL with `ImportError: cannot import name 'share_page' from 'api.endpoints.share_router'`

- [ ] **Step 3: Implement the endpoint**

Add near the top of `services/backend/api/endpoints/share_router.py`, alongside the existing imports:

```python
import re
from urllib.parse import quote as url_quote
```

Add these two module-level helpers right after the `_SCRAPER_AGENTS` tuple:

```python
_REF_LINK_RE = re.compile(r"\[([^\]]+)\]\(ref:[^)]+\)")
_REF_PAREN_RE = re.compile(r"\(ref:[^)]+\)")
_BOOK_ID_RE = re.compile(r"\s*\(?BookID:\s*[a-zA-Z0-9-]+\)?", re.IGNORECASE)


def _clean_share_text(text: str) -> str:
    """Mirrors the frontend's cleanShareText (apps/frontend/src/utils/shareText.ts)."""
    if not text:
        return ""
    cleaned = _REF_LINK_RE.sub(r"\1", text)
    cleaned = _REF_PAREN_RE.sub("", cleaned)
    cleaned = _BOOK_ID_RE.sub("", cleaned)
    return cleaned.strip()


def _truncate_snippet(text: str, max_len: int = 300) -> str:
    """Same cut-to-last-space-plus-ellipsis pattern as
    PagesRepository.search_content_pages (pages_repository.py)."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "..."
```

Add the import for `PagesRepository` alongside the existing `BooksRepository` import:

```python
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.pages_repository import PagesRepository
```

Add the new endpoint at the end of the file, after `share_qa`:

```python
@router.get("/page/{book_id}/{page_number}")
async def share_page(
    book_id: str,
    page_number: int,
    request: Request,
    quote: str | None = Query(None, max_length=500),
    session: AsyncSession = Depends(get_session),
):
    safe_id = html.escape(book_id)
    base_url = settings.frontend_base_url
    deep_link = f"{base_url}/books/{safe_id}/{page_number}"
    if quote:
        deep_link = f"{deep_link}?quote={url_quote(quote)}"
    share_url = str(request.url)

    user_agent = request.headers.get("user-agent", "").lower()
    is_scraper = any(bot in user_agent for bot in _SCRAPER_AGENTS)

    if not is_scraper:
        return RedirectResponse(url=deep_link, status_code=302)

    try:
        books_repo = BooksRepository(session)
        book = await books_repo.get(book_id)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Page share endpoint DB error",
            book_id=book_id,
            page_number=page_number,
            error=str(exc),
        )
        return RedirectResponse(url=deep_link, status_code=302)

    if not book or book.status != "ready" or book.visibility == "private":
        return RedirectResponse(url=deep_link, status_code=302)

    try:
        pages_repo = PagesRepository(session)
        page = await pages_repo.find_one(book_id, page_number)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Page share endpoint page lookup failed",
            book_id=book_id,
            page_number=page_number,
            error=str(exc),
        )
        return RedirectResponse(url=deep_link, status_code=302)

    if not page:
        return RedirectResponse(url=deep_link, status_code=302)

    title = html.escape(book.title or "")
    page_label = f"{page_number}-بەت"
    og_title = f"{title} — {page_label}" if title else page_label

    if quote:
        description = html.escape(" ".join(quote.split()))
    else:
        cleaned = _clean_share_text(page.text or "")
        snippet = _truncate_snippet(cleaned)
        description = html.escape(" ".join(snippet.split()))

    cover_url = f"{base_url}/api/covers/{safe_id}.jpg"

    log_json(
        logger,
        logging.INFO,
        "Page share page served to scraper",
        book_id=book_id,
        page_number=page_number,
        agent=user_agent[:80],
    )

    page_html = f"""<!DOCTYPE html>
<html lang="ug" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta property="og:type" content="article">
  <meta property="og:title" content="{og_title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{cover_url}">
  <meta property="og:url" content="{html.escape(share_url)}">
  <meta property="og:site_name" content="كىتابىم">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{og_title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{cover_url}">
  <title>{og_title}</title>
</head>
<body></body>
</html>"""

    return HTMLResponse(content=page_html)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd services/backend && pytest tests/api/endpoints/share_router_test.py -v`
Expected: PASS — all 6 tests green

- [ ] **Step 5: Run the full backend test suite to confirm no regressions**

Run: `pytest services/backend/tests/ -q`
Expected: PASS (no new failures)

- [ ] **Step 6: Commit**

```bash
git add services/backend/api/endpoints/share_router.py services/backend/tests/api/endpoints/share_router_test.py
git commit -m "$(cat <<'EOF'
feat: add public /api/share/page/{book_id}/{page_number} endpoint

OG-preview endpoint for page/quote sharing, modeled on the existing
share_qa handler: scraper-gated, redirects real browsers to the
/books/{id}/{page} deep link, serves cleaned+truncated page-text (or
the shared quote, when present) as the crawler-visible description.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Generalize `ShareSearchResultModal` for page/quote sharing

**Files:**
- Modify: `apps/frontend/src/components/share/ShareSearchResultModal.tsx`
- Modify: `apps/frontend/src/tests/components/share/ShareSearchResultModal.test.tsx`

**Interfaces:**
- Consumes: `buildSafeTweetText` from Task 1; `t('share.sharePage')` from Task 3; the `/api/share/page/{book_id}/{page_number}` shape from Task 4.
- Produces: `ShareSearchResultModal` gains optional props `bookId?: string`, `pageNumber?: number`, `quote?: string`, `variant?: 'searchResult' | 'page' | 'quote'` (default `'searchResult'`). Existing props (`title`, `subtitle`, `content`, `sourceLabel`, `url`, `onClose`) and the 3 existing callers (`QuranResultsList.tsx`, `LookupResultsList.tsx`, `ContentResultsList.tsx`) are unaffected.

- [ ] **Step 1: Write the failing tests**

Add these tests to the end of `apps/frontend/src/tests/components/share/ShareSearchResultModal.test.tsx`, inside the existing `describe('ShareSearchResultModal', ...)` block:

```tsx
  // Extracts the `text` (or `u`) query param via the URL API instead of manually
  // decodeURIComponent-ing the whole string — this content embeds an already-encoded
  // URL (the deep link's own ?quote= param), so a single blind decode of the outer
  // string leaves that inner encoding intact; parsing per-param avoids reasoning
  // about how many encoding layers are actually being unwound.
  const getOpenedQueryParam = (paramName: string): string => {
    const openCall = vi.mocked(window.open).mock.calls[0][0] as string;
    return new URL(openCall).searchParams.get(paramName) || '';
  };

  it('renders the page-share header label and deep link when bookId/pageNumber are given', () => {
    render(
      <ShareSearchResultModal
        title="My Book"
        content="Page text content here."
        bookId="book-1"
        pageNumber={5}
        variant="page"
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('share.sharePage')).toBeInTheDocument();

    fireEvent.click(screen.getByText('share.postToX'));
    const tweetText = getOpenedQueryParam('text');
    expect(tweetText).toContain(`${window.location.origin}/books/book-1/5`);
    expect(tweetText).not.toContain('quote=');
  });

  it('renders the quote-share header label and includes the quote query param when quote is given', () => {
    render(
      <ShareSearchResultModal
        title="My Book"
        content="a highlighted quote"
        bookId="book-1"
        pageNumber={5}
        quote="a highlighted quote"
        variant="quote"
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('share.shareQuote')).toBeInTheDocument();

    fireEvent.click(screen.getByText('share.postToX'));
    const tweetText = getOpenedQueryParam('text');
    expect(tweetText).toContain(
      `${window.location.origin}/books/book-1/5?quote=${encodeURIComponent('a highlighted quote')}`
    );
  });

  it('uses the /api/share/page OG-preview URL (not the plain deep link) for the Facebook sharer', () => {
    render(
      <ShareSearchResultModal
        title="My Book"
        content="Page text content here."
        bookId="book-1"
        pageNumber={5}
        variant="page"
        onClose={onCloseMock}
      />
    );

    fireEvent.click(screen.getByText('share.postToFacebook'));
    expect(getOpenedQueryParam('u')).toBe(`${window.location.origin}/api/share/page/book-1/5`);
  });

  it('falls back to the plain url prop when bookId/pageNumber are not given (existing callers unaffected)', () => {
    render(
      <ShareSearchResultModal
        title="Dictionary Entry"
        content="definition text"
        url="https://kitabim.ai/dictionary/entry-1"
        onClose={onCloseMock}
      />
    );

    fireEvent.click(screen.getByText('share.postToX'));
    const tweetText = getOpenedQueryParam('text');
    expect(tweetText).toContain('https://kitabim.ai/dictionary/entry-1');
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/share/ShareSearchResultModal.test.tsx`
Expected: FAIL — `share.sharePage`/`share.shareQuote` text not found (component doesn't yet accept `bookId`/`pageNumber`/`quote`/`variant`)

- [ ] **Step 3: Generalize the component**

```tsx
// apps/frontend/src/components/share/ShareSearchResultModal.tsx
import { Check, Copy, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { buildSafeTweetText } from '../../utils/shareText';
import { FacebookIcon, XIcon } from './ShareIcons';

interface ShareSearchResultModalProps {
  title: string;
  subtitle?: string;
  content: string;
  sourceLabel?: string;
  url?: string;
  bookId?: string;
  pageNumber?: number;
  quote?: string;
  variant?: 'searchResult' | 'page' | 'quote';
  onClose: () => void;
}

export const ShareSearchResultModal: React.FC<ShareSearchResultModalProps> = ({
  title,
  subtitle,
  content,
  sourceLabel,
  url,
  bookId,
  pageNumber,
  quote,
  variant = 'searchResult',
  onClose,
}) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const isPageShare = bookId !== undefined && pageNumber !== undefined;
  const quoteQueryParam = quote ? `?quote=${encodeURIComponent(quote)}` : '';
  const deepLink = isPageShare
    ? `${window.location.origin}/books/${bookId}/${pageNumber}${quoteQueryParam}`
    : undefined;
  const ogPreviewLink = isPageShare
    ? `${window.location.origin}/api/share/page/${bookId}/${pageNumber}${quoteQueryParam}`
    : undefined;

  const shareTargetUrl = deepLink || url || window.location.origin;
  const facebookTargetUrl = ogPreviewLink || shareTargetUrl;

  const fullTextToShare = [
    title ? `📌 ${title}` : '',
    subtitle ? `(${subtitle})` : '',
    content ? `"${content}"` : '',
    sourceLabel ? `— Source: ${sourceLabel}` : '',
    `Kitabim AI: ${shareTargetUrl}`,
  ]
    .filter(Boolean)
    .join('\n\n');

  const handleCopy = async () => {
    await navigator.clipboard.writeText(fullTextToShare);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTwitter = () => {
    const tweetText = buildSafeTweetText({
      headLines: [title ? `📌 ${title}` : ''],
      contentPrefix: '"',
      contentText: content,
      contentSuffix: '"',
      tailLines: [
        sourceLabel ? `— ${sourceLabel}` : '',
        shareTargetUrl,
      ],
    });

    const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
    window.open(twitterUrl, '_blank', 'noopener,noreferrer,width=550,height=420');
  };

  const handleFacebook = async () => {
    await navigator.clipboard.writeText(fullTextToShare).catch(() => {});
    const fbUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(facebookTargetUrl)}`;
    window.open(fbUrl, '_blank', 'noopener,noreferrer,width=620,height=560');
  };

  const previewContent = content.length > 200 ? content.slice(0, 200) + '…' : content;

  const headerLabel =
    variant === 'page' ? t('share.sharePage') :
    variant === 'quote' ? t('share.shareQuote') :
    t('share.shareSearchResult');

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" dir="rtl">
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl" onClick={onClose} />

      <div
        className="relative z-10 w-full max-w-md bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[32px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] dark:shadow-black/35 overflow-hidden border border-white/40 dark:border-slate-800 animate-scale-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl">
              <XIcon />
            </div>
            <span className="font-normal text-[#1a1a1a] dark:text-slate-100 uyghur-text">
              {headerLabel}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-red-50 dark:hover:bg-red-950/20 text-slate-300 dark:text-slate-500 hover:text-red-400 dark:hover:text-red-400 rounded-xl transition-all"
          >
            <X size={20} strokeWidth={2.5} />
          </button>
        </div>

        {/* Search Result Card Preview */}
        <div className="p-5 pb-4 flex flex-col gap-3">
          <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wider font-normal text-right">
            {t('share.previewLabel')}
          </p>

          <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4 shadow-sm flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100 uyghur-text">
                {title}
              </h4>
              {sourceLabel && (
                <span className="px-2.5 py-0.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] font-medium text-xs rounded-full shrink-0">
                  {sourceLabel}
                </span>
              )}
            </div>

            {subtitle && (
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium uyghur-text">
                {subtitle}
              </p>
            )}

            {previewContent && (
              <p className="text-sm text-slate-700 dark:text-slate-300 uyghur-text leading-relaxed bg-slate-50 dark:bg-slate-900 p-3 rounded-xl border border-slate-100 dark:border-slate-800">
                {previewContent}
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="grid grid-cols-3 gap-2 p-5 pt-0">
          <button
            onClick={handleCopy}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[#1a1a1a] dark:text-slate-200 rounded-2xl text-xs font-normal transition-all active:scale-95"
          >
            {copied ? (
              <Check size={15} className="text-emerald-500" strokeWidth={2.5} />
            ) : (
              <Copy size={15} strokeWidth={2.5} />
            )}
            <span className="uyghur-text">{copied ? t('share.linkCopied') : t('share.copyLink')}</span>
          </button>

          <button
            onClick={handleTwitter}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-black hover:bg-slate-900 dark:bg-slate-800 dark:hover:bg-slate-700 text-white rounded-2xl text-xs font-normal transition-all active:scale-95 shadow-md"
          >
            <XIcon />
            <span className="uyghur-text whitespace-nowrap">{t('share.postToX')}</span>
          </button>

          <button
            onClick={handleFacebook}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-[#1877F2] hover:bg-[#166fe5] text-white rounded-2xl text-xs font-normal transition-all active:scale-95 shadow-md shadow-[#1877F2]/30"
          >
            <FacebookIcon />
            <span className="uyghur-text whitespace-nowrap">{t('share.postToFacebook')}</span>
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/share/ShareSearchResultModal.test.tsx`
Expected: PASS — all tests (original + 4 new) green

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/share/ShareSearchResultModal.tsx apps/frontend/src/tests/components/share/ShareSearchResultModal.test.tsx
git commit -m "$(cat <<'EOF'
feat: generalize ShareSearchResultModal for page/quote sharing

Adds optional bookId/pageNumber/quote/variant props that build the
/books/{id}/{page} deep link and /api/share/page OG-preview URL when
present, and route the X tweet through buildSafeTweetText instead of
the previous naive content.slice(0, 160). Existing search-result
callers (no bookId/pageNumber) are unaffected.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `useQuoteHighlight` hook

**Files:**
- Create: `apps/frontend/src/hooks/useQuoteHighlight.ts`
- Create: `apps/frontend/src/tests/hooks/useQuoteHighlight.test.ts`

**Interfaces:**
- Produces: `useQuoteHighlight(containerRef: RefObject<HTMLElement | null>, quote: string | null | undefined, renderedText: string, onApplied?: () => void): void`
  - No-ops (does **not** call `onApplied`) while `containerRef.current` is `null` or `renderedText` is falsy — i.e. while the page is still loading/not yet rendered, so the caller's "pending highlight" state is not cleared prematurely.
  - Once content is rendered: searches for an exact substring match of `quote` in the container's concatenated text-node content; if found, wraps it in a `<mark>` (splitting across multiple text nodes if the match spans element boundaries, e.g. crossing a `<strong>`) and calls `scrollIntoView({ block: 'center', behavior: 'smooth' })` on the first wrapped element; then always calls `onApplied?.()` exactly once (whether or not a match was found).

- [ ] **Step 1: Write the failing tests**

```typescript
// apps/frontend/src/tests/hooks/useQuoteHighlight.test.ts
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { useQuoteHighlight } from '@/src/hooks/useQuoteHighlight';

beforeEach(() => {
  document.body.innerHTML = '';
  Element.prototype.scrollIntoView = vi.fn();
});

const makeContainer = (html: string): HTMLDivElement => {
  const div = document.createElement('div');
  div.innerHTML = html;
  document.body.appendChild(div);
  return div;
};

describe('useQuoteHighlight', () => {
  test('does nothing while renderedText is empty (page still loading) — onApplied is not called', () => {
    const container = makeContainer('<p></p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, 'some quote', '', onApplied));

    expect(onApplied).not.toHaveBeenCalled();
    expect(container.querySelector('mark')).toBeNull();
  });

  test('does nothing when quote is null/undefined — onApplied is not called', () => {
    const container = makeContainer('<p>Hello world</p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, null, 'Hello world', onApplied));

    expect(onApplied).not.toHaveBeenCalled();
  });

  test('wraps and scrolls to a match fully inside a single text node', () => {
    const container = makeContainer('<p>Hello world example text</p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() =>
      useQuoteHighlight(ref, 'world example', 'Hello world example text', onApplied)
    );

    const mark = container.querySelector('mark');
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toBe('world example');
    expect(container.textContent).toBe('Hello world example text');
    expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({
      block: 'center',
      behavior: 'smooth',
    });
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  test('wraps a match spanning multiple text nodes across an element boundary', () => {
    const container = makeContainer('<p>Hello <strong>bold</strong> world</p>');
    // Concatenated raw text: "Hello bold world" — pick a quote spanning all 3 text nodes.
    const quote = 'lo bold wo';
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, quote, 'Hello bold world', onApplied));

    const marks = container.querySelectorAll('mark');
    expect(marks.length).toBeGreaterThan(1);
    expect(container.textContent).toBe('Hello bold world');
    expect(Array.from(marks).map(m => m.textContent).join('')).toBe(quote);
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  test('no-op (no <mark>, no scroll) when the quote is not found, but onApplied still fires once', () => {
    const container = makeContainer('<p>Hello world</p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, 'text that does not exist', 'Hello world', onApplied));

    expect(container.querySelector('mark')).toBeNull();
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(onApplied).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useQuoteHighlight.test.ts`
Expected: FAIL with "Cannot find module '@/src/hooks/useQuoteHighlight'"

- [ ] **Step 3: Implement the hook**

```typescript
// apps/frontend/src/hooks/useQuoteHighlight.ts
import { RefObject, useEffect } from 'react';

const HIGHLIGHT_CLASS = 'bg-[#0369a1]/20 dark:bg-[#38bdf8]/30 rounded px-0.5';

interface TextNodeEntry {
  node: Text;
  start: number;
}

const collectTextNodes = (container: HTMLElement): TextNodeEntry[] => {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const entries: TextNodeEntry[] = [];
  let offset = 0;
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const textNode = node as Text;
    entries.push({ node: textNode, start: offset });
    offset += textNode.data.length;
  }
  return entries;
};

const findNodeAtOffset = (
  entries: TextNodeEntry[],
  offset: number
): { node: Text; localOffset: number } | null => {
  for (const entry of entries) {
    const end = entry.start + entry.node.data.length;
    if (offset >= entry.start && offset <= end) {
      return { node: entry.node, localOffset: offset - entry.start };
    }
  }
  return null;
};

const wrapMatch = (
  entries: TextNodeEntry[],
  start: { node: Text; localOffset: number },
  end: { node: Text; localOffset: number }
): HTMLElement | null => {
  if (start.node === end.node) {
    const range = document.createRange();
    range.setStart(start.node, start.localOffset);
    range.setEnd(end.node, end.localOffset);
    const mark = document.createElement('mark');
    mark.className = HIGHLIGHT_CLASS;
    range.surroundContents(mark);
    return mark;
  }

  const startIdx = entries.findIndex(e => e.node === start.node);
  const endIdx = entries.findIndex(e => e.node === end.node);
  if (startIdx === -1 || endIdx === -1) return null;

  const firstFragment =
    start.localOffset > 0 ? start.node.splitText(start.localOffset) : start.node;
  if (end.localOffset < end.node.data.length) {
    end.node.splitText(end.localOffset);
  }

  const toWrap: Text[] = [firstFragment];
  for (let i = startIdx + 1; i <= endIdx; i++) {
    toWrap.push(entries[i].node);
  }

  let firstWrapper: HTMLElement | null = null;
  toWrap.forEach(textNode => {
    const wrapper = document.createElement('mark');
    wrapper.className = HIGHLIGHT_CLASS;
    textNode.parentNode?.insertBefore(wrapper, textNode);
    wrapper.appendChild(textNode);
    if (!firstWrapper) firstWrapper = wrapper;
  });

  return firstWrapper;
};

/**
 * Finds an exact substring match of `quote` within `containerRef`'s rendered
 * text and wraps it in a <mark>, scrolling it into view. No-ops (without
 * calling onApplied) until the container is mounted and renderedText is
 * non-empty, so a caller using this to clear "pending highlight" state
 * doesn't clear it before the target page has actually rendered.
 */
export function useQuoteHighlight(
  containerRef: RefObject<HTMLElement | null>,
  quote: string | null | undefined,
  renderedText: string,
  onApplied?: () => void
): void {
  useEffect(() => {
    if (!quote) return;
    const container = containerRef.current;
    if (!container || !renderedText) return;

    const entries = collectTextNodes(container);
    const fullText = entries.map(e => e.node.data).join('');
    const matchIndex = fullText.indexOf(quote);

    if (matchIndex === -1) {
      onApplied?.();
      return;
    }

    const start = findNodeAtOffset(entries, matchIndex);
    const end = findNodeAtOffset(entries, matchIndex + quote.length);
    if (!start || !end) {
      onApplied?.();
      return;
    }

    const mark = wrapMatch(entries, start, end);
    mark?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    onApplied?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef, quote, renderedText, onApplied]);
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useQuoteHighlight.test.ts`
Expected: PASS — all 5 tests green

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/hooks/useQuoteHighlight.ts apps/frontend/src/tests/hooks/useQuoteHighlight.test.ts
git commit -m "$(cat <<'EOF'
feat: add useQuoteHighlight hook for shared-quote deep links

Exact-substring TreeWalker/Range match against a page's rendered
text, wrapping single- or multi-text-node matches in <mark> and
scrolling to them. Waits for renderedText/containerRef to be ready
before attempting a match or clearing the caller's pending state, so
it doesn't fire (and give up) before the target page has loaded.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: `useTextSelectionShare` hook

**Files:**
- Create: `apps/frontend/src/hooks/useTextSelectionShare.ts`
- Create: `apps/frontend/src/tests/hooks/useTextSelectionShare.test.ts`

**Interfaces:**
- Produces: `interface TextSelectionShare { text: string; top: number; left: number }`; `useTextSelectionShare(containerRef: RefObject<HTMLElement | null>): TextSelectionShare | null`
  - Listens for `selectionchange`; returns `null` unless there's a non-collapsed selection whose range is fully contained within `containerRef.current`; otherwise returns the trimmed selected text plus `{ top, left }` viewport coordinates (from the selection range's bounding rect) suitable for positioning a `position: fixed` popover above the selection, horizontally centered.

- [ ] **Step 1: Write the failing tests**

```typescript
// apps/frontend/src/tests/hooks/useTextSelectionShare.test.ts
import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { useTextSelectionShare } from '@/src/hooks/useTextSelectionShare';

const fireSelectionChange = () => {
  document.dispatchEvent(new Event('selectionchange'));
};

const selectTextIn = (el: Node, startOffset: number, endOffset: number) => {
  const range = document.createRange();
  range.setStart(el, startOffset);
  range.setEnd(el, endOffset);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
};

beforeEach(() => {
  document.body.innerHTML = '';
  window.getSelection()?.removeAllRanges();
});

describe('useTextSelectionShare', () => {
  test('returns null when there is no selection', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Hello world</p>';
    document.body.appendChild(container);

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));
    expect(result.current).toBeNull();
  });

  test('returns the selected text and coordinates when the selection is inside the container', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Hello world example</p>';
    document.body.appendChild(container);
    const textNode = container.querySelector('p')!.firstChild!;

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));

    selectTextIn(textNode, 6, 11); // "world"
    fireSelectionChange();

    expect(result.current?.text).toBe('world');
    expect(typeof result.current?.top).toBe('number');
    expect(typeof result.current?.left).toBe('number');
  });

  test('returns null when the selection is outside the container', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Inside text</p>';
    document.body.appendChild(container);

    const outside = document.createElement('p');
    outside.textContent = 'Outside text';
    document.body.appendChild(outside);

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));

    selectTextIn(outside.firstChild!, 0, 7);
    fireSelectionChange();

    expect(result.current).toBeNull();
  });

  test('returns null once the selection is cleared', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Hello world</p>';
    document.body.appendChild(container);
    const textNode = container.querySelector('p')!.firstChild!;

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));

    selectTextIn(textNode, 0, 5);
    fireSelectionChange();
    expect(result.current?.text).toBe('Hello');

    window.getSelection()?.removeAllRanges();
    fireSelectionChange();
    expect(result.current).toBeNull();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useTextSelectionShare.test.ts`
Expected: FAIL with "Cannot find module '@/src/hooks/useTextSelectionShare'"

- [ ] **Step 3: Implement the hook**

```typescript
// apps/frontend/src/hooks/useTextSelectionShare.ts
import { RefObject, useEffect, useState } from 'react';

export interface TextSelectionShare {
  text: string;
  top: number;
  left: number;
}

/**
 * Tracks the current text selection, returning its trimmed text and viewport
 * coordinates whenever the selection is non-empty and fully contained within
 * containerRef — used to show a "share this quote" popover near the
 * selection. Returns null otherwise (no selection, or selection outside the
 * container).
 */
export function useTextSelectionShare(
  containerRef: RefObject<HTMLElement | null>
): TextSelectionShare | null {
  const [selection, setSelection] = useState<TextSelectionShare | null>(null);

  useEffect(() => {
    const handleSelectionChange = () => {
      const sel = window.getSelection();
      const container = containerRef.current;

      if (!sel || sel.isCollapsed || sel.rangeCount === 0 || !container) {
        setSelection(null);
        return;
      }

      const range = sel.getRangeAt(0);
      if (!container.contains(range.commonAncestorContainer)) {
        setSelection(null);
        return;
      }

      const text = sel.toString().trim();
      if (!text) {
        setSelection(null);
        return;
      }

      const rect = range.getBoundingClientRect();
      setSelection({ text, top: rect.top, left: rect.left + rect.width / 2 });
    };

    document.addEventListener('selectionchange', handleSelectionChange);
    return () => document.removeEventListener('selectionchange', handleSelectionChange);
  }, [containerRef]);

  return selection;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/hooks/useTextSelectionShare.test.ts`
Expected: PASS — all 4 tests green

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/hooks/useTextSelectionShare.ts apps/frontend/src/tests/hooks/useTextSelectionShare.test.ts
git commit -m "$(cat <<'EOF'
feat: add useTextSelectionShare hook for quote-share popover

Tracks selectionchange and returns the selected text + viewport
coordinates when the selection is non-empty and contained within a
given container ref, null otherwise.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: `AppContext` — deep-link page number + quote

**Files:**
- Modify: `apps/frontend/src/context/AppContext.tsx`
- Modify: `apps/frontend/src/tests/context/AppContext.test.tsx`

**Interfaces:**
- Produces: `AppContextType` gains `pendingQuoteHighlight: string | null` and `setPendingQuoteHighlight: React.Dispatch<React.SetStateAction<string | null>>`. `/books/<id>` deep links now also parse an optional page-number path segment and a `?quote=` query param; when present, they set `currentPage` and `pendingQuoteHighlight` respectively after loading the book. `/books/<id>` with no page number behaves exactly as before (no regression).

- [ ] **Step 1: Write the failing tests**

Add these tests to `apps/frontend/src/tests/context/AppContext.test.tsx`. They need a mocked `PersistenceService.getBookById` and control over `window.location`/history, so add the necessary imports and mock at the top of the file, then the two new tests at the end:

```tsx
// Add to the top of apps/frontend/src/tests/context/AppContext.test.tsx, alongside the
// existing imports:
import { waitFor } from '@testing-library/react';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookById: vi.fn(),
  },
}));

// Add these two tests at the end of the file:

test('deep link /books/<id>/<page> sets currentPage after the book loads', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue({
    id: 'book-1',
    title: 'Deep Linked Book',
  } as any);
  window.history.pushState({}, '', '/books/book-1/7');

  const { result } = renderHook(() => useAppContext(), { wrapper });

  await waitFor(() => {
    expect(result.current.selectedBook?.id).toBe('book-1');
  });
  expect(result.current.currentPage).toBe(7);
  expect(result.current.view).toBe('reader');
});

test('deep link /books/<id>/<page>?quote=... sets pendingQuoteHighlight after the book loads', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue({
    id: 'book-2',
    title: 'Quoted Book',
  } as any);
  window.history.pushState({}, '', '/books/book-2/3?quote=a%20shared%20quote');

  const { result } = renderHook(() => useAppContext(), { wrapper });

  await waitFor(() => {
    expect(result.current.selectedBook?.id).toBe('book-2');
  });
  expect(result.current.currentPage).toBe(3);
  expect(result.current.pendingQuoteHighlight).toBe('a shared quote');
});

test('deep link /books/<id> with no page number leaves currentPage untouched (no regression)', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue({
    id: 'book-3',
    title: 'No Page Book',
  } as any);
  window.history.pushState({}, '', '/books/book-3');

  const { result } = renderHook(() => useAppContext(), { wrapper });

  await waitFor(() => {
    expect(result.current.selectedBook?.id).toBe('book-3');
  });
  expect(result.current.currentPage).toBeNull();
  expect(result.current.pendingQuoteHighlight).toBeNull();
});
```

Note: `window.history.pushState` must run **before** `renderHook` mounts `AppProvider`, since `parsePath` reads `window.location.pathname`/`.search` only once, at mount, to seed initial state.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/context/AppContext.test.tsx`
Expected: FAIL — `currentPage`/`pendingQuoteHighlight` remain `null` for all three new tests (page number and quote are not yet parsed or applied)

- [ ] **Step 3: Extend `parsePath` and the deep-link effect**

Replace the `parsePath` function (currently `AppContext.tsx:64-91`):

```tsx
  const parsePath = (path: string): {
    view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check' | 'graph' | 'dictionary' | 'quran',
    tab: string,
    bookId?: string,
    pageNumber?: number,
    quote?: string,
  } => {
    const parts = path.toLowerCase().split('/').filter(Boolean);
    const viewPortion = parts[0] || 'home';

    let view: 'home' | 'library' | 'admin' | 'reader' | 'global-chat' | 'join-us' | 'spell-check' | 'graph' | 'dictionary' | 'quran' = 'home';
    let tab = 'books';
    let bookId: string | undefined;
    let pageNumber: number | undefined;
    let quote: string | undefined;

    if (viewPortion === 'library') view = 'library';
    else if (viewPortion === 'admin') {
      view = 'admin';
      tab = parts[1] || 'books';
    }
    else if (viewPortion === 'chat') view = 'global-chat';
    else if (viewPortion === 'join-us') view = 'join-us';
    else if (viewPortion === 'spell-check') view = 'spell-check';
    else if (viewPortion === 'reader') view = 'reader';
    else if (viewPortion === 'graph') view = 'graph';
    else if (viewPortion === 'dictionary') view = 'dictionary';
    else if (viewPortion === 'quran') view = 'quran';
    else if (viewPortion === 'books' && parts[1]) {
      // Deep link from social share: /books/<id> or /books/<id>/<pageNumber>?quote=<text>
      view = 'library';
      bookId = parts[1];
      if (parts[2] && /^\d+$/.test(parts[2])) {
        pageNumber = parseInt(parts[2], 10);
      }
      const quoteParam = new URLSearchParams(window.location.search).get('quote');
      if (quoteParam) quote = quoteParam;
    }

    return { view, tab, bookId, pageNumber, quote };
  };
```

Right after `const initialBookId = initialRoute.bookId;` (currently line 96), add:

```tsx
  const initialPageNumber = initialRoute.pageNumber;
  const initialQuote = initialRoute.quote;
```

Add the new state right after `const [currentPage, setCurrentPage] = useState<number | null>(null);` (currently line 166):

```tsx
  const [pendingQuoteHighlight, setPendingQuoteHighlight] = useState<string | null>(null);
```

Replace the deep-link effect (currently `AppContext.tsx:174-183`):

```tsx
  // Open the reader directly when landing on a /books/<id>[/<page>][?quote=] deep
  // link (e.g. from a social share)
  useEffect(() => {
    if (!initialBookId) return;
    PersistenceService.getBookById(initialBookId).then(book => {
      if (book) {
        setSelectedBook(book);
        setViewInternal('reader');
        if (initialPageNumber) setCurrentPage(initialPageNumber);
        if (initialQuote) setPendingQuoteHighlight(initialQuote);
        window.history.replaceState({}, '', '/');
      }
    });
  }, []);
```

Add `pendingQuoteHighlight: string | null;` and `setPendingQuoteHighlight: React.Dispatch<React.SetStateAction<string | null>>;` to the `AppContextType` interface, right after the existing `currentPage`/`setCurrentPage` lines (currently `AppContext.tsx:24-25`):

```tsx
  currentPage: number | null;
  setCurrentPage: React.Dispatch<React.SetStateAction<number | null>>;
  pendingQuoteHighlight: string | null;
  setPendingQuoteHighlight: React.Dispatch<React.SetStateAction<string | null>>;
```

Add `pendingQuoteHighlight,` and `setPendingQuoteHighlight,` to the `value` object, right after the existing `currentPage,`/`setCurrentPage,` lines (currently `AppContext.tsx:242-243`):

```tsx
    currentPage,
    setCurrentPage,
    pendingQuoteHighlight,
    setPendingQuoteHighlight,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/context/AppContext.test.tsx`
Expected: PASS — all tests (2 existing + 3 new) green

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/context/AppContext.tsx apps/frontend/src/tests/context/AppContext.test.tsx
git commit -m "$(cat <<'EOF'
feat: parse page number and quote from /books/<id> deep links

Extends the existing book-share deep-link handling to also read an
optional page-number path segment and ?quote= query param, setting
currentPage/pendingQuoteHighlight after the book loads. Plain
/books/<id> links (no page) behave exactly as before.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: `PageItem` — whole-page share button + quote-selection popover + highlight wiring

**Files:**
- Modify: `apps/frontend/src/components/reader/PageItem.tsx`
- Modify: `apps/frontend/src/tests/components/reader/PageItem.test.tsx`

**Interfaces:**
- Consumes: `ShareSearchResultModal` (Task 5), `useTextSelectionShare` (Task 7), `useQuoteHighlight` (Task 6), `cleanShareText` (Task 1).
- Produces: `PageItem` gains optional props `bookId?: string`, `bookTitle?: string`, `bookAuthor?: string`, `highlightQuote?: string`, `onHighlightApplied?: () => void`. Renders a hover-revealed share button in the header row (opens the page-share modal) and, when text is selected within the page's content, a floating share button near the selection (opens the quote-share modal). All existing props/behavior unchanged.

- [ ] **Step 1: Write the failing tests**

Add these tests to `apps/frontend/src/tests/components/reader/PageItem.test.tsx`. First, add stubs needed by the new hooks/modal to the top of the file (`Element.prototype.scrollIntoView`, `navigator.clipboard`, `window.open`) inside the existing `beforeEach`:

```tsx
// Add inside the existing beforeEach(() => { ... }) block:
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('open', vi.fn());
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
```

Then add these tests at the end of the file:

```tsx
test('PageItem renders a page-share button that opens the share modal with cleaned page text', () => {
  renderPageItem({
    page: { ...mockPage, text: 'Answer text [link](ref:427a5621d325:summary) (BookID: abc-123)' },
    bookId: 'book-1',
    bookTitle: 'My Book',
    bookAuthor: 'An Author',
  });

  fireEvent.click(screen.getByTitle('share.sharePage'));

  expect(screen.getByText('share.sharePage')).toBeInTheDocument();
  expect(screen.getByText(/Answer text link/)).toBeInTheDocument();
});

test('PageItem shows a floating share button near a text selection and opens the quote modal', () => {
  renderPageItem({
    page: { ...mockPage, text: 'Hello world example text' },
    bookId: 'book-1',
    bookTitle: 'My Book',
  });

  const contentParagraph = screen.getByText(/Hello world example text/);
  const textNode = contentParagraph.firstChild!;
  const range = document.createRange();
  range.setStart(textNode, 6);
  range.setEnd(textNode, 11); // "world"
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  fireEvent(document, new Event('selectionchange'));

  fireEvent.click(screen.getByTitle('share.shareQuote'));

  expect(screen.getByText('share.shareQuote')).toBeInTheDocument();
});

test('PageItem calls onHighlightApplied once a highlightQuote match is applied', () => {
  const onHighlightApplied = vi.fn();
  renderPageItem({
    page: { ...mockPage, text: 'Hello highlighted world' },
    highlightQuote: 'highlighted',
    onHighlightApplied,
  });

  expect(onHighlightApplied).toHaveBeenCalledTimes(1);
  expect(document.querySelector('mark')).not.toBeNull();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: FAIL — `share.sharePage`/`share.shareQuote` titles/buttons don't exist yet

- [ ] **Step 3: Wire up `PageItem.tsx`**

Update the imports at the top of `apps/frontend/src/components/reader/PageItem.tsx`:

```tsx
import { BookmarkCheck, Edit3, ListTree, ListX, Loader2, RotateCcw, Save, Share2 } from 'lucide-react';
import React from 'react';
import { useIsEditor } from '../../hooks/useAuth';
import { useQuoteHighlight } from '../../hooks/useQuoteHighlight';
import { useTextSelectionShare } from '../../hooks/useTextSelectionShare';
import { useI18n } from '../../i18n/I18nContext';
import { cleanShareText } from '../../utils/shareText';
import { MarkdownContent } from '../common/MarkdownContent';
import { ShareSearchResultModal } from '../share/ShareSearchResultModal';
```

Extend `PageItemProps` (currently `PageItem.tsx:16-38`) with the new optional props:

```tsx
interface PageItemProps {
  page: any;
  isActive: boolean;
  isEditing: boolean;
  fontSize: number;
  contentFontFamily?: string;
  contentFontClassName?: string;
  onSetActive: () => void;
  onEdit: () => void;
  onReprocess: () => void;
  onSetStartPage?: () => void;
  onToggleToc?: (nextIsToc: boolean) => void;

  tempText: string;
  onTempTextChange: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
  isLoading: boolean;
  isSaving?: boolean;
  isFullscreen?: boolean;
  contentPageOffset?: number;
  onTocPageClick?: (targetPage: number) => void;

  bookId?: string;
  bookTitle?: string;
  bookAuthor?: string;
  highlightQuote?: string;
  onHighlightApplied?: () => void;
}
```

Update the component signature to destructure the new props, add the new refs/state/hooks, right after the existing `containerRef` declaration (currently `PageItem.tsx:47`):

```tsx
export const PageItem: React.FC<PageItemProps> = ({
  page, isActive, isEditing, fontSize, contentFontFamily, contentFontClassName, onSetActive, onEdit, onReprocess, onSetStartPage, onToggleToc,
  tempText, onTempTextChange, onSave, onCancel, isLoading, isSaving, isFullscreen, contentPageOffset, onTocPageClick,
  bookId, bookTitle, bookAuthor, highlightQuote, onHighlightApplied,
}) => {
  const { t } = useI18n();
  const isEditor = useIsEditor();
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [shareState, setShareState] = React.useState<{ content: string; quote?: string } | null>(null);

  const textSelection = useTextSelectionShare(contentRef);
```

Add the `useQuoteHighlight` call after the existing `displayText` memo (currently `PageItem.tsx:87-90`):

```tsx
  const displayText = React.useMemo(
    () => (contentFontClassName === 'reader-font-adobe' ? normalizeArabic(page.text || '') : (page.text || "...")),
    [contentFontClassName, page.text]
  );

  useQuoteHighlight(contentRef, highlightQuote, isLoading || isEditing ? '' : displayText, onHighlightApplied);
```

In the header row's right-side `<div className="flex items-center gap-3">` block (currently `PageItem.tsx:123-130`), add the share button before the existing page-number `<span>`:

```tsx
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShareState({ content: cleanShareText(page.text || '') })}
            title={t('share.sharePage')}
            className={`flex items-center justify-center h-7 w-7 rounded-lg text-slate-400 dark:text-slate-500 hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-all ${isActive ? 'opacity-100' : 'opacity-0'} sm:group-hover:opacity-100`}
          >
            <Share2 size={14} />
          </button>
          <span className="text-xs font-bold text-[#94a3b8] dark:text-slate-500 uppercase flex items-center gap-1.5">
            <span>{t('chat.pageNumber', { page: page.displayPageNumber || page.display_page_number || page.pageNumber })}</span>
            {(page.displayPageNumber || page.display_page_number) && String(page.displayPageNumber || page.display_page_number) !== String(page.pageNumber) && (
              <span className="text-[10px] opacity-60">(PDF {page.pageNumber})</span>
            )}
          </span>
        </div>
```

Wrap the non-editing `<MarkdownContent>` render (currently `PageItem.tsx:167-174`) in a `contentRef`-attached `<div>`:

```tsx
      isLoading ? (
          <div className="flex flex-col items-center justify-center py-10 opacity-50"><Loader2 className="animate-spin text-[#0369a1] dark:text-[#38bdf8] mb-2" /><span className="text-xs uppercase dark:text-slate-400">{t('admin.table.recognizing')}</span></div>
        ) : (
          <div ref={contentRef}>
            <MarkdownContent
              content={displayText}
              className={`uyghur-text text-[#1a1a1a] dark:text-slate-100 ${contentFontClassName || ''}`}
              style={contentStyle}
              contentPageOffset={contentPageOffset}
              onTocPageClick={onTocPageClick}
              isTocPage={page?.isToc ?? page?.is_toc}
            />
          </div>
        )
```

Add the floating selection popover and the share modal right before the component's closing `</div>` (currently `PageItem.tsx:177`, the outermost wrapper's close tag):

```tsx
      {textSelection && (
        <button
          onClick={() => {
            setShareState({ content: textSelection.text, quote: textSelection.text });
            window.getSelection()?.removeAllRanges();
          }}
          title={t('share.shareQuote')}
          style={{
            position: 'fixed',
            top: textSelection.top - 44,
            left: textSelection.left,
            transform: 'translateX(-50%)',
          }}
          className="z-[250] flex items-center justify-center h-9 w-9 rounded-full bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-lg"
        >
          <Share2 size={16} />
        </button>
      )}

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
    </div>
  );
};
```

(That last `</div>\n  );\n};` replaces the file's existing final three lines — everything above it is new, inserted just before them.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/PageItem.test.tsx`
Expected: PASS — all tests (7 existing + 3 new) green

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/reader/PageItem.tsx apps/frontend/src/tests/components/reader/PageItem.test.tsx
git commit -m "$(cat <<'EOF'
feat: wire whole-page and quote sharing into PageItem

Hover-revealed share button in the page header (shares the full
cleaned page text) and a floating popover on text selection (shares
just the selection), both opening the generalized
ShareSearchResultModal. Also wires useQuoteHighlight against a
highlightQuote prop for shared-quote deep links.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Thread new props through `ReaderView` and `VirtualScrollReader`

**Files:**
- Modify: `apps/frontend/src/components/reader/ReaderView.tsx`
- Modify: `apps/frontend/src/components/reader/VirtualScrollReader.tsx`
- Modify: `apps/frontend/src/tests/components/reader/ReaderView.test.tsx`
- Modify: `apps/frontend/src/tests/components/reader/VirtualScrollReader.test.tsx`

**Interfaces:**
- Consumes: `PageItem`'s new props (Task 9), `AppContext`'s `pendingQuoteHighlight`/`setPendingQuoteHighlight` (Task 8).
- Produces: every `PageItem` rendered by the reader (both the non-virtual-scroll list and `VirtualScrollReader`'s render loop) receives `bookId`, `bookTitle`, `bookAuthor`, and a correctly-gated `highlightQuote`/`onHighlightApplied` (only the page matching the current page gets a non-empty `highlightQuote`).

- [ ] **Step 1: Write the failing tests**

Add to `apps/frontend/src/tests/components/reader/ReaderView.test.tsx`: extend the `PageItem` mock (currently lines 52-69) to also render the new props so assertions can see them, and add `pendingQuoteHighlight`/`setPendingQuoteHighlight` to `createContextValue()`:

```tsx
// Replace the existing PageItem mock (lines 52-69) with:
vi.mock('@/src/components/reader/PageItem', () => ({
  PageItem: ({
    page,
    isEditing,
    onEdit,
    onSave,
    onCancel,
    onReprocess,
    bookId,
    bookTitle,
    highlightQuote,
  }: any) => (
    <div>
      <div>{page.text}</div>
      {!isEditing && <button onClick={onEdit}>edit-{page.pageNumber}</button>}
      {isEditing && <button onClick={onSave}>save-{page.pageNumber}</button>}
      {isEditing && <button onClick={onCancel}>cancel-{page.pageNumber}</button>}
      <button onClick={onReprocess}>reprocess-{page.pageNumber}</button>
      <div data-testid={`share-props-${page.pageNumber}`}>
        {bookId || ''}|{bookTitle || ''}|{highlightQuote || ''}
      </div>
    </div>
  ),
}));

// Add to createContextValue() (currently lines 101-127), alongside currentPage/setCurrentPage:
  pendingQuoteHighlight: null,
  setPendingQuoteHighlight: vi.fn(),
```

Add a new test at the end of the file:

```tsx
test('ReaderView passes bookId/bookTitle and gated highlightQuote to each PageItem', () => {
  const contextValue = { ...createContextValue(), pendingQuoteHighlight: 'a quote' };
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(contextValue as any);
  vi.mocked(AuthModule.useAuth).mockReturnValue({ isAuthenticated: true, user: { role: 'admin' } } as any);
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);

  renderReader();

  // mockBook.pages has pageNumber 1 (== currentPage) and 2.
  expect(screen.getByTestId('share-props-1').textContent).toBe('1|Reader Book|a quote');
  expect(screen.getByTestId('share-props-2').textContent).toBe('1|Reader Book|');
});
```

Add to `apps/frontend/src/tests/components/reader/VirtualScrollReader.test.tsx`: extend its `PageItem` mock (currently line 18-20) to expose the new props similarly:

```tsx
// Replace the existing PageItem mock with:
vi.mock('@/src/components/reader/PageItem', () => ({
  PageItem: ({ bookId, bookTitle, highlightQuote }: any) => (
    <div data-testid="page-item">
      Page Content
      <div data-testid="share-props">{bookId || ''}|{bookTitle || ''}|{highlightQuote || ''}</div>
    </div>
  ),
}));
```

Add a new test at the end of the file. The existing `renderReader()` helper (lines 28-33) takes no args and never actually mounts `PageItem` (its mocked `PersistenceService.getBookPages` resolves `[]`, so the `pages` map stays empty and every page renders the loading placeholder instead) — for this test, render `VirtualScrollReader` directly with a `selectedBookPages` prop instead, which syncs synchronously into the internal `pages` map via the component's existing `useEffect` (`VirtualScrollReader.tsx:68-84`) and does mount `PageItem`:

```tsx
test('passes bookId/bookTitle to PageItem and only gates highlightQuote to the current-center page', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { id: 'user-1', role: 'reader' },
  } as any);

  render(
    <I18nContext.Provider value={i18nValue}>
      <VirtualScrollReader
        bookId="book-1"
        totalPages={2}
        fontSize={16}
        scrollParentRef={{ current: document.createElement('div') }}
        selectedBookPages={[
          { pageNumber: 1, text: 'Page 1 text', status: 'ready' },
          { pageNumber: 2, text: 'Page 2 text', status: 'ready' },
        ]}
        initialPage={1}
        bookTitle="My Book"
        pendingQuoteHighlight="a quote"
      />
    </I18nContext.Provider>
  );

  const shareProps = screen.getAllByTestId('share-props').map(el => el.textContent);
  expect(shareProps).toContain('book-1|My Book|a quote'); // page 1 (current center) is highlighted
  expect(shareProps).toContain('book-1|My Book|'); // page 2 is not
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/ReaderView.test.tsx src/tests/components/reader/VirtualScrollReader.test.tsx`
Expected: FAIL — the new `share-props` test IDs render as `||` (empty) since `ReaderView`/`VirtualScrollReader` don't pass the new props yet

- [ ] **Step 3: Wire `ReaderView.tsx`**

Add `pendingQuoteHighlight` and `setPendingQuoteHighlight` to the `useAppContext()` destructure (currently `ReaderView.tsx:36-49`):

```tsx
  const {
    selectedBook,
    view,
    setView,
    previousView,
    currentPage,
    setCurrentPage,
    pendingQuoteHighlight,
    setPendingQuoteHighlight,
    chat,
    bookActions,
    setModal,
    setIsReaderFullscreen,
    fontSize,
    setFontSize,
  } = useAppContext();
```

Add the new props to the `VirtualScrollReader` render (currently `ReaderView.tsx:601-632`):

```tsx
              <VirtualScrollReader
                bookId={selectedBook.id}
                totalPages={selectedBook.totalPages || (selectedBook as any).total_pages || 0}
                fontSize={fontSize}
                contentFontFamily={readerContentFontFamily}
                contentFontClassName={readerContentFontClassName}
                initialPage={currentPage || 1}
                onPageChange={setCurrentPage}
                scrollParentRef={mainScrollRef}
                isFullscreen={isFullscreen}
                isChatCollapsed={isSidebarCollapsed}
                editingPageNum={editingPageNum}
                tempPageText={tempPageText}
                bookTitle={selectedBook.title}
                bookAuthor={selectedBook.author}
                pendingQuoteHighlight={pendingQuoteHighlight}
                onQuoteHighlightApplied={() => setPendingQuoteHighlight(null)}
                onEdit={(pageNum, text) => {
                  setEditingPageNum(pageNum);
                  setTempPageText(text);
                }}
                onReprocess={(pageNum) => {
                  bookActions.handleReProcessPage(selectedBook.id, pageNum);
                }}
                onSetStartPage={isEditor ? (pageNum) => handleSetStartPage(pageNum) : undefined}
                onToggleToc={isEditor ? (pageNum, nextIsToc) => bookActions.handleToggleToc(selectedBook.id, pageNum, nextIsToc) : undefined}
                onTempTextChange={setTempPageText}
                onSave={(pageNum, text) => {
                  handleUpdatePage(selectedBook.id, pageNum, text);
                }}
                onCancel={() => setEditingPageNum(null)}
                isSaving={isSaving}
                selectedBookPages={selectedBook.pages}
                contentPageOffset={contentPageOffset}
                onTocPageClick={handleTocPageClick}
              />
```

(`bookId={selectedBook.id}` was already present — everything else after `tempPageText={tempPageText}` through `onQuoteHighlightApplied={...}` is new.)

Add the same props to the non-virtual-scroll `PageItem` render (currently `ReaderView.tsx:645-673`):

```tsx
                      <PageItem
                        key={page.pageNumber}
                        page={page}
                        isActive={currentPage === page.pageNumber}
                        isEditing={editingPageNum === page.pageNumber}
                        fontSize={fontSize}
                        contentFontFamily={readerContentFontFamily}
                        contentFontClassName={readerContentFontClassName}
                        bookId={selectedBook.id}
                        bookTitle={selectedBook.title}
                        bookAuthor={selectedBook.author}
                        highlightQuote={currentPage === page.pageNumber ? (pendingQuoteHighlight ?? undefined) : undefined}
                        onHighlightApplied={() => setPendingQuoteHighlight(null)}
                        onSetActive={() => setCurrentPage(page.pageNumber)}
                        onEdit={() => { setEditingPageNum(page.pageNumber); setTempPageText(page.text || ''); }}
                        onReprocess={() => bookActions.handleReProcessPage(selectedBook.id, page.pageNumber)}
                        onSetStartPage={isEditor ? () => handleSetStartPage(page.pageNumber) : undefined}
                        onToggleToc={isEditor ? (nextIsToc) => bookActions.handleToggleToc(selectedBook.id, page.pageNumber, nextIsToc) : undefined}
                        tempText={tempPageText}
                        onTempTextChange={setTempPageText}
                        onSave={() => {
                          handleUpdatePage(selectedBook.id, page.pageNumber, tempPageText);
                          window.scrollTo(0, 0);
                        }}
                        onCancel={() => {
                          setEditingPageNum(null);
                          window.scrollTo(0, 0);
                        }}
                        isLoading={!page.text && ((!page.pipelineStep && (page.status === 'ocr_processing' || page.status === 'indexing' || page.status === 'pending')) || (page.pipelineStep === 'ocr' && page.milestone !== 'succeeded'))}
                        isSaving={isSaving}
                        isFullscreen={isFullscreen}
                        contentPageOffset={contentPageOffset}
                        onTocPageClick={handleTocPageClick}
                      />
```

- [ ] **Step 4: Wire `VirtualScrollReader.tsx`**

Add the new props to `VirtualScrollReaderProps` (currently `VirtualScrollReader.tsx:10-34`):

```tsx
interface VirtualScrollReaderProps {
  bookId: string;
  totalPages: number;
  fontSize: number;
  contentFontFamily?: string;
  contentFontClassName?: string;
  initialPage?: number;
  onPageChange?: (page: number) => void;
  scrollParentRef?: React.RefObject<HTMLDivElement>;
  isFullscreen?: boolean;
  isChatCollapsed?: boolean;
  editingPageNum?: number | null;
  tempPageText?: string;
  bookTitle?: string;
  bookAuthor?: string;
  pendingQuoteHighlight?: string | null;
  onQuoteHighlightApplied?: () => void;
  onEdit?: (pageNum: number, text: string) => void;
  onReprocess?: (pageNum: number) => void;
  onTempTextChange?: (text: string) => void;
  onSave?: (pageNum: number, text: string) => void;
  onCancel?: () => void;
  onSetStartPage?: (pageNum: number) => void;
  onToggleToc?: (pageNum: number, nextIsToc: boolean) => void;
  isSaving?: boolean;
  selectedBookPages?: any[];
  contentPageOffset?: number;
  onTocPageClick?: (targetPage: number) => void;
}
```

Destructure them in the component signature (currently `VirtualScrollReader.tsx:36-60`):

```tsx
const VirtualScrollReader: React.FC<VirtualScrollReaderProps> = ({
  bookId,
  totalPages,
  fontSize,
  contentFontFamily,
  contentFontClassName,
  initialPage = 1,
  onPageChange,
  scrollParentRef,
  isFullscreen = false,
  isChatCollapsed = false,
  editingPageNum = null,
  tempPageText = '',
  bookTitle,
  bookAuthor,
  pendingQuoteHighlight = null,
  onQuoteHighlightApplied,
  onEdit,
  onReprocess,
  onTempTextChange,
  onSave,
  onCancel,
  onSetStartPage,
  onToggleToc,
  isSaving = false,
  selectedBookPages = [],
  contentPageOffset,
  onTocPageClick,
}) => {
```

Add the props to the `PageItem` render inside the map loop (currently `VirtualScrollReader.tsx:303-330`):

```tsx
              {page ? (
                <PageItem
                  page={page}
                  fontSize={fontSize}
                  contentFontFamily={contentFontFamily}
                  contentFontClassName={contentFontClassName}
                  isActive={pageNum === currentCenterPage}
                  isEditing={isEditingThisPage}
                  bookId={bookId}
                  bookTitle={bookTitle}
                  bookAuthor={bookAuthor}
                  highlightQuote={pageNum === currentCenterPage ? (pendingQuoteHighlight ?? undefined) : undefined}
                  onHighlightApplied={onQuoteHighlightApplied}
                  onSetActive={() => { }}
                  onEdit={() => onEdit?.(pageNum, page.text || '')}
                  onReprocess={() => onReprocess?.(pageNum)}
                  onSetStartPage={() => onSetStartPage?.(pageNum)}
                  onToggleToc={(nextIsToc) => onToggleToc?.(pageNum, nextIsToc)}
                  tempText={isEditingThisPage ? tempPageText : ''}
                  onTempTextChange={(text) => onTempTextChange?.(text)}
                  onSave={() => {
                    setPages(prev => {
                      const existing = prev.get(pageNum) || page;
                      return new Map(prev).set(pageNum, { ...existing, text: tempPageText });
                    });
                    onSave?.(pageNum, tempPageText);
                  }}
                  onCancel={() => onCancel?.()}
                  isLoading={page.status === 'processing' || page.status === 'indexing'}
                  isSaving={isSaving}
                  isFullscreen={isFullscreen}
                  contentPageOffset={contentPageOffset}
                  onTocPageClick={onTocPageClick}
                />
              ) : (
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/frontend && npx vitest run src/tests/components/reader/ReaderView.test.tsx src/tests/components/reader/VirtualScrollReader.test.tsx`
Expected: PASS — all tests green, including the two new ones

- [ ] **Step 6: Run the full frontend test suite to confirm no regressions**

Run: `cd apps/frontend && npx vitest run`
Expected: PASS (no new failures anywhere)

- [ ] **Step 7: Commit**

```bash
git add apps/frontend/src/components/reader/ReaderView.tsx apps/frontend/src/components/reader/VirtualScrollReader.tsx apps/frontend/src/tests/components/reader/ReaderView.test.tsx apps/frontend/src/tests/components/reader/VirtualScrollReader.test.tsx
git commit -m "$(cat <<'EOF'
feat: thread book/highlight props through ReaderView and VirtualScrollReader

Both PageItem render sites (the non-virtual-scroll list and
VirtualScrollReader's internal loop) now receive bookId/bookTitle/
bookAuthor plus a highlightQuote gated to only the current page, so
page/quote sharing and shared-quote highlighting work in both
rendering modes.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Final Verification (after all tasks)

1. Backend: `pytest services/backend/tests/ -q` and `pytest packages/backend-core/tests/ -q` — full suite green.
2. Frontend: `cd apps/frontend && npx vitest run` — full suite green.
3. Manual, via `./deploy/local/rebuild-and-restart.sh all`:
   - Open a book in the reader as a **guest** (logged out). Hover a page, click the share icon — modal shows the full page text; "Post to X" opens a compose window with the full text and a `/books/{id}/{page}` link; confirm no login prompt appears anywhere in this flow.
   - As a guest, confirm text selection is still blocked (existing anti-copy behavior unchanged) and so the quote-share popover never appears — this is expected, not a bug.
   - Log in, select a sentence in a page, confirm the floating popover appears and opens the quote-variant modal with the correct header label (`share.shareQuote`).
   - Copy a page-share link and a quote-share link; open each in a new incognito tab (logged out) — confirm both land on the correct page, auto-scrolled, and the quote link additionally highlights the shared sentence.
   - Check both light and dark mode for the highlight (`<mark>`) and popover styling.
   - Check a narrow/mobile viewport width — confirm the floating popover doesn't overflow the screen edge.
   - Confirm the existing book-level "Share Book" button (`ShareModal`) and the chat "Share Answer" button (`ShareChatModal`) still work exactly as before (regression check on the shared-utility refactor from Tasks 1-2).
