import { VirtualScrollReader } from '@/src/components/reader/VirtualScrollReader';
import * as AuthModule from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookPages: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('@/src/components/reader/PageItem', () => ({
  PageItem: ({ bookId, bookTitle, highlightQuote }: any) => (
    <div data-testid="page-item">
      Page Content
      <div data-testid="share-props">{bookId || ''}|{bookTitle || ''}|{highlightQuote || ''}</div>
    </div>
  ),
}));

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderReader = () =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <VirtualScrollReader bookId="book-1" totalPages={5} fontSize={16} scrollParentRef={{ current: document.createElement('div') }} />
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
});

test('disables selection and prevents copy for guest users in reader', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: false,
    user: null,
  } as any);

  renderReader();

  const readerContainer = screen.getByTestId('reader-container');
  expect(readerContainer).toHaveClass('select-none');

  const copyEvent = new Event('copy', { bubbles: true, cancelable: true });
  const preventCopySpy = vi.spyOn(copyEvent, 'preventDefault');
  fireEvent(readerContainer, copyEvent);
  expect(preventCopySpy).toHaveBeenCalled();

  const contextMenuEvent = new Event('contextmenu', { bubbles: true, cancelable: true });
  const preventContextMenuSpy = vi.spyOn(contextMenuEvent, 'preventDefault');
  fireEvent(readerContainer, contextMenuEvent);
  expect(preventContextMenuSpy).toHaveBeenCalled();
});

test('allows selection and copying for registered/authenticated users in reader', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { id: 'user-1', role: 'reader' },
  } as any);

  renderReader();

  const readerContainer = screen.getByTestId('reader-container');
  expect(readerContainer).not.toHaveClass('select-none');

  const copyEvent = new Event('copy', { bubbles: true, cancelable: true });
  const preventCopySpy = vi.spyOn(copyEvent, 'preventDefault');
  fireEvent(readerContainer, copyEvent);
  expect(preventCopySpy).not.toHaveBeenCalled();

  const contextMenuEvent = new Event('contextmenu', { bubbles: true, cancelable: true });
  const preventContextMenuSpy = vi.spyOn(contextMenuEvent, 'preventDefault');
  fireEvent(readerContainer, contextMenuEvent);
  expect(preventContextMenuSpy).not.toHaveBeenCalled();
});

test('observes every rendered page for resize, so async content loads cannot silently shift scroll position', () => {
  const observe = vi.fn();
  const realResizeObserver = global.ResizeObserver;
  vi.stubGlobal('ResizeObserver', class {
    observe = observe;
    unobserve = vi.fn();
    disconnect = vi.fn();
  });

  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { id: 'user-1', role: 'reader' },
  } as any);

  renderReader();

  const observedPages = observe.mock.calls
    .map(([el]) => el.getAttribute('data-page-number'))
    .filter(Boolean);
  expect(new Set(observedPages)).toEqual(new Set(['1', '2', '3', '4', '5']));

  vi.stubGlobal('ResizeObserver', realResizeObserver);
});

test('re-observes all pages after exiting edit mode so scrolling down loads subsequent pages', () => {
  const observe = vi.fn();
  const realIntersectionObserver = global.IntersectionObserver;
  vi.stubGlobal('IntersectionObserver', class {
    observe = observe;
    unobserve = vi.fn();
    disconnect = vi.fn();
  });

  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { id: 'user-1', role: 'reader' },
  } as any);

  const { rerender } = render(
    <I18nContext.Provider value={i18nValue}>
      <VirtualScrollReader bookId="book-1" totalPages={5} fontSize={16} editingPageNum={2} scrollParentRef={{ current: document.createElement('div') }} />
    </I18nContext.Provider>
  );

  // During edit mode for page 2, only page 2 is rendered & observed
  observe.mockClear();

  // Exit edit mode
  rerender(
    <I18nContext.Provider value={i18nValue}>
      <VirtualScrollReader bookId="book-1" totalPages={5} fontSize={16} editingPageNum={null} scrollParentRef={{ current: document.createElement('div') }} />
    </I18nContext.Provider>
  );

  const reobservedPages = observe.mock.calls
    .map(([el]) => el?.getAttribute?.('data-page-number'))
    .filter(Boolean);

  expect(new Set(reobservedPages)).toEqual(new Set(['1', '2', '3', '4', '5']));

  vi.stubGlobal('IntersectionObserver', realIntersectionObserver);
});

test('passes bookId/bookTitle to PageItem and only gates highlightQuote to the current-center page', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { id: 'user-1', role: 'reader' },
  } as any);

  // On initial mount, VirtualScrollReader's "reset pages cache when bookId changes"
  // effect (keyed on [bookId]) runs AFTER the "sync selectedBookPages into cache"
  // effect and wipes out what it just set, since a fresh bookId counts as a change
  // on mount too. Mounting without selectedBookPages first and rerendering with it
  // avoids that — bookId is unchanged across the rerender, so only the sync effect
  // fires the second time.
  const { rerender } = render(
    <I18nContext.Provider value={i18nValue}>
      <VirtualScrollReader
        bookId="book-1"
        totalPages={2}
        fontSize={16}
        scrollParentRef={{ current: document.createElement('div') }}
        initialPage={1}
        bookTitle="My Book"
        pendingQuoteHighlight="a quote"
      />
    </I18nContext.Provider>
  );

  rerender(
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

