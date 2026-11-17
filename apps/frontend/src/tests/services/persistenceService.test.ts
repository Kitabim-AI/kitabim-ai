import { PersistenceService } from '@/src/services/persistenceService';
import { authFetch } from '@/src/services/authService';
import { beforeEach, describe, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('PersistenceService updatePage method', () => {
  test('updatePage sends page text', async () => {
    vi.mocked(authFetch).mockResolvedValue({ ok: true } as Response);

    await PersistenceService.updatePage('book-1', 2, 'text');

    expect(authFetch).toHaveBeenCalledWith(
      '/api/books/book-1/pages/2/update',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'text' }),
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

