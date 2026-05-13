import { useSpellCheck } from '@/src/hooks/useSpellCheck';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

const mockIssues = [
  { id: 1, word: 'teh', char_offset: 0, char_end: 3, ocr_corrections: ['the'], status: 'open' },
  { id: 2, word: 'quikc', char_offset: 4, char_end: 9, ocr_corrections: ['quick'], status: 'open' },
];

test('useSpellCheck loadIssues fetches and stores open issues', async () => {
  const mockFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ milestone: null, issues: mockIssues }),
  });
  // @ts-expect-error test mock
  global.fetch = mockFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));

  await act(async () => {
    await result.current.loadIssues();
  });

  expect(result.current.hasLoaded).toBe(true);
  expect(result.current.issues).toHaveLength(2);
  expect(result.current.issues[0].word).toBe('teh');
  expect(result.current.isLoading).toBe(false);
});

test('useSpellCheck loadIssues filters out non-open issues', async () => {
  const issuesWithMixed = [
    ...mockIssues,
    { id: 3, word: 'fox', char_offset: 10, char_end: 13, ocr_corrections: [], status: 'corrected' },
  ];
  const mockFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ milestone: null, issues: issuesWithMixed }),
  });
  // @ts-expect-error test mock
  global.fetch = mockFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));

  await act(async () => {
    await result.current.loadIssues();
  });

  // Should filter out the 'corrected' status issue
  expect(result.current.issues).toHaveLength(2);
  expect(result.current.issues.every(i => i.status === 'open')).toBe(true);
});

test('useSpellCheck loadIssues handles fetch failure gracefully', async () => {
  const mockFetch = vi.fn().mockResolvedValue({ ok: false });
  // @ts-expect-error test mock
  global.fetch = mockFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));

  await act(async () => {
    await result.current.loadIssues();
  });

  expect(result.current.hasLoaded).toBe(false);
  expect(result.current.issues).toHaveLength(0);
});

test('useSpellCheck applyCorrection removes issue on success', async () => {
  // Seed with issues first
  const loadFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ milestone: null, issues: mockIssues }),
  });
  // @ts-expect-error test mock
  global.fetch = loadFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));
  await act(async () => { await result.current.loadIssues(); });

  // Now mock apply
  const applyFetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({ applied: 1 }) });
  // @ts-expect-error test mock
  global.fetch = applyFetch;

  let success: boolean | undefined;
  await act(async () => {
    success = await result.current.applyCorrection(1, 'the');
  });

  expect(success).toBe(true);
  expect(result.current.issues).toHaveLength(1);
  expect(result.current.issues[0].id).toBe(2);
});

test('useSpellCheck applyCorrection returns false on failure', async () => {
  const mockFetch = vi.fn().mockResolvedValue({ ok: false });
  // @ts-expect-error test mock
  global.fetch = mockFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));

  let success: boolean | undefined;
  await act(async () => {
    success = await result.current.applyCorrection(1, 'the');
  });

  expect(success).toBe(false);
});

test('useSpellCheck ignoreIssue removes issue on success', async () => {
  const loadFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ milestone: null, issues: mockIssues }),
  });
  // @ts-expect-error test mock
  global.fetch = loadFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));
  await act(async () => { await result.current.loadIssues(); });

  const ignoreFetch = vi.fn().mockResolvedValue({ ok: true, json: vi.fn().mockResolvedValue({ ignored: 1 }) });
  // @ts-expect-error test mock
  global.fetch = ignoreFetch;

  await act(async () => {
    await result.current.ignoreIssue(1);
  });

  expect(result.current.issues).toHaveLength(1);
  expect(result.current.issues[0].id).toBe(2);
});

test('useSpellCheck reset clears all state', async () => {
  const mockFetch = vi.fn().mockResolvedValue({
    ok: true,
    json: vi.fn().mockResolvedValue({ milestone: null, issues: mockIssues }),
  });
  // @ts-expect-error test mock
  global.fetch = mockFetch;

  const { result } = renderHook(() => useSpellCheck('book1', 1));
  await act(async () => { await result.current.loadIssues(); });

  expect(result.current.hasLoaded).toBe(true);
  expect(result.current.issues).toHaveLength(2);

  act(() => { result.current.reset(); });

  expect(result.current.hasLoaded).toBe(false);
  expect(result.current.issues).toHaveLength(0);
  expect(result.current.isScanning).toBe(false);
});
