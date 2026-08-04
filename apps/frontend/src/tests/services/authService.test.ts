import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('authService.initAppConfig / getCollectionPageSize', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('fetches collectionPageSize from /api/config and exposes it', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ appId: 'app-1', collectionPageSize: 55 }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getCollectionPageSize } = await import('../../services/authService');
    await initAppConfig();

    expect(getCollectionPageSize()).toBe(55);
  });

  it('falls back to 40 when the config fetch fails', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('network error'));
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getCollectionPageSize } = await import('../../services/authService');
    await initAppConfig();

    expect(getCollectionPageSize()).toBe(40);
  });

  it('falls back to 40 when collectionPageSize is missing from the response', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ appId: 'app-1' }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getCollectionPageSize } = await import('../../services/authService');
    await initAppConfig();

    expect(getCollectionPageSize()).toBe(40);
  });
});
