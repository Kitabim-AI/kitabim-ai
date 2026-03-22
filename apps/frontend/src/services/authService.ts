/**
 * Authentication service for handling auth API calls.
 */
import { APP_CLIENT_ID } from '../config';

const API_BASE = '/api/auth';
const TOKEN_KEY = 'kitabim_access_token';

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

/**
 * Get stored access token from localStorage.
 */
export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Store access token in localStorage.
 */
export function setAccessToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

/**
 * Clear access token from localStorage.
 */
export function clearAccessToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Create headers with authorization if token exists.
 */
export function getAuthHeaders(): HeadersInit {
  const token = getAccessToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'X-Kitabim-App-Id': APP_CLIENT_ID,
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
  const token = getAccessToken();

  const headers = new Headers(options.headers);
  headers.set('X-Kitabim-App-Id', APP_CLIENT_ID);
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
      const authChannel = new BroadcastChannel('kitabim_auth');

      const popup = window.open(
        `${API_BASE}/${provider}/login`,
        `${provider}-login`,
        `width=${width},height=${height},left=${left},top=${top},popup=1`
      );

      if (!popup) {
        authChannel.close();
        reject(new Error('Popup blocked. Please allow popups for this site.'));
        return;
      }

      let messageReceived = false;

      // Shared logic to finalize login
      const finalizeLogin = async (token: string) => {
        if (messageReceived) return;
        console.log(`[OAuth ${provider}] Login success! Finalizing session...`);
        messageReceived = true;
        
        setAccessToken(token);
        authChannel.close();
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

      // Listen for BroadcastChannel messages
      authChannel.onmessage = (event) => {
        if (event.data?.type === 'OAUTH_SUCCESS' && event.data?.accessToken) {
          finalizeLogin(event.data.accessToken);
        }
      };

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

        if (event.data?.type === 'OAUTH_SUCCESS') {
          finalizeLogin(event.data.accessToken);
        } else if (event.data?.type === 'OAUTH_ERROR') {
          console.log(`[OAuth ${provider}] Received error message`);
          messageReceived = true;
          authChannel.close();
          window.removeEventListener('message', handleMessage);
          reject(new Error(event.data.error));
        }
      };

      window.addEventListener('message', handleMessage);

      // Check if token was set in localStorage as fallback (for when popup can't post message)
      const checkInterval = setInterval(async () => {
        try {
          if (popup.closed) {
            clearInterval(checkInterval);
            window.removeEventListener('message', handleMessage);

            if (!messageReceived) {
              console.log(`[OAuth ${provider}] Popup closed, checking for localStorage token`);
              // Check if token was set via localStorage fallback
              const token = getAccessToken();
              if (token) {
                const user = await this.getCurrentUser();
                if (user) {
                  console.log(`[OAuth ${provider}] Found token in localStorage, login successful`);
                  authChannel.close();
                  resolve(user);
                  return;
                }
              }
              authChannel.close();
              reject(new Error('Login cancelled or popup closed without authentication'));
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

async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE}/refresh`, {
        method: 'POST',
        headers: {
          'X-Kitabim-App-Id': APP_CLIENT_ID,
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
