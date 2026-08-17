import React from 'react';
import { AppProvider, useAppContext } from '@/src/context/AppContext';
import { AuthProvider } from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { NotificationProvider } from '@/src/context/NotificationContext';
import { act, renderHook, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookById: vi.fn(),
  },
}));

const i18nMockValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <NotificationProvider>
    <AuthProvider>
      <I18nContext.Provider value={i18nMockValue}>
        <AppProvider>{children}</AppProvider>
      </I18nContext.Provider>
    </AuthProvider>
  </NotificationProvider>
);

test('home search tab and query survive opening and closing the reader', () => {
  const { result } = renderHook(() => useAppContext(), { wrapper });

  act(() => {
    result.current.setHomeActiveTab('content');
    result.current.setHomeSearchText('tarikh');
  });
  expect(result.current.homeActiveTab).toBe('content');
  expect(result.current.homeSearchText).toBe('tarikh');

  // AppProvider stays mounted for the whole SPA session — only HomeView unmounts when
  // the reader opens and remounts when it closes — so the home search session must survive.
  act(() => {
    result.current.setView('reader');
  });
  act(() => {
    result.current.setView(result.current.previousView);
  });

  expect(result.current.view).toBe('home');
  expect(result.current.homeActiveTab).toBe('content');
  expect(result.current.homeSearchText).toBe('tarikh');
});

test('home search tab and query reset when explicitly navigating away from home', () => {
  const { result } = renderHook(() => useAppContext(), { wrapper });

  act(() => {
    result.current.setHomeActiveTab('content');
    result.current.setHomeSearchText('tarikh');
  });

  act(() => {
    result.current.setView('join-us');
  });

  expect(result.current.homeActiveTab).toBe('ask');
  expect(result.current.homeSearchText).toBe('');
});

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
