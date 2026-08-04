import { useContentSearch } from '@/src/hooks/useContentSearch';
import { SearchTabsService } from '@/src/services/searchTabsService';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/searchTabsService', () => ({
  SearchTabsService: {
    searchBookContent: vi.fn(),
  },
}));

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

test('does not fetch below the 2-character minimum', () => {
  renderHook(() => useContentSearch('a', 40));

  act(() => {
    vi.advanceTimersByTime(500);
  });

  expect(SearchTabsService.searchBookContent).not.toHaveBeenCalled();
});

test('fetches page 1 for a valid query and exposes hasMore based on total', async () => {
  vi.mocked(SearchTabsService.searchBookContent).mockResolvedValue({
    hits: [{ id: '1', bookId: 'b1', bookTitle: 'T1', pageNumber: 1, snippet: 's1' } as any],
    total: 5,
    page: 1,
    pageSize: 40,
  });

  const { result } = renderHook(() => useContentSearch('some phrase', 40));

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(SearchTabsService.searchBookContent).toHaveBeenCalledWith('some phrase', 1, 40);
  expect(result.current.hits).toHaveLength(1);
  expect(result.current.total).toBe(5);
  expect(result.current.hasMore).toBe(true);
});

test('loadMore appends the next page and dedupes by hit id', async () => {
  vi.mocked(SearchTabsService.searchBookContent).mockResolvedValueOnce({
    hits: [{ id: '1', bookId: 'b1', bookTitle: 'T1', pageNumber: 1, snippet: 's1' } as any],
    total: 2,
    page: 1,
    pageSize: 40,
  });
  const { result } = renderHook(() => useContentSearch('some phrase', 40));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  vi.mocked(SearchTabsService.searchBookContent).mockResolvedValueOnce({
    hits: [{ id: '1', bookId: 'b1', bookTitle: 'T1', pageNumber: 1, snippet: 's1' } as any, { id: '2', bookId: 'b2', bookTitle: 'T2', pageNumber: 2, snippet: 's2' } as any],
    total: 2,
    page: 2,
    pageSize: 40,
  });

  await act(async () => {
    await result.current.loadMore();
  });

  expect(result.current.hits.map((h) => h.id)).toEqual(['1', '2']);
  expect(result.current.hasMore).toBe(false);
});

