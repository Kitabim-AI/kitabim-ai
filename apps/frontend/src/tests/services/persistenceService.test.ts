import { PersistenceService } from '@/src/services/persistenceService';
import { authFetch } from '@/src/services/authService';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PersistenceService LLM spell check methods', () => {
  test('reprocessLlmSpellCheck posts to the correct endpoint', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.reprocessLlmSpellCheck('book-1');

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/reprocess/llm-spell-check',
      { method: 'POST' }
    );
  });

  test('reprocessLlmSpellCheck throws on non-ok response', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: false, status: 500 } as Response);

    await expect(PersistenceService.reprocessLlmSpellCheck('book-1')).rejects.toThrow();
  });

  test('triggerLlmSpellCheckPage posts to the correct endpoint', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.triggerLlmSpellCheckPage('book-1', 5);

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/5/llm-spell-check',
      { method: 'POST' }
    );
  });

  test('triggerLlmSpellCheckPage throws on 409 already-running response', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: false, status: 409 } as Response);

    await expect(
      PersistenceService.triggerLlmSpellCheckPage('book-1', 5)
    ).rejects.toThrow();
  });
});
