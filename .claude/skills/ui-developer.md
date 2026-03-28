# UI Developer Skill — Kitabim AI Frontend

You are acting as a frontend developer for the kitabim-ai React/TypeScript app. Your job is to implement, wire up, and test frontend features correctly — hooks, services, state, context, routing, and component logic.

## Stack

| Tool | Version / Notes |
|------|----------------|
| React | 19 — use `React.FC`, no `React.memo` unless measured |
| TypeScript | ~5.8 strict |
| Vite | 6 — bundler and dev server |
| Tailwind CSS | 3.4 — utility classes only, no separate CSS files |
| Testing | Vitest + @testing-library/react |
| Icons | lucide-react ^0.563 |
| HTTP | `authFetch` / `getAuthHeaders` from `services/authService` |

No router library — the app uses `window.history.pushState` with a hand-rolled view system in `AppContext`.

---

## Directory Layout

```
apps/frontend/src/
  App.tsx                    # Root: AppProvider > AppContent (view switch)
  context/
    AppContext.tsx            # Global state — view, books, chat, modal, auth guards
    NotificationContext.tsx   # Toast notifications
  hooks/
    useAuth.tsx              # AuthProvider + useAuth, useIsAdmin, useIsEditor, useCanRead
    useBooks.ts              # Book list, pagination, sorting
    useChat.ts               # Chat messages, streaming, usage
    useBookActions.ts        # Upload, delete, open, process actions
  services/
    persistenceService.ts    # REST API calls — books, pages, summaries (uses authFetch)
    authService.ts           # Token mgmt, OAuth, authFetch, getAuthHeaders
    geminiService.ts         # Gemini AI integration
    userService.ts           # User CRUD
    contactService.ts        # Contact form
    pdfService.ts            # PDF parsing
  i18n/
    I18nContext.tsx          # useI18n() — t(key, params?)
    i18n.ts                  # Language type, translations loader
    locales/ug.json          # Uyghur translations (default)
    locales/en.json          # English translations
  components/
    layout/Shell.tsx         # App shell: Navbar + main scroll area + footer + overlays
    layout/Navbar.tsx        # Top nav bar
    ui/GlassPanel.tsx        # Reusable glass-morphism card wrapper
    common/Modal.tsx         # Confirm/alert modal (driven by AppContext modal state)
    common/NotificationContainer.tsx
    library/                 # Home, LibraryView, BookCard, SearchOverlay
    reader/                  # ReaderView, VirtualScrollReader, PageItem
    chat/                    # ChatInterface, ReferenceModal
    admin/                   # AdminView, AdminTabs, StatsPanel, sub-panels
    spell-check/             # SpellCheckView, SpellCheckPanel, ReviewPanel, HighlightedText
    pages/                   # JoinUsView
    auth/                    # AuthButton
  tests/
    test-utils.tsx           # renderWithProviders — wraps with all providers
    components/              # Co-located component tests
    hooks/                   # Hook tests
```

---

## State Architecture

### Global state: `useAppContext()`
The single source of truth. Never replicate state that already lives here.

Key fields:
```ts
view         // current page: 'home'|'library'|'admin'|'reader'|'global-chat'|'join-us'|'spell-check'
setView      // navigate (pushes to history unless updateHistory=false)
selectedBook // Book | null
books        // current page of books
refreshLibrary()
modal        // { isOpen, title, message, type, onConfirm, destructive, isLoading }
setModal     // open the global confirm/alert modal
bookActions  // upload, delete, open, process
chat         // messages, streaming state, chatInput, send
fontSize     // reader font size
isReaderFullscreen
activeTab    // admin sub-tab
```

### Auth: `useAuth()`
Lives inside `AuthProvider` (wraps the whole app in `test-utils.tsx`). Exposes:
```ts
user, isAuthenticated, isLoading
loginWithGoogle, loginWithFacebook, loginWithTwitter, logout, refreshUser
```
Role guards (import from `hooks/useAuth`):
```ts
useIsAdmin()   // role === 'admin'
useIsEditor()  // role === 'admin' | 'editor'
useCanRead()   // any authenticated role
```

