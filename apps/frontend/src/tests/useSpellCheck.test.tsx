import { renderHook, act } from '@testing-library/react';
import { useSpellCheck } from '../hooks/useSpellCheck';
import { expect, test, vi, beforeEach } from 'vitest';

beforeEach(() => {
  vi.clearAllMocks();
});

test('useSpellCheck runs and stores pages', async () => {
  const response = { ok: true, json: vi.fn().mockResolvedValue({ bookId: '1', pageNumber: 2, corrections: [], totalIssues: 0, checkedAt: 'now' }) };
  const fetchMock = vi.fn().mockResolvedValue(response);
  // @ts-expect-error test mock
  global.fetch = fetchMock;

  const { result } = renderHook(() => useSpellCheck('1', 2));

  await act(async () => {
    await result.current.runSpellCheck('Some text');
  });

  expect(fetchMock).toHaveBeenCalledWith(
    '/api/books/1/pages/2/spell-check/',
    expect.any(Object)
  );
  expect(result.current.spellCheckResult?.bookId).toBe('1');
  expect(result.current.isChecking).toBe(false);
});

test('useSpellCheck handles empty text without fetch', async () => {
  const fetchMock = vi.fn();
  // @ts-expect-error test mock
  global.fetch = fetchMock;

  const { result } = renderHook(() => useSpellCheck('1', 2));
  await act(async () => {
    await result.current.runSpellCheck('   ');
  });

  expect(fetchMock).not.toHaveBeenCalled();
});

test('useSpellCheck apply/ignore/reset updates sets', () => {
  const { result } = renderHook(() => useSpellCheck('1', 2));

  act(() => {
    const updated = result.current.applyCorrection({ original: 'a', corrected: 'b', confidence: 1, reason: 't' }, 'a a');
    expect(updated).toBe('b b');
  });

  act(() => {
    result.current.ignoreCorrection({ original: 'x', corrected: 'y', confidence: 1, reason: 't' });
  });

  expect(result.current.appliedCorrections.has('a')).toBe(true);
  expect(result.current.ignoredCorrections.has('x')).toBe(true);

  act(() => {
    result.current.resetSpellCheck();
  });

  expect(result.current.appliedCorrections.size).toBe(0);
  expect(result.current.ignoredCorrections.size).toBe(0);
});

test('useSpellCheck alerts on failure', async () => {
  const response = { ok: false };
  const fetchMock = vi.fn().mockResolvedValue(response);
  const alertMock = vi.fn();
  // @ts-expect-error test mock
  global.fetch = fetchMock;
  // @ts-expect-error test mock
  global.alert = alertMock;

  const { result } = renderHook(() => useSpellCheck('1', 2));

  await act(async () => {
    await result.current.runSpellCheck('text');
  });

  expect(alertMock).toHaveBeenCalled();
});
