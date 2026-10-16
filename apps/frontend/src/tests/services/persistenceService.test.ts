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

  test('previewLlmSpellCheck posts text and returns corrected_text', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: true,
      json: async () => ({ corrected_text: 'fixed' }),
    } as any);
    const controller = new AbortController();

    const result = await PersistenceService.previewLlmSpellCheck('book-1', 5, 'draft', controller.signal);

    expect(result).toBe('fixed');
    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/5/llm-spell-check/preview',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'draft' }),
        signal: controller.signal,
      }
    );
  });

  test('previewLlmSpellCheck throws the backend detail on error', async () => {
    vi.mocked(authFetch).mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: 'translated guardrail error' }),
    } as any);

    await expect(
      PersistenceService.previewLlmSpellCheck('book-1', 5, 'draft')
    ).rejects.toThrow('translated guardrail error');
  });

  test('updatePage sends llm_spell_checked flag', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.updatePage('book-1', 2, 'text', true);

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/2/update',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'text', llm_spell_checked: true }),
      }
    );
  });
});

describe('PersistenceService downloadBook method', () => {
  test('uses download-ticket and triggers direct browser download', async () => {
    vi.mocked(authFetch).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ download_url: '/api/books/book-1/download?ticket=test-ticket' }),
    } as any);

    const clickSpy = vi.fn();
    const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue({
      set href(val: string) {},
      set download(val: string) {},
      click: clickSpy,
    } as any);
    const appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node: any) => node);
    const removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node: any) => node);

    await PersistenceService.downloadBook('book-1', 'test.pdf');

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/download-ticket',
      { method: 'POST' }
    );
    expect(clickSpy).toHaveBeenCalled();

    createElementSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
  });

  test('falls back to direct fetch if ticket fails', async () => {
    vi.mocked(authFetch)
      .mockResolvedValueOnce({ ok: false, status: 500 } as any) // ticket fails
      .mockResolvedValueOnce({
        ok: true,
        blob: async () => new Blob(['pdf-data']),
      } as any); // fallback fetch succeeds

    const clickSpy = vi.fn();
    const createElementSpy = vi.spyOn(document, 'createElement').mockReturnValue({
      set href(val: string) {},
      set download(val: string) {},
      click: clickSpy,
    } as any);
    const appendChildSpy = vi.spyOn(document.body, 'appendChild').mockImplementation((node: any) => node);
    const removeChildSpy = vi.spyOn(document.body, 'removeChild').mockImplementation((node: any) => node);
    const createObjectURLSpy = vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:test');
    const revokeObjectURLSpy = vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {});

    await PersistenceService.downloadBook('book-1', 'test.pdf');

    expect(authFetch).toHaveBeenCalledWith('/api/books/book-1/download');
    expect(clickSpy).toHaveBeenCalled();

    createElementSpy.mockRestore();
    appendChildSpy.mockRestore();
    removeChildSpy.mockRestore();
    createObjectURLSpy.mockRestore();
    revokeObjectURLSpy.mockRestore();
  });
});

