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

  it('fetches showChatCost from /api/config and exposes it', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ showChatCost: false }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getShowChatCost } = await import('../../services/authService');
    await initAppConfig();

    expect(getShowChatCost()).toBe(false);
  });

  it('defaults showChatCost to true when omitted or on error', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('error'));
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getShowChatCost } = await import('../../services/authService');
    await initAppConfig();

    expect(getShowChatCost()).toBe(true);
  });

  it('fetches maxUploadMb from /api/config and exposes it', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ maxUploadMb: 750 }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getMaxUploadMb } = await import('../../services/authService');
    await initAppConfig();

    expect(getMaxUploadMb()).toBe(750);
  });

  it('defaults maxUploadMb to 500 when omitted or on error', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('error'));
    global.fetch = mockFetch as unknown as typeof fetch;

    const { initAppConfig, getMaxUploadMb } = await import('../../services/authService');
    await initAppConfig();

    expect(getMaxUploadMb()).toBe(500);
  });

  it('includes X-Kitabim-App-Id header from environment in auth headers and authFetch', async () => {
    vi.stubEnv('VITE_SECURITY_APP_ID', 'test-app-id-123');

    const mockFetch = vi.fn().mockResolvedValue({
      status: 200,
      ok: true,
      json: vi.fn().mockResolvedValue({}),
    });
    global.fetch = mockFetch as unknown as typeof fetch;

    const { getAuthHeaders, authFetch } = await import('../../services/authService');
    const headers = getAuthHeaders() as Record<string, string>;
    expect(headers['X-Kitabim-App-Id']).toBe('test-app-id-123');

    await authFetch('/api/test');
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/test',
      expect.objectContaining({
        headers: expect.any(Headers),
      })
    );
    const sentHeaders = mockFetch.mock.calls[0][1].headers as Headers;
    expect(sentHeaders.get('X-Kitabim-App-Id')).toBe('test-app-id-123');

    vi.unstubAllEnvs();
  });
});
