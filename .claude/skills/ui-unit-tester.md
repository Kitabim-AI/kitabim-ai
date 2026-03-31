# UI Unit Tester Skill — Kitabim AI Frontend

You are acting as a frontend test engineer for the kitabim-ai React/TypeScript app. Your job is to write comprehensive, reliable unit tests for React components and hooks — covering happy paths, edge cases, user interactions, and error states.

## Testing Stack

| Tool | Purpose |
|------|---------|
| Vitest 4 | Test runner and assertion library |
| @testing-library/react 16 | Component/hook rendering |
| @testing-library/jest-dom 6 | DOM matchers (`toBeInTheDocument`, etc.) |
| jsdom 27 | DOM environment |
| vitest coverage-v8 | Coverage reporting |

**Run tests:**
```bash
cd apps/frontend
npm test             # watch mode
npm run test:coverage  # with coverage report
```

---

## File Placement

Mirror the source tree under `src/tests/`:

```
src/tests/
  test-utils.tsx                    # renderWithProviders — all provider wrappers
  components/
    library/BookCard.test.tsx       # mirrors src/components/library/BookCard.tsx
    chat/ChatInterface.test.tsx
    reader/ReaderView.test.tsx
    ...
  hooks/
    useChat.test.tsx                # mirrors src/hooks/useChat.ts
    useBooks.test.tsx
    ...
```

**Naming:** `<ComponentOrHookName>.test.tsx`

---

## Core Rule: Always Use `renderWithProviders`

Never use `render` from `@testing-library/react` directly. Always use the wrapper from `test-utils.tsx`:

```ts
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { expect, test, vi, beforeEach } from 'vitest';
import React from 'react';
```

The wrapper provides: `NotificationProvider` → `AuthProvider` → `I18nContext` (mocked) → `AppProvider`.

---

## i18n Assertions

The `t()` mock returns the key itself. **Always assert against translation keys, not translated strings.**

```ts
// ✅ Correct — assert against the key
expect(screen.getByText('common.save')).toBeInTheDocument();

// ❌ Wrong — translated string not available in tests
expect(screen.getByText('Save')).toBeInTheDocument();

// ✅ With params — params are interpolated into the key
// t('book.pagesCount', { count: 5 }) → 'book.pagesCount'  (key returned as-is)
// But if the key contains {{count}}, the mock replaces it:
// t('book.pages {{count}}', { count: 5 }) → 'book.pages 5'
```

---

## Component Test Template

```tsx
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { MyComponent } from '@/src/components/path/MyComponent';
import { expect, test, vi, beforeEach, describe } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';

// --- Mock external services (not providers — those come from renderWithProviders) ---
vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    someMethod: vi.fn(),
  },
}));

// --- Shared test data ---
const mockBook: Book = {
  id: '1',
  title: 'Test Book',
  author: 'Test Author',
  totalPages: 100,
  pages: [],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'hash123',
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('MyComponent', () => {
  test('renders correctly with required props', () => {
    render(<MyComponent book={mockBook} />);
    expect(screen.getAllByText('Test Book').length).toBeGreaterThan(0);
  });

  test('handles user click', () => {
    const onClick = vi.fn();
    render(<MyComponent book={mockBook} onClick={onClick} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledWith(mockBook);
  });

  test('shows loading state', () => {
    render(<MyComponent book={mockBook} isLoading />);
    // Assert against i18n key
    expect(screen.getByText('common.loading')).toBeInTheDocument();
  });

  test('shows error state', async () => {
    render(<MyComponent book={mockBook} />);
    // Trigger async action that fails
    fireEvent.click(screen.getByRole('button', { name: /submit/i }));
    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
```

---

## Hook Test Template

Use `renderHook` from `@testing-library/react`. No `renderWithProviders` needed for hooks unless they consume context.

