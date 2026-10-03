import { useBookmarks } from '@/src/hooks/useBookmarks';
import { PersistenceService } from '@/src/services/persistenceService';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    listBookmarks: vi.fn(),
    createBookmark: vi.fn(),
    renameBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
  },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ isAuthenticated: true })),
}));

import { useAuth } from '@/src/hooks/useAuth';

const mockBookmark = {
  id: 'bm1', bookId: 'b1', bookTitle: 'T', pageNumber: 3, name: 'N', quoteText: null, createdAt: 'now',
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('loads bookmarks scoped to a book on mount', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);

  const { result } = renderHook(() => useBookmarks('b1'));

  await waitFor(() => expect(result.current.bookmarks).toEqual([mockBookmark]));
  expect(PersistenceService.listBookmarks).toHaveBeenCalledWith('b1');
});

test('loads all bookmarks when no bookId given', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);

  renderHook(() => useBookmarks());

  await waitFor(() => expect(PersistenceService.listBookmarks).toHaveBeenCalledWith(undefined));
});

test('skips fetching and clears list for guests', async () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);

  const { result } = renderHook(() => useBookmarks('b1'));

  await waitFor(() => expect(result.current.isLoading).toBe(false));
  expect(PersistenceService.listBookmarks).not.toHaveBeenCalled();
  expect(result.current.bookmarks).toEqual([]);
});

test('create appends the new bookmark to state', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
  vi.mocked(PersistenceService.createBookmark).mockResolvedValue(mockBookmark);
  const { result } = renderHook(() => useBookmarks('b1'));
  await waitFor(() => expect(result.current.isLoading).toBe(false));

  await act(async () => {
    await result.current.create(3, 'N');
  });

  expect(PersistenceService.createBookmark).toHaveBeenCalledWith('b1', 3, 'N', undefined);
  expect(result.current.bookmarks).toEqual([mockBookmark]);
});

test('rename updates the bookmark name in state', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);
  const { result } = renderHook(() => useBookmarks('b1'));
  await waitFor(() => expect(result.current.bookmarks).toEqual([mockBookmark]));

  await act(async () => {
    await result.current.rename('bm1', 'Renamed');
  });

  expect(PersistenceService.renameBookmark).toHaveBeenCalledWith('bm1', 'Renamed');
  expect(result.current.bookmarks[0].name).toBe('Renamed');
});

test('remove drops the bookmark from state', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([mockBookmark]);
  const { result } = renderHook(() => useBookmarks('b1'));
  await waitFor(() => expect(result.current.bookmarks).toEqual([mockBookmark]));

  await act(async () => {
    await result.current.remove('bm1');
  });

  expect(PersistenceService.deleteBookmark).toHaveBeenCalledWith('bm1');
  expect(result.current.bookmarks).toEqual([]);
});
