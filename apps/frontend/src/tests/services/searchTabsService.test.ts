import { SearchTabsService } from '@/src/services/searchTabsService';
import { authFetch } from '@/src/services/authService';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test('searchNames maps snake_case letter_group to camelCase', async () => {
  vi.mocked(authFetch).mockResolvedValue({
    ok: true,
    json: async () => [{ id: 1, name: 'ئابدۇللا', letter_group: 'ئا' }],
  } as any);

  const result = await SearchTabsService.searchNames('ئا');

  expect(result).toEqual([{ id: 1, name: 'ئابدۇللا', letterGroup: 'ئا' }]);
  expect(authFetch).toHaveBeenCalledWith(expect.stringContaining('/api/names-dictionary/search?q='));
});

test('searchDictionary returns [] when the request fails', async () => {
  vi.mocked(authFetch).mockResolvedValue({ ok: false } as any);

  const result = await SearchTabsService.searchDictionary('كىتاب');

  expect(result).toEqual([]);
});

test('checkSpelling maps is_known/suggestions to camelCase, and returns null on failure', async () => {
  vi.mocked(authFetch).mockResolvedValueOnce({
    ok: true,
    json: async () => ({ is_known: false, word: 'كىتاپ', suggestions: [{ id: 1, word: 'كىتاب', score: 0.8 }] }),
  } as any);

  const result = await SearchTabsService.checkSpelling('كىتاپ');
  expect(result).toEqual({ isKnown: false, word: 'كىتاپ', suggestions: [{ id: 1, word: 'كىتاب', score: 0.8 }] });

  vi.mocked(authFetch).mockResolvedValueOnce({ ok: false } as any);
  expect(await SearchTabsService.checkSpelling('x')).toBeNull();
});

test('searchBookContent returns an empty page on failure instead of throwing', async () => {
  vi.mocked(authFetch).mockRejectedValue(new Error('network error'));

  const result = await SearchTabsService.searchBookContent('some phrase', 1, 40);

  expect(result).toEqual({ books: [], total: 0, totalReady: 0, page: 1, pageSize: 40 });
});
