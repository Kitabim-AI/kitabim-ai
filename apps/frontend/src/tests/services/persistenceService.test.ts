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

