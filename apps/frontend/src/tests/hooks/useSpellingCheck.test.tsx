import { useSpellingCheck } from '@/src/hooks/useSpellingCheck';
import { SearchTabsService } from '@/src/services/searchTabsService';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/searchTabsService', () => ({
  SearchTabsService: {
    checkSpelling: vi.fn(),
  },
}));

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

test('returns null result for an empty word without calling the service', () => {
  const { result } = renderHook(() => useSpellingCheck(''));

  act(() => {
    vi.advanceTimersByTime(500);
  });

  expect(SearchTabsService.checkSpelling).not.toHaveBeenCalled();
  expect(result.current.result).toBeNull();
});

test('debounces and surfaces the spelling check result', async () => {
  vi.mocked(SearchTabsService.checkSpelling).mockResolvedValue({
    isKnown: true,
    word: 'كىتاب',
    suggestions: [],
  });

  const { result } = renderHook(() => useSpellingCheck('كىتاب'));

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(SearchTabsService.checkSpelling).toHaveBeenCalledWith('كىتاب');
  expect(result.current.result).toEqual({ isKnown: true, word: 'كىتاب', suggestions: [] });
});
