import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { useLlmSpellCheckPreview } from '@/src/hooks/useLlmSpellCheckPreview';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: { previewLlmSpellCheck: vi.fn() },
}));

beforeEach(() => vi.clearAllMocks());

test('successful check snapshots baseline and replaces text', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockResolvedValue('fixed text');
  const onChange = vi.fn();
  const { result } = renderHook(() => useLlmSpellCheckPreview('book-1', 3, 'draft text', onChange));

  await act(async () => { await result.current.runCheck(); });

  expect(PersistenceService.previewLlmSpellCheck).toHaveBeenCalledWith('book-1', 3, 'draft text', expect.any(AbortSignal));
  expect(onChange).toHaveBeenCalledWith('fixed text');
  expect(result.current.baselineText).toBe('draft text');
  expect(result.current.isChecking).toBe(false);
  expect(result.current.error).toBeNull();
});

test('failed check sets error and leaves text and baseline alone', async () => {
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockRejectedValue(new Error('boom'));
  const onChange = vi.fn();
  const { result } = renderHook(() => useLlmSpellCheckPreview('book-1', 3, 'draft', onChange));

  await act(async () => { await result.current.runCheck(); });

  expect(onChange).not.toHaveBeenCalled();
  expect(result.current.baselineText).toBeNull();
  expect(result.current.error).toBe('boom');
  expect(result.current.isChecking).toBe(false);
});

test('reset during an in-flight check aborts it and ignores the result', async () => {
  let resolve!: (v: string) => void;
  vi.mocked(PersistenceService.previewLlmSpellCheck).mockImplementation(
    () => new Promise<string>((r) => { resolve = r; })
  );
  const onChange = vi.fn();
  const { result } = renderHook(() => useLlmSpellCheckPreview('book-1', 3, 'draft', onChange));

  let pending!: Promise<void>;
  act(() => { pending = result.current.runCheck(); });
  expect(result.current.isChecking).toBe(true);

  const signal = vi.mocked(PersistenceService.previewLlmSpellCheck).mock.calls[0][3] as AbortSignal;
  act(() => { result.current.reset(); });
  expect(signal.aborted).toBe(true);

  await act(async () => { resolve('late result'); await pending; });

  expect(onChange).not.toHaveBeenCalled();
  expect(result.current.baselineText).toBeNull();
  expect(result.current.isChecking).toBe(false);
});

test('runCheck is a no-op without a bookId', async () => {
  const { result } = renderHook(() => useLlmSpellCheckPreview(undefined, 3, 'draft', vi.fn()));
  await act(async () => { await result.current.runCheck(); });
  expect(PersistenceService.previewLlmSpellCheck).not.toHaveBeenCalled();
});