### Notifications
```ts
import { useNotification } from '../../context/NotificationContext';
const { showNotification } = useNotification();
showNotification('Message text', 'success' | 'error' | 'info');
```

---

## API / Service Layer

All HTTP calls go through `authFetch` — it auto-attaches the bearer token:
```ts
import { authFetch, getAuthHeaders } from '../services/authService';

// JSON GET
const res = await authFetch('/api/books');
if (!res.ok) throw new Error(`${res.status}`);
const data = await res.json();

// JSON POST
const res = await authFetch('/api/books', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(payload),
});
```

Use `getAuthHeaders()` for FormData (file uploads) where you set the body manually.

API base path: `/api` (proxied by Vite to `http://localhost:30800` in dev).

---

## i18n

Always use `t()` for user-visible strings. Never hardcode display text.

```ts
import { useI18n } from '../../i18n/I18nContext';
const { t } = useI18n();

// Simple
t('common.save')

// With params
t('book.pagesCount', { count: 42 })   // template: "{{count}} pages"
```

To add new strings: add keys to both `locales/ug.json` AND `locales/en.json`.

---

## Routing / Navigation

No react-router. Navigation is `setView(...)` from `useAppContext()`.

```ts
setView('library')            // navigate, push history
setView('reader', false)      // navigate, skip history entry
```

URL ↔ view mapping (defined in `AppContext.tsx`):
```
/           → home
/library    → library
/admin      → admin (tab: books)
/admin/users → admin (tab: users)
/chat       → global-chat
/spell-check → spell-check
/reader     → reader (no direct URL entry, opened via book click)
/join-us    → join-us
```

---

## Writing Hooks

```ts
import { useState, useEffect, useCallback } from 'react';
import { authFetch } from '../services/authService';

interface UseMyFeatureReturn {
  data: MyType | null;
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useMyFeature(id: string): UseMyFeatureReturn {
  const [data, setData] = useState<MyType | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await authFetch(`/api/my-endpoint/${id}`);
      if (!res.ok) throw new Error(`${res.status}`);
      setData(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  return { data, isLoading, error, refresh };
}
```

---

## Testing

**Test runner:** `vitest` — run with `npm test` inside `apps/frontend/`.

**Always use `renderWithProviders`** from `tests/test-utils.tsx` — it wraps with `NotificationProvider`, `AuthProvider`, `I18nContext` (mocked), and `AppProvider`:

```ts
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { expect, test, vi } from 'vitest';
import React from 'react';

test('renders correctly', () => {
  render(<MyComponent prop={value} />);
  expect(screen.getByText('some text')).toBeInTheDocument();
});

test('handles async action', async () => {
  render(<MyComponent />);
  fireEvent.click(screen.getByRole('button'));
  await waitFor(() => expect(screen.getByText('done')).toBeInTheDocument());
});
```

**Mocking services:**
```ts
import * as persistenceService from '@/src/services/persistenceService';
vi.spyOn(persistenceService.PersistenceService, 'getGlobalLibrary')
  .mockResolvedValue({ books: [], total: 0, page: 1, pageSize: 10, totalReady: 0 });
```

The i18n mock in `renderWithProviders` returns the key itself (e.g. `t('common.save')` → `'common.save'`), so test against keys, not translated strings.

---

## Shared Types

Import from `@shared/types` (workspace package, not a relative path):
```ts
import { Book, Page } from '@shared/types';
```

---

## Workflow

1. **Read the relevant hook/service/context before writing** — don't duplicate state or API calls that already exist.
2. **Wire to existing context first** — check if `useAppContext()` already has what you need before adding new state.
3. **Keep services pure** — service functions call `authFetch` and return data/throw; they have no React state.
4. **Keep hooks focused** — one concern per hook. Extract shared async logic into the service layer.
5. **Test all new hooks and non-trivial components** — place tests in `tests/hooks/` or `tests/components/` to mirror `src/`.
6. **Never hardcode display text** — always add to both locale files and use `t()`.
7. **Protect admin/editor views** — check `useIsEditor()` before rendering sensitive UI, mirroring the guard in `App.tsx`.
