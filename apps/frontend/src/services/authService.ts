/**
 * Authentication service for handling auth API calls.
 */
const API_BASE = '/api/auth';
const SESSION_TOKEN_KEY = 'kitabim_access_token_session';

// App ID configured via Vite build-time environment variable (from SECURITY_APP_ID)
let _appClientId =
  ((import.meta as any).env?.VITE_SECURITY_APP_ID as string) ||
  (typeof process !== 'undefined' ? (process.env?.VITE_SECURITY_APP_ID as string) : '') ||
  '';
let _configPromise: Promise<void> | null = null;
let _configLoaded = false;

const DEFAULT_COLLECTION_PAGE_SIZE = 40;
let _collectionPageSize = DEFAULT_COLLECTION_PAGE_SIZE;
let _showChatCost = true;
const DEFAULT_MAX_UPLOAD_MB = 500;
let _maxUploadMb = DEFAULT_MAX_UPLOAD_MB;

export async function initAppConfig(): Promise<void> {
  if (_configLoaded) return;
  if (!_configPromise) {
    _configPromise = (async () => {
      try {
        const res = await fetch('/api/config');
        if (res.ok) {
          const data = await res.json();
          _collectionPageSize =
            typeof data.collectionPageSize === 'number'
              ? data.collectionPageSize
              : DEFAULT_COLLECTION_PAGE_SIZE;
          _showChatCost =
            typeof data.showChatCost === 'boolean'
              ? data.showChatCost
              : true;
          _maxUploadMb =
            typeof data.maxUploadMb === 'number'
              ? data.maxUploadMb
              : DEFAULT_MAX_UPLOAD_MB;
          _configLoaded = true;
        }
      } catch {
        // Non-fatal — defaults used
      } finally {
        _configPromise = null;
      }
    })();
  }
  return _configPromise;
}

export function getCollectionPageSize(): number {
  return _collectionPageSize;
}

export function getShowChatCost(): boolean {
  return _showChatCost;
}

export function getMaxUploadMb(): number {
  return _maxUploadMb;
}

// Access token lives in memory only — never persisted to localStorage.
// On page load, useAuth recovers the session via the httpOnly refresh cookie.
let _accessToken: string | null = null;

export interface User {
  id: string;
  email: string;
  displayName: string;
  avatarUrl?: string;
  role: 'admin' | 'editor' | 'reader';
}

export interface AuthTokens {
  accessToken: string;
}

export const AUTH_ERROR_CODES = [
  'signup_email_domain_rejected',
  'signup_verification_unavailable',
  'oauth_login_failed',
  'email_not_verified',
  'email_already_exists',
  'account_disabled',
] as const;

export type AuthErrorCode = (typeof AUTH_ERROR_CODES)[number];

const AUTH_ERROR_CODE_SET: ReadonlySet<string> = new Set(AUTH_ERROR_CODES);

export function isAuthErrorCode(value: unknown): value is AuthErrorCode {
  return typeof value === 'string' && AUTH_ERROR_CODE_SET.has(value);
}

export class OAuthCallbackError extends Error {
  readonly errorCode: AuthErrorCode;

  constructor(errorCode: AuthErrorCode, fallbackMessage?: string) {
    super(fallbackMessage || errorCode);
    this.name = 'OAuthCallbackError';
    this.errorCode = errorCode;
  }
}

let _redirectErrorChecked = false;
let _consumedRedirectError: AuthErrorCode | null = null;

/**
 * Consume and validate `?auth_error=` from the URL once per page load (Mobile Safari OAuth fallback).
 * Strips the query parameter immediately via history.replaceState while caching the validated
 * AuthErrorCode across React 19 <StrictMode> double-mounts until clearConsumedRedirectAuthError() runs.
 */
export function consumeRedirectAuthError(): AuthErrorCode | null {
  if (_redirectErrorChecked) {
    return _consumedRedirectError;
  }
  _redirectErrorChecked = true;

  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const params = new URLSearchParams(window.location.search);
    if (!params.has('auth_error')) {
      return null;
    }

    const rawCode = params.get('auth_error');
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete('auth_error');
    window.history.replaceState({}, '', cleanUrl.toString());

    if (isAuthErrorCode(rawCode)) {
      _consumedRedirectError = rawCode;
      return rawCode;
    }
  } catch {
    // Ignore malformed URL edge cases
  }

  return null;
}

/**
 * Reset cached redirect error state after UI consumption.
 */
export function clearConsumedRedirectAuthError(): void {
  _consumedRedirectError = null;
}

/**
 * Get access token from memory.
 */
export function getAccessToken(): string | null {
  return _accessToken;
}

/**
 * Store access token in memory only (never persisted to localStorage).
 */
export function setAccessToken(token: string): void {
  _accessToken = token;
}

/**
 * Clear access token from memory.
 */
export function clearAccessToken(): void {
  _accessToken = null;
}

/**
 * Read a one-time token from sessionStorage (OAuth redirect fallback), store
 * it in memory, and clear it immediately so it doesn't linger.
 * Returns true if a token was recovered.
 */
