# SEO & GEO for Kitabim.AI — Design (DRAFT, in progress)

**Status:** Design under discussion, not yet approved. Picking back up later.

## Goal

Improve discoverability of Kitabim.AI both for traditional search engines (SEO) and
AI answer engines like ChatGPT, Perplexity, and Google AI Overviews (GEO — Generative
Engine Optimization), so that:
1. People find Kitabim.AI via organic search / AI assistants when looking for the
   Uyghur books, authors, proverbs, and dictionary content it hosts.
2. AI engines cite Kitabim.AI as a source when answering questions about that content.

## Decisions made so far

- **App shape:** Public book/text library + AI chat (public pages are the SEO surface).
- **Primary driver:** Both traffic growth and being an AI-cited source, roughly equally.
- **Routing:** Introduce real per-entity URLs (React Router), replacing the current
  client-side `view` state navigation. This is a prerequisite for any real SEO — crawlers
  need distinct, linkable URLs, not one URL for the whole app.
- **Content priority (in order asked, all in scope):** Books & pages, Dictionary entries,
  Authors, Proverbs.
- **Rendering strategy:** Server-rendered content pages for bots — extend the existing
  `share_router.py` bot-detection pattern into full dynamic rendering (not static
  build-time prerendering, not a full SSR framework rewrite).
- **Language:** Uyghur only — content and metadata (titles, descriptions, structured
  data) stay in Uyghur. No bilingual metadata layer for now.
- **Phasing:** Break into 3 phases; this doc covers Phase 1 in detail, Phases 2-3 as
  rough scope for later specs.

## Current-state findings (as of 2026-07-16)

- **Frontend is a pure client-side SPA** — no SSR/SSG. `apps/frontend/index.html` has a
  single static `<title>`, no meta description/OG/Twitter tags, no canonical link. No
  `react-helmet`/similar. No `react-router-dom` — navigation is internal `view` state in
  `App.tsx`, driven by `apps/frontend/src/context/AppContext.tsx`.
- **`AppContext.tsx` already has a hand-rolled, partial URL sync**, not a real router:
  - `parsePath()` (`AppContext.tsx:79-83`) parses `/books/{id}` on initial load
    ("Deep link from Facebook share") into `view`/`bookId` state.
  - `pushState` is called from `setView` (`:106`) and `setActiveTab` (`:133`).
  - Critically, after opening a shared book deep link, it calls
    `window.history.replaceState({}, '', '/')` (`:171`) — **wiping the URL back to `/`**.
    This is the root cause of there being no persistent, bookmarkable, crawlable URLs
    today: the URL is treated as a one-time entry signal, not as durable app state.
  - `package.json` confirms: no `react-router-dom`, no `react-helmet-async`. React 19.2.3.
- **No `robots.txt` or `sitemap.xml`** anywhere in `apps/frontend/public/`.
- **No JSON-LD / structured data** anywhere in the frontend.
- **Existing proto-GEO asset: `services/backend/api/endpoints/share_router.py`** —
  `GET /api/share/book/{book_id}` and `GET /api/share/qa`. Detects scraper UAs
  (`_SCRAPER_AGENTS`, `share_router.py:20-31`: Facebook, Twitter, LinkedIn, WhatsApp,
  Slack, Telegram, Discord, Googlebot, Applebot — **no AI-crawler UAs**), and for
  matched bots serves a minimal HTML page with `og:*`/`twitter:*` tags and an **empty
  `<body></body>`** — no real indexable content. Non-bot requests get a 302 redirect to
  the SPA deep link (which itself gets wiped per above).
- **Nginx (`deploy/gcp/nginx/conf.d/kitabim.conf`)**: single domain `kitabim.ai`,
  `location ^~ /api/` proxies to backend (`:42`), everything else (including all HTML)
  falls through to the frontend container as SPA (`:79-87`). This confirms a clean
  extension point: add a `map $http_user_agent $is_bot` block and route matched bot
  requests for content paths to new backend render endpoints, leaving human traffic on
  the existing SPA path untouched.
