import { useLookupSearch } from '@/src/hooks/useLookupSearch';
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

test('does not call the search function below the minimum query length', () => {
  const searchFn = vi.fn().mockResolvedValue([]);
  renderHook(() => useLookupSearch(searchFn, 'a', 2));

  act(() => {
    vi.advanceTimersByTime(500);
  });

  expect(searchFn).not.toHaveBeenCalled();
});

test('debounces and calls the search function once the query reaches minLength', async () => {
  const searchFn = vi.fn().mockResolvedValue([{ id: 1, word: 'كىتاب' }]);
  const { result } = renderHook(() => useLookupSearch(searchFn, 'كىتاب', 1, 20));

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(searchFn).toHaveBeenCalledWith('كىتاب', 20);
  expect(result.current.results).toHaveLength(1);
});

test('clears results when the query is cleared below minLength', async () => {
  const searchFn = vi.fn().mockResolvedValue([{ id: 1, word: 'كىتاب' }]);
  const { result, rerender } = renderHook(({ query }) => useLookupSearch(searchFn, query, 1), {
    initialProps: { query: 'كىتاب' },
  });

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
  expect(result.current.results).toHaveLength(1);

  rerender({ query: '' });

  expect(result.current.results).toHaveLength(0);
});

test('ignores a stale in-flight response when the query changes quickly', async () => {
  let resolveFirst: (v: any[]) => void = () => {};
  const searchFn = vi
    .fn()
    .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockImplementationOnce(() => Promise.resolve([{ id: 2, word: 'second' }]));

  const { result, rerender } = renderHook(({ query }) => useLookupSearch(searchFn, query, 1), {
    initialProps: { query: 'first' },
  });

  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });
  rerender({ query: 'second' });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(300);
  });

  expect(result.current.results).toEqual([{ id: 2, word: 'second' }]);

  // The stale first request resolving afterwards must not clobber the newer result.
  await act(async () => {
    resolveFirst([{ id: 1, word: 'first' }]);
    await Promise.resolve();
  });
  expect(result.current.results).toEqual([{ id: 2, word: 'second' }]);
});