export function recoverSessionToken(): boolean {
  const token = sessionStorage.getItem(SESSION_TOKEN_KEY);
  if (token) {
    _accessToken = token;
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
    return true;
  }
  return false;
}

/**
 * Create headers with authorization if token exists.
 */
export function getAuthHeaders(): HeadersInit {
  const token = getAccessToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-Kitabim-App-Id': _appClientId,
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const lang = localStorage.getItem('kitabim_language') || 'ug';
  headers['Accept-Language'] = lang;
  return headers;
}

/**
 * Authenticated fetch wrapper that handles 401 errors.
 */
export async function authFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  if (!_appClientId) {
    await initAppConfig();
  }
  const token = getAccessToken();

  const headers = new Headers(options.headers);
  headers.set('X-Kitabim-App-Id', _appClientId);
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const lang = localStorage.getItem('kitabim_language') || 'ug';
  headers.set('Accept-Language', lang);

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include', // Include cookies for refresh token
  });

  // Handle 401 - try to refresh token
  if (response.status === 401 && token) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry with new token
      const newToken = getAccessToken();
      headers.set('Authorization', `Bearer ${newToken}`);
      return fetch(url, { ...options, headers, credentials: 'include' });
    }
    // Refresh failed - clear token
    clearAccessToken();
  }

  return response;
}

/**
 * Auth service methods.
 */