```ts
import { renderHook, act, waitFor } from '@testing-library/react';
import { useMyHook } from '@/src/hooks/useMyHook';
import { someService } from '@/src/services/someService';
import { expect, test, vi, beforeEach, describe } from 'vitest';

vi.mock('@/src/services/someService', () => ({
  someService: {
    fetchData: vi.fn(),
  },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    isAuthenticated: true,
    user: { id: 'u1', role: 'admin' },
  })),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useMyHook', () => {
  test('initial state is correct', () => {
    const { result } = renderHook(() => useMyHook('id1'));
    expect(result.current.data).toBeNull();
    expect(result.current.isLoading).toBe(false);
  });

  test('fetches data on mount', async () => {
    vi.mocked(someService.fetchData).mockResolvedValue({ value: 42 });

    const { result } = renderHook(() => useMyHook('id1'));

    await waitFor(() => {
      expect(result.current.data).toEqual({ value: 42 });
    });
  });

  test('handles action via act()', async () => {
    const { result } = renderHook(() => useMyHook('id1'));

    act(() => {
      result.current.setInput('hello');
    });

    await act(async () => {
      await result.current.submit();
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });
  });

  test('handles error state', async () => {
    vi.mocked(someService.fetchData).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useMyHook('id1'));

    await waitFor(() => {
      expect(result.current.error).toBe('Network error');
    });
  });
});
```

---

## Mocking Patterns

### Mock a service module
```ts
vi.mock('@/src/services/geminiService', () => ({
  chatWithBookStream: vi.fn(),
  getChatUsage: vi.fn(),
}));

// In test:
vi.mocked(getChatUsage).mockResolvedValue({ usage: 0, limit: 10, hasReachedLimit: false });
```

### Mock a class/static method (PersistenceService pattern)
```ts
import * as persistenceService from '@/src/services/persistenceService';

vi.spyOn(persistenceService.PersistenceService, 'getGlobalLibrary')
  .mockResolvedValue({ books: [], total: 0, page: 1, pageSize: 10, totalReady: 0 });
```

### Mock streaming (async generator pattern used in chatWithBookStream)
```ts
vi.mocked(chatWithBookStream).mockImplementation(
  async (_question, _bookId, _page, _history, onChunk, onComplete, onError) => {
    onChunk('First ');
    onChunk('chunk');
    onComplete();
  }
);
```

### Mock auth state
```ts
vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    isAuthenticated: true,
    user: { id: 'user1', role: 'admin' },
    isLoading: false,
  })),
  useIsAdmin: vi.fn(() => true),
  useIsEditor: vi.fn(() => true),
  useCanRead: vi.fn(() => true),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
```

---

## What to Test

### Components — test these:
- **Renders key content** — title, author, page count visible
- **Conditional rendering** — shows/hides elements based on props (loading, error, empty)
- **User interactions** — click, input change, form submit → correct handler called with correct args
- **State transitions** — UI updates after async action completes
- **Edge cases** — missing optional props, empty arrays, boundary values

### Hooks — test these:
- **Initial state** — correct defaults
- **Data fetching** — calls service with right args, sets data on success
- **Error handling** — sets error state on rejection, doesn't crash
- **Actions** — `act()` + `waitFor()` pattern for state-setting actions
- **Cleanup** — no state updates after unmount (use `{ unmount }` from renderHook)

### Do NOT test:
- Tailwind class names or CSS styles
- Internal implementation details (private state variable values)
- Third-party library internals
- Pure TypeScript types/interfaces

---

## Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| `screen.getByText('Save')` — translated string | `screen.getByText('common.save')` — i18n key |
| `render()` from testing-library directly | `renderWithProviders()` from test-utils |
| Forgetting `await act(async () => ...)` for async actions | Wrap async hook actions in `await act(async () => ...)` |
| Asserting on text that appears multiple times | Use `screen.getAllByText(...).length` or `getAllByText(...)[0]` |
| Not calling `vi.clearAllMocks()` in `beforeEach` | Always add `beforeEach(() => { vi.clearAllMocks(); })` |
| Importing `Book` from a relative path | Import from `@shared/types` |
| Mocking the entire `AppContext` | Use `renderWithProviders` — it provides a real AppProvider |

---

## Workflow

1. **Read the component or hook first** — understand its props, state, and service calls.
2. **Identify what to mock** — external services, auth state. Do NOT mock React context providers.
3. **Write the test file** in `src/tests/` mirroring the source path.
4. **Cover:** render, interaction, loading, error, and edge cases.
5. **Run:** `npm test` in `apps/frontend/` to confirm all tests pass.
6. **Check coverage:** `npm run test:coverage` if adding tests for an uncovered area.
