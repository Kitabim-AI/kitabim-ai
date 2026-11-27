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

  expect(SearchTabsService.checkSpelling).toHaveBeenCalledWith('كىتاب', expect.any(AbortSignal));
  expect(result.current.result).toEqual({ isKnown: true, word: 'كىتاب', suggestions: [] });
});

test('aborts in-flight spelling check when word changes', async () => {
  let capturedSignal: AbortSignal | undefined;
  vi.mocked(SearchTabsService.checkSpelling).mockImplementation(async (_word, signal) => {
    capturedSignal = signal;
    return new Promise(() => {});
  });

  const { rerender } = renderHook(({ w }) => useSpellingCheck(w), {
    initialProps: { w: 'كىت' },
  });

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(capturedSignal).toBeDefined();
  expect(capturedSignal?.aborted).toBe(false);

  rerender({ w: 'كىتاب' });
  expect(capturedSignal?.aborted).toBe(true);
});