export const AuthService = {
  /**
   * Get current user profile.
   */
  async getCurrentUser(): Promise<User | null> {
    const token = getAccessToken();
    if (!token) {
      return null;
    }

    try {
      const response = await authFetch(`${API_BASE}/me`);
      if (!response.ok) {
        if (response.status === 401) {
          clearAccessToken();
        }
        return null;
      }

      const data = await response.json();
      return {
        id: data.id,
        email: data.email,
        displayName: data.display_name,
        avatarUrl: data.avatar_url,
        role: data.role,
      };
    } catch (error) {
      console.error('Failed to get current user:', error);
      return null;
    }
  },

  /**
   * Detect iOS/iPadOS Safari (popup flow is unreliable — use redirect instead).
   * iPadOS 13+ in "Request Desktop Website" mode reports a Mac UA, so we also
   * check for maxTouchPoints > 1 to catch iPads masquerading as desktop.
   */
  _isMobileSafari(): boolean {
    const ua = navigator.userAgent;
    const isIOS = /iPhone|iPad|iPod/i.test(ua);
    const isIPadDesktopMode = /Macintosh/i.test(ua) && navigator.maxTouchPoints > 1;
    const isSafari = /Safari/i.test(ua) && !/CriOS|FxiOS|OPiOS|EdgiOS|Chrome/i.test(ua);
    return (isIOS || isIPadDesktopMode) && isSafari;
  },

  /**
   * Generic OAuth login handler (private method).
   */
  _loginWithProvider(provider: 'google' | 'facebook' | 'twitter'): Promise<User | null> {
    // iOS Safari: popup flow breaks due to ITP cookie restrictions — use full-page redirect
    if (this._isMobileSafari()) {
      const next = encodeURIComponent(window.location.origin + '/');
      window.location.href = `${API_BASE}/${provider}/login?next=${next}`;
      return new Promise(() => {}); // Page navigates away; promise intentionally never resolves
    }

    return new Promise((resolve, reject) => {
      const width = 500;
      const height = 600;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      // Use BroadcastChannel as a more robust alternative to window.postMessage
      // that doesn't depend on the fragile window.opener link.
      const authChannel =
        typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('kitabim_auth') : null;

      const popup = window.open(
        `${API_BASE}/${provider}/login`,
        `${provider}-login`,
        `width=${width},height=${height},left=${left},top=${top},popup=1`
      );

      if (!popup) {
        authChannel?.close();
        reject(new OAuthCallbackError('oauth_login_failed', 'Popup blocked. Please allow popups for this site.'));
        return;
      }

      let messageReceived = false;
      let checkInterval: ReturnType<typeof setInterval> | undefined;

      // Shared logic to finalize login
      const finalizeLogin = async (token: string) => {
        if (messageReceived) return;
        console.log(`[OAuth ${provider}] Login success! Finalizing session...`);
        messageReceived = true;
        if (checkInterval !== undefined) {
          clearInterval(checkInterval);
        }

        setAccessToken(token);
        authChannel?.close();
        window.removeEventListener('message', handleMessage);

        try {
          if (popup && !popup.closed) {
            popup.close();
          }
        } catch (e) {
          console.warn(`[OAuth ${provider}] Could not close popup:`, e);
        }

        const user = await this.getCurrentUser();
        resolve(user);
      };

      // Shared logic to fail login with a closed AuthErrorCode
      const failLogin = (errorCode: AuthErrorCode, fallbackMessage?: string) => {
        if (messageReceived) return;
        console.log(`[OAuth ${provider}] Login error (${errorCode})`);
        messageReceived = true;
        if (checkInterval !== undefined) {
          clearInterval(checkInterval);
        }

        authChannel?.close();
        window.removeEventListener('message', handleMessage);

        try {
          if (popup && !popup.closed) {
            popup.close();
          }
        } catch (e) {
          console.warn(`[OAuth ${provider}] Could not close popup:`, e);
        }

        reject(new OAuthCallbackError(errorCode, fallbackMessage));
      };

      // Listen for BroadcastChannel messages
      if (authChannel) {
        authChannel.onmessage = (event) => {
          if (event.data?.type === 'OAUTH_SUCCESS' && event.data?.accessToken) {
            finalizeLogin(event.data.accessToken);
          } else if (event.data?.type === 'OAUTH_ERROR') {
            const code = isAuthErrorCode(event.data?.errorCode)
              ? event.data.errorCode
              : 'oauth_login_failed';
            failLogin(code, typeof event.data?.error === 'string' ? event.data.error : undefined);
          }
        };
      }

      // Listen for postMessage from popup (legacy/fallback)
      const handleMessage = async (event: MessageEvent) => {
        // Allow messages from same origin OR backend origin
        // Local dev: Vite dev server (localhost:3000) or Docker frontend (localhost:30080)
        // Production: kitabim.ai and www.kitabim.ai
        const allowedOrigins = [
          window.location.origin,           // Current origin (always allowed)
          'http://localhost:3000',          // Vite dev server
          'http://localhost:30080',         // Docker frontend
          'https://kitabim.ai',             // Production
          'https://www.kitabim.ai'          // Production www subdomain
        ];
        if (!allowedOrigins.includes(event.origin)) {
          console.log(`[OAuth ${provider}] Ignored message from origin:`, event.origin);
          return;
        }

        if (event.data?.type === 'OAUTH_SUCCESS' && event.data?.accessToken) {
          finalizeLogin(event.data.accessToken);
        } else if (event.data?.type === 'OAUTH_ERROR') {
          const code = isAuthErrorCode(event.data?.errorCode)
            ? event.data.errorCode
            : 'oauth_login_failed';
          failLogin(code, typeof event.data?.error === 'string' ? event.data.error : undefined);
        }
      };

      window.addEventListener('message', handleMessage);

      // When popup closes, attempt a silent refresh — the backend may have set
      // the httpOnly refresh cookie even if postMessage/BroadcastChannel failed.
      checkInterval = setInterval(async () => {
        try {
          if (popup.closed) {
            clearInterval(checkInterval);
            window.removeEventListener('message', handleMessage);

            if (!messageReceived) {
              console.log(`[OAuth ${provider}] Popup closed, attempting silent token refresh`);
              const refreshed = await refreshAccessToken();
              if (refreshed) {
                const user = await this.getCurrentUser();
                if (user) {
                  console.log(`[OAuth ${provider}] Silent refresh succeeded`);
                  authChannel?.close();
                  resolve(user);
                  return;
                }
              }
              authChannel?.close();
              resolve(null);
            }
          }
        } catch (e) {
          // Popup.closed can throw if popup is on different origin
          // This is expected behavior, ignore it
        }
      }, 500);
    });
  },

  /**
   * Initiate Google login in a popup window.
   */
  loginWithGoogle(): Promise<User | null> {
    return this._loginWithProvider('google');
  },

  /**
   * Initiate Facebook login in a popup window.
   */
  loginWithFacebook(): Promise<User | null> {
    return this._loginWithProvider('facebook');
  },

  /**
   * Initiate Twitter login in a popup window.
   */
  loginWithTwitter(): Promise<User | null> {
    return this._loginWithProvider('twitter');
  },

  /**
   * Logout the current user.
   */
  async logout(): Promise<void> {
    try {
      await authFetch(`${API_BASE}/logout`, {
        method: 'POST',
      });
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      clearAccessToken();
    }
  },

  /**
   * Check auth health endpoint.
   */
  async checkHealth(): Promise<{ status: string; googleOauth: string }> {
    try {
      const response = await fetch(`${API_BASE}/health`);
      if (!response.ok) {
        throw new Error('Auth service unhealthy');
      }
      const data = await response.json();
      return {
        status: data.status,
        googleOauth: data.google_oauth,
      };
    } catch (error) {
      console.error('Auth health check failed:', error);
      return { status: 'error', googleOauth: 'unknown' };
    }
  },
};

/**
 * Refresh the access token using the refresh token cookie.
 */
/**
 * Refresh the access token using the refresh token cookie.
 * Uses a singleton promise to avoid multiple simultaneous refresh calls.
 */
let refreshPromise: Promise<boolean> | null = null;

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE}/refresh`, {
        method: 'POST',
        headers: {
          'X-Kitabim-App-Id': _appClientId,
        },
        credentials: 'include',
      });

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      if (data.access_token) {
        setAccessToken(data.access_token);
        return true;
      }

      return false;
    } catch (error) {
      console.error('Token refresh failed:', error);
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export default AuthService;
