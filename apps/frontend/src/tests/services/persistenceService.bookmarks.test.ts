import { PersistenceService } from '@/src/services/persistenceService';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

import { authFetch } from '@/src/services/authService';

const jsonResponse = (body: unknown, ok = true) => ({
  ok,
  json: async () => body,
} as Response);

beforeEach(() => {
  vi.clearAllMocks();
});

test('saveReadingProgress PUTs the page number', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ bookId: 'b1', pageNumber: 5 }));

  await PersistenceService.saveReadingProgress('b1', 5);

  expect(authFetch).toHaveBeenCalledWith(
    '/api/bookmarks/progress/b1',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ page_number: 5 }) })
  );
});

test('getReadingProgress returns the saved page number', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ pageNumber: 12 }));

  const result = await PersistenceService.getReadingProgress('b1');

  expect(result).toBe(12);
});

test('getReadingProgress returns null when none saved', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ pageNumber: null }));

  const result = await PersistenceService.getReadingProgress('b1');

  expect(result).toBeNull();
});

test('getReadingProgress returns null on failure', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({}, false));

  const result = await PersistenceService.getReadingProgress('b1');

  expect(result).toBeNull();
});

test('listReadingProgress returns the items array', async () => {
  const items = [{ bookId: 'b1', bookTitle: 'T', bookCoverUrl: null, pageNumber: 5, updatedAt: 'now' }];
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ items }));

  const result = await PersistenceService.listReadingProgress();

  expect(result).toEqual(items);
});

test('createBookmark POSTs page, name, and optional quote', async () => {
  const bookmark = { id: 'bm1', bookId: 'b1', bookTitle: 'T', pageNumber: 3, name: 'N', quoteText: 'Q', createdAt: 'now' };
  vi.mocked(authFetch).mockResolvedValue(jsonResponse(bookmark));

  const result = await PersistenceService.createBookmark('b1', 3, 'N', 'Q');

  expect(authFetch).toHaveBeenCalledWith(
    '/api/bookmarks/b1',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ page_number: 3, name: 'N', quote_text: 'Q' }),
    })
  );
  expect(result).toEqual(bookmark);
});

test('listBookmarks omits bookId query param when not scoped', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ bookmarks: [] }));

  await PersistenceService.listBookmarks();

  expect(authFetch).toHaveBeenCalledWith('/api/bookmarks');
});

test('listBookmarks includes bookId query param when scoped', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ bookmarks: [] }));

  await PersistenceService.listBookmarks('b1');

  expect(authFetch).toHaveBeenCalledWith('/api/bookmarks?book_id=b1');
});

test('renameBookmark PATCHes the new name', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({}));

  await PersistenceService.renameBookmark('bm1', 'New name');

  expect(authFetch).toHaveBeenCalledWith(
    '/api/bookmarks/bm1',
    expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ name: 'New name' }) })
  );
});

test('deleteBookmark DELETEs the bookmark', async () => {
  vi.mocked(authFetch).mockResolvedValue(jsonResponse({ success: true }));

  await PersistenceService.deleteBookmark('bm1');

  expect(authFetch).toHaveBeenCalledWith('/api/bookmarks/bm1', expect.objectContaining({ method: 'DELETE' }));
});
