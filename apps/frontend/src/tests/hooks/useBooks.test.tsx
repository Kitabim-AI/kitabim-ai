import { renderHook, act } from '@testing-library/react';
import { useBooks } from '@/src/hooks/useBooks';
import { PersistenceService } from '@/src/services/persistenceService';
import { expect, test, vi, beforeEach } from 'vitest';
import React from 'react';
import { AuthProvider } from '@/src/hooks/useAuth';
import { AppProvider } from '@/src/context/AppContext';
import { NotificationProvider } from '@/src/context/NotificationContext';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getGlobalLibrary: vi.fn(),
    getRandomProverb: vi.fn().mockResolvedValue({ text: 'Test Proverb', author: 'Author' })
  }
}));

const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <NotificationProvider>
    <AuthProvider>
      <AppProvider>
        {children}
      </AppProvider>
    </AuthProvider>
  </NotificationProvider>
);

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  (PersistenceService.getRandomProverb as any).mockResolvedValue({ text: 'Mock Proverb', author: 'Author' });
});

test('useBooks fetches library data on refresh', async () => {
  const mockResponse = {
    books: [{ id: '1', title: 'T1', status: 'ready' }],
    total: 1,
    totalReady: 1
  };
  (PersistenceService.getGlobalLibrary as any).mockResolvedValue(mockResponse);

  const { result } = renderHook(() => useBooks('library', '', 10, 1), { wrapper: Wrapper });

  // Initial call from useEffect will consume one mock or the default mockResolvedValue
  // Wait for loading to finish
  await act(async () => {
    // Wait for the effect
  });

  await act(async () => {
    await result.current.refreshLibrary();
  });

  expect(result.current.books).toHaveLength(1);
  expect(result.current.totalBooks).toBe(1);
  expect(PersistenceService.getGlobalLibrary).toHaveBeenCalled();
});

test.skip('useBooks handles sorting', () => {
  // Skipping as useBooks no longer supports toggleSort
});

test('useBooks handles loadMoreShelf', async () => {
  const firstBatch = {
    books: Array(12).fill(0).map((_, i) => ({ id: `${i}`, title: `T${i}` })),
    total: 24,
    totalReady: 24
  };
  const secondBatch = {
    books: Array(12).fill(0).map((_, i) => ({ id: `${i + 12}`, title: `T${i + 12}` })),
    total: 24,
    totalReady: 24
  };

  (PersistenceService.getGlobalLibrary as any).mockImplementation((page: number) => {
    if (page === 1) return Promise.resolve(firstBatch);
    if (page === 2) return Promise.resolve(secondBatch);
    return Promise.resolve({ books: [], total: 24, totalReady: 24 });
  });

  const { result } = renderHook(() => useBooks('library', '', 10, 1), { wrapper: Wrapper });

  // Wait for initial load
  await act(async () => {
    // useEffect load
  });

  expect(result.current.books).toHaveLength(12);

  await act(async () => {
    await result.current.loadMoreShelf();
  });

  expect(result.current.books).toHaveLength(24);
  expect(result.current.hasMoreShelf).toBe(false);
});
