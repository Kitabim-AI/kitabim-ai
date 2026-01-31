import { renderHook, act } from '@testing-library/react';
import { useBooks } from '../hooks/useBooks';
import { PersistenceService } from '../services/persistenceService';
import { expect, test, vi, beforeEach } from 'vitest';

vi.mock('../services/persistenceService', () => ({
  PersistenceService: {
    getGlobalLibrary: vi.fn()
  }
}));

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

test('useBooks fetches library data on refresh', async () => {
  const mockResponse = {
    books: [{ id: '1', title: 'T1', status: 'ready' }],
    total: 1,
    totalReady: 1
  };
  (PersistenceService.getGlobalLibrary as any).mockResolvedValue(mockResponse);

  const { result } = renderHook(() => useBooks('library', '', 10, 1));

  await act(async () => {
    await result.current.refreshLibrary();
  });

  expect(result.current.books).toHaveLength(1);
  expect(result.current.totalBooks).toBe(1);
  expect(PersistenceService.getGlobalLibrary).toHaveBeenCalled();
});

test('useBooks handles sorting', () => {
  const { result } = renderHook(() => useBooks('admin', '', 10, 1));

  act(() => {
    result.current.toggleSort('title');
  });

  expect(result.current.sortConfig.key).toBe('title');
  expect(sessionStorage.getItem('kitabim_sort_config')).toContain('title');

  act(() => {
    result.current.toggleSort('title');
  });
  expect(result.current.sortConfig.direction).toBe('asc');
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

  (PersistenceService.getGlobalLibrary as any)
    .mockResolvedValueOnce(firstBatch)
    .mockResolvedValueOnce(secondBatch);

  const { result } = renderHook(() => useBooks('library', '', 10, 1));

  await act(async () => {
    await result.current.refreshLibrary();
  });

  expect(result.current.books).toHaveLength(12);

  await act(async () => {
    await result.current.loadMoreShelf();
  });

  expect(result.current.books).toHaveLength(24);
  expect(result.current.hasMoreShelf).toBe(false);
});
