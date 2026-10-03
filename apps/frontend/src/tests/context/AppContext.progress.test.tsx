import React from 'react';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { AppProvider, useAppContext } from '@/src/context/AppContext';
import { AuthProvider } from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { NotificationProvider } from '@/src/context/NotificationContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookById: vi.fn().mockResolvedValue(null),
    saveReadingProgress: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock('@/src/hooks/useBooks', () => ({
  useBooks: () => ({
    books: [], setBooks: vi.fn(), totalBooks: 0, totalReady: 0, sortedBooks: [],
    sortConfig: { key: 'title', direction: 'asc' }, refreshLibrary: vi.fn(),
    loadMoreShelf: vi.fn(), isLoading: false, isLoadingMoreShelf: false, hasMoreShelf: false,
  }),
}));

vi.mock('@/src/hooks/useChat', () => ({
  useChat: () => ({ setChatMessages: vi.fn(), selectedCharacterId: '', setSelectedCharacterId: vi.fn() }),
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

test('debounces reading-progress saves after currentPage settles', async () => {
  const { result } = renderHook(() => useAppContext(), { wrapper });

  act(() => {
    result.current.setSelectedBook({ id: 'book-1' } as any);
  });
  act(() => {
    result.current.setCurrentPage(5);
  });
  act(() => {
    result.current.setCurrentPage(6);
  });

  expect(PersistenceService.saveReadingProgress).not.toHaveBeenCalled();

  await act(async () => {
    vi.advanceTimersByTime(2100);
  });

  expect(PersistenceService.saveReadingProgress).toHaveBeenCalledTimes(1);
  expect(PersistenceService.saveReadingProgress).toHaveBeenCalledWith('book-1', 6);
});

test('does not save progress when no book is selected', async () => {
  renderHook(() => useAppContext(), { wrapper });

  await act(async () => {
    vi.advanceTimersByTime(3000);
  });

  expect(PersistenceService.saveReadingProgress).not.toHaveBeenCalled();
});
