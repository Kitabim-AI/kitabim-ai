/**
 * Authentication service for handling auth API calls.
 */

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
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
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
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

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
   * Initiate Google login in a popup window.
   */
  loginWithGoogle(): Promise<User | null> {
    return new Promise((resolve, reject) => {
      const width = 500;
      const height = 600;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      const popup = window.open(
        `${API_BASE}/google/login`,
        'google-login',
        `width=${width},height=${height},left=${left},top=${top},popup=1`
      );

      if (!popup) {
        reject(new Error('Popup blocked. Please allow popups for this site.'));
        return;
      }

      // Listen for message from popup
      const handleMessage = async (event: MessageEvent) => {
        // Allow messages from same origin OR backend origin
        const allowedOrigins = [window.location.origin, 'http://localhost:8000'];
        if (!allowedOrigins.includes(event.origin)) return;

        if (event.data?.type === 'OAUTH_SUCCESS') {
          clearInterval(checkClosed);
          window.removeEventListener('message', handleMessage);

          const { accessToken } = event.data;
          setAccessToken(accessToken);

          // Fetch user profile
          const user = await this.getCurrentUser();
          resolve(user);
        } else if (event.data?.type === 'OAUTH_ERROR') {
          clearInterval(checkClosed);
          window.removeEventListener('message', handleMessage);
          reject(new Error(event.data.error));
        }
      };

      window.addEventListener('message', handleMessage);

      // Check if popup was closed without completing login
      const checkClosed = setInterval(() => {
        try {
          // Browser might throw or warn on this check due to COOP
          if (popup && popup.closed) {
            clearInterval(checkClosed);
            window.removeEventListener('message', handleMessage);
            resolve(null); // User closed popup
          }
        } catch (error) {
          // Ignore COOP/Cross-origin errors, the message listener handles the success case
          console.debug('Popup closed check suppressed by COOP');
        }
      }, 500);
    });
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
async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/refresh`, {
      method: 'POST',
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
  }
}

export default AuthService;
