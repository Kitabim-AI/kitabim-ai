# AGENTS.md — Frontend

## Service Purpose
React 19 / Vite / TypeScript SPA. Provides the Uyghur Digital Library UI: book browsing, document reader, spell-check workflow, RAG chat, and admin panel. Consumes the backend API only — no AI keys or secrets in the browser.

## Stack
- React 19, TypeScript, Vite, Tailwind CSS
- Vitest + React Testing Library for tests
- i18n: custom `I18nContext` supporting English and Uyghur (`src/i18n/`, `src/locales/`)

## Structure
```
apps/frontend/src/
  App.tsx                        ← Root component and routing
  index.tsx                      ← React entry point
  config.ts                      ← Frontend configuration constants
  components/
    auth/                        ← AuthButton (login/logout)
    admin/
      AdminView.tsx              ← Admin dashboard shell
      AdminTabs.tsx              ← Tab navigation
      StatsPanel.tsx             ← Statistics display
      ProgressBar.tsx            ← Progress bars
      ActionMenu.tsx             ← Admin action menu
      TagEditor.tsx              ← Tag editor
      ContactSubmissionsPanel.tsx ← Contact submissions viewer
      config/SystemConfigPanel.tsx ← System config editor
      users/UserManagementPanel.tsx ← User administration
      rules/AutoCorrectRulesPanel.tsx ← Auto-correct rules
      dictionary/DictionaryManagementPanel.tsx ← Dictionary editor
    layout/
      Navbar.tsx                 ← Top navigation bar
      Shell.tsx                  ← App shell/layout wrapper
    library/
      LibraryView.tsx            ← Book grid / main library
      HomeView.tsx               ← Landing/home page
      BookCard.tsx               ← Individual book card
      SearchOverlay.tsx          ← Search UI overlay
    reader/
      ReaderView.tsx             ← Book reader interface
      PageItem.tsx               ← Single page display
      VirtualScrollReader.tsx    ← Virtualized page scrolling
    spell-check/
      SpellCheckView.tsx         ← Spell-check page
      SpellCheckPanel.tsx        ← Editor panel
      ReviewPanel.tsx            ← Correction review panel
      HighlightedText.tsx        ← Error highlighting
    chat/
      ChatInterface.tsx          ← RAG chat input/output
      ReferenceModal.tsx         ← Source reference modal
    common/
      Modal.tsx                  ← Modal dialog
      MarkdownContent.tsx        ← Markdown renderer
      NotificationContainer.tsx  ← Toast notifications
      UserAvatar.tsx             ← User avatar
      LanguageSwitcher.tsx       ← EN/UG toggle
      ProverbDisplay.tsx         ← Proverb widget
    pages/
      JoinUsView.tsx             ← Join/contribution page
    ui/
      GlassPanel.tsx             ← Glass-morphism panel component
  hooks/
    useAuth.tsx                  ← Authentication state & actions
    useChat.ts                   ← RAG chat state & API calls
    useBooks.ts                  ← Books data fetching
    useBookActions.ts            ← Book CRUD actions
    useSpellCheck.ts             ← Spell-check state & workflow
    usePendingCorrections.ts     ← Pending correction tracking
  services/
    authService.ts               ← Auth API client
    userService.ts               ← User API client
    pdfService.ts                ← PDF handling
    contactService.ts            ← Contact form API
    geminiService.ts             ← Gemini AI integration (proxied via backend)
    persistenceService.ts        ← LocalStorage management
  context/
    AppContext.tsx               ← Global app state provider
    NotificationContext.tsx      ← Toast notification provider
  i18n/
    i18n.ts                      ← i18n setup
    I18nContext.tsx              ← i18n context provider
  locales/
    en.json                      ← English translations
    ug.json                      ← Uyghur translations
  constants/
    characters.ts                ← Uyghur character definitions
    milestones.ts                ← Progress milestone definitions
  tests/                         ← Vitest + RTL tests (mirrors src/ structure)
```

## Run (Dev — standalone)
```bash
npm install
npm run dev   # Vite dev server proxies /api → backend
```

## Notes
- Vite dev server proxies `/api` to the backend (configured in `vite.config.ts`).
- Do not add AI keys or other secrets to client code — all AI calls go through the backend.
- For final verification, always use Docker Compose, not the standalone dev server.
- Local dev: `./deploy/local/rebuild-and-restart.sh frontend`

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in `docs/<branch-name>/` (e.g. `docs/main/`). Run `git branch --show-current` for the branch name.
