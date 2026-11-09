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

describe('authService OAuth error transport & redirect consumption', () => {
  class FakeBroadcastChannel {
    static instances: FakeBroadcastChannel[] = [];
    name: string;
    closed = false;
    onmessage: ((event: { data: any }) => void) | null = null;

    constructor(name: string) {
      this.name = name;
      FakeBroadcastChannel.instances.push(this);
    }

    close() {
      this.closed = true;
    }

    emit(data: any) {
      this.onmessage?.({ data });
    }
  }

  beforeEach(() => {
    vi.resetModules();
    vi.useRealTimers();
    FakeBroadcastChannel.instances = [];
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel);
    window.history.replaceState({}, '', 'http://localhost:3000/');
  });

  it('rejects with OAuthCallbackError and clears interval on BroadcastChannel OAUTH_ERROR', async () => {
    vi.useFakeTimers();
    const popup = { closed: false, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);

    const { AuthService, OAuthCallbackError } = await import('../../services/authService');
    const loginPromise = AuthService.loginWithGoogle();

    expect(FakeBroadcastChannel.instances).toHaveLength(1);
    const channel = FakeBroadcastChannel.instances[0];
    expect(channel.name).toBe('kitabim_auth');

    channel.emit({
      type: 'OAUTH_ERROR',
      errorCode: 'signup_email_domain_rejected',
      error: 'Domain rejected',
    });

    await expect(loginPromise).rejects.toMatchObject({
      name: 'OAuthCallbackError',
      errorCode: 'signup_email_domain_rejected',
      message: 'Domain rejected',
    });
    await expect(loginPromise).rejects.toBeInstanceOf(OAuthCallbackError);
    expect(channel.closed).toBe(true);
    expect(popup.close).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('falls back to oauth_login_failed when OAUTH_ERROR has an unknown errorCode', async () => {
    const popup = { closed: false, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);

    const { AuthService } = await import('../../services/authService');
    const loginPromise = AuthService.loginWithGoogle();

    FakeBroadcastChannel.instances[0].emit({
      type: 'OAUTH_ERROR',
      errorCode: 'unexpected_custom_code',
      error: 'Something failed',
    });

    await expect(loginPromise).rejects.toMatchObject({
      errorCode: 'oauth_login_failed',
    });
  });

  it('resolves null without error when user voluntarily closes the OAuth popup', async () => {
    vi.useFakeTimers();
    const popup = { closed: false, close: vi.fn() };
    vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 401 }) as unknown as typeof fetch;

    const { AuthService } = await import('../../services/authService');
    const loginPromise = AuthService.loginWithGoogle();

    popup.closed = true;
    await vi.advanceTimersByTimeAsync(600);

    await expect(loginPromise).resolves.toBeNull();
    expect(FakeBroadcastChannel.instances[0].closed).toBe(true);
  });

  it('consumes valid ?auth_error= once, strips URL param, survives StrictMode double-calls, and rejects spoofed codes', async () => {
    window.history.replaceState(
      {},
      '',
      'http://localhost:3000/?foo=bar&auth_error=signup_email_domain_rejected'
    );

    const { consumeRedirectAuthError, clearConsumedRedirectAuthError } = await import(
      '../../services/authService'
    );

    // First call strips ?auth_error= and returns the validated code
    expect(consumeRedirectAuthError()).toBe('signup_email_domain_rejected');
    expect(window.location.search).toBe('?foo=bar');

    // Second call (React 19 <StrictMode> double-mount) returns cached code
    expect(consumeRedirectAuthError()).toBe('signup_email_domain_rejected');

    // Clearing resets cached code
    clearConsumedRedirectAuthError();
    expect(consumeRedirectAuthError()).toBeNull();

    // Fresh module load with spoofed ?auth_error= strips param and returns null
    vi.resetModules();
    window.history.replaceState(
      {},
      '',
      'http://localhost:3000/?auth_error=Visit%20evil.example.com'
    );
    const reloaded = await import('../../services/authService');
    expect(reloaded.consumeRedirectAuthError()).toBeNull();
    expect(window.location.search).toBe('');
  });
});
