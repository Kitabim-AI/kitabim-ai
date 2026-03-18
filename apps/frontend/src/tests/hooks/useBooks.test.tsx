import { renderHook, act, waitFor } from '@testing-library/react';
import { useBooks } from '@/src/hooks/useBooks';
import { PersistenceService } from '@/src/services/persistenceService';
import { expect, test, vi, beforeEach } from 'vitest';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getGlobalLibrary: vi.fn(),
  }
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    isAuthenticated: false,
  })),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('useBooks fetches library data on refresh', async () => {
  const mockResponse = {
    books: [{ id: '1', title: 'T1', status: 'ready' }],
    total: 1,
    totalReady: 1
  };
  vi.mocked(PersistenceService.getGlobalLibrary).mockResolvedValue(mockResponse as any);

  const { result } = renderHook(() => useBooks('library', '', 10, 1));

  await waitFor(() => {
    expect(result.current.books).toHaveLength(1);
  });

  await act(async () => {
    result.current.refreshLibrary();
  });

  expect(result.current.totalBooks).toBe(1);
  expect(PersistenceService.getGlobalLibrary).toHaveBeenCalledTimes(2);
});

test('useBooks keeps uploadDate-desc as the default sort config', () => {
  vi.mocked(PersistenceService.getGlobalLibrary).mockResolvedValue({
    books: [],
    total: 0,
    totalReady: 0,
  } as any);

  const { result } = renderHook(() => useBooks('library', '', 10, 1));

  return waitFor(() => {
    expect(result.current.sortConfig).toEqual({
      key: 'uploadDate',
      direction: 'desc',
    });
  });
});

test('useBooks handles loadMoreShelf', async () => {
  const firstBatch = {
    books: Array.from({ length: 40 }, (_, i) => ({ id: `${i}`, title: `T${i}` })),
    total: 80,
    totalReady: 80,
  };
  const secondBatch = {
    books: Array.from({ length: 40 }, (_, i) => ({ id: `${i + 40}`, title: `T${i + 40}` })),
    total: 80,
    totalReady: 80,
  };

  vi.mocked(PersistenceService.getGlobalLibrary).mockImplementation((page: number) => {
    if (page === 1) return Promise.resolve(firstBatch as any);
    if (page === 2) return Promise.resolve(secondBatch as any);
    return Promise.resolve({ books: [], total: 80, totalReady: 80 } as any);
  });

  const { result } = renderHook(() => useBooks('library', '', 10, 1));

  await waitFor(() => {
    expect(result.current.books).toHaveLength(40);
  });

  await act(async () => {
    await result.current.loadMoreShelf();
  });

  expect(result.current.books).toHaveLength(80);
  expect(result.current.hasMoreShelf).toBe(false);
});