- No sitemap/robots-serving logic, no SEO/GEO docs anywhere in `docs/`. This is
  greenfield apart from the `share_router.py` pattern.

## Phase 1 — Foundation: Routing + Server Rendering (this phase, detailed)

### Architecture
Replace the hand-rolled `pushState`/`parsePath` logic in `AppContext.tsx` with React
Router, mapping real URLs to the existing view state instead of discarding them.
Extend `deploy/gcp/nginx/conf.d/kitabim.conf` with bot-aware routing so known bots
requesting content URLs get backend-rendered HTML instead of the SPA shell; humans get
the SPA exactly as today. This generalizes `share_router.py`'s bot-detection pattern
rather than replacing it.

### Routes in scope
- `/books/:bookId` and `/books/:bookId/pages/:pageNumber` (page-level, since GEO
  benefits from citable per-passage URLs)
- `/proverbs/:proverbId`
- `/authors/:authorId`
- `/dictionary/:word`
- Everything else (chat, admin, quran, spell-check) stays on today's internal-state
  navigation — out of scope, not blocked from a later phase.

### URL identifiers
IDs, not slugs, for Phase 1 (e.g. `/books/abc123`, not a title slug). Slugs are better
for SEO but need a DB migration (new `slug` columns) plus redirect handling — real scope
creep for a foundation phase. Proposal: defer slugs to Phase 2/3 as an explicit
enhancement, with 301 redirects from ID URLs preserving any link equity already earned.
**Flagged as an open call — revisit before implementation.**

### Backend rendering
Generalize `_SCRAPER_AGENTS` into a shared bot-detection util and expand the list to
include actual AI crawlers: GPTBot, ChatGPT-User, ClaudeBot, PerplexityBot,
Google-Extended, CCBot, Bytespider, Amazonbot — today's list only covers social/search
crawlers, a real gap for GEO. New render endpoints per content type return real HTML
body content (actual book excerpt/description, dictionary definition, proverb text,
author bio + booklist) plus OG/Twitter tags — not the empty `<body></body>` the current
share endpoints produce. Reuse existing repositories; no new data layer.

### Error handling
Missing/private/deleted content → real 404 HTML (not a crash or silent empty page),
mirroring the existing try/except pattern in `share_router.py`.

### Testing
- Backend: unit tests for the bot-detection util (incl. new AI-bot list) and each
  render endpoint (200 w/ real content assertions, 404 on missing/private content).
- Frontend: routing tests confirming route→view mapping matches today's deep-link
  behavior.
- Manual: `curl -A "GPTBot/1.0"` against a local instance to confirm real HTML is
  returned, before calling this done.

## Phase 2 (rough scope, not yet designed in detail)
- `sitemap.xml` generation endpoint (covering the 4 content types)
- `robots.txt` with explicit crawler rules, including AI bots
- JSON-LD structured data: `Book`, `DefinedTerm` (dictionary), `Person` (authors),
  `Quotation` (proverbs)
- Revisit slug-based URLs (see open call above) if desired at this point

## Phase 3 (rough scope, not yet designed in detail)
- `llms.txt`
- Citation-friendly content structuring (clear Q&A blocks, definition formatting)
- Internal linking, canonical URLs, hreflang (if ever needed)

## Open items to resolve before writing the Phase 1 implementation plan
1. Slug vs. ID URLs (see above) — confirm or override the ID-first proposal.
2. Exact list of AI-crawler user agent strings to whitelist (draft list above, needs
   verification against current bot UA strings).
3. Whether `/books/:bookId/pages/:pageNumber` is truly needed in Phase 1 or can wait —
   confirm page-level citability is worth the added route/render surface now vs. later.
4. Confirm which of `/api-designer`, `/database-designer`, `/ui-designer`,
   `/infra-developer` skills to invoke for the actual Phase 1 implementation plan, since
   it touches backend endpoints, frontend routing, and nginx config.
