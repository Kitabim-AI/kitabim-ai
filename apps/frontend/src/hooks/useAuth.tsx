/**
 * Authentication hook for React components.
 */

import { useState, useEffect, useCallback, createContext, useContext, ReactNode } from 'react';
import { AuthService, User, getAccessToken, clearAccessToken } from '../services/authService';

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  error: string | null;
}

interface AuthContextType extends AuthState {
  login: () => Promise<void>;              // Backward compat (uses Google)
  loginWithGoogle: () => Promise<void>;
  loginWithFacebook: () => Promise<void>;
  loginWithTwitter: () => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
    error: null,
  });

  // Check for existing session on mount
  useEffect(() => {
    const initAuth = async () => {
      const token = getAccessToken();
      if (!token) {
        setState({
          user: null,
          isLoading: false,
          isAuthenticated: false,
          error: null,
        });
        return;
      }

      try {
        const user = await AuthService.getCurrentUser();
        setState({
          user,
          isLoading: false,
          isAuthenticated: !!user,
          error: null,
        });
      } catch (error) {
        console.error('Auth init failed:', error);
        clearAccessToken();
        setState({
          user: null,
          isLoading: false,
          isAuthenticated: false,
          error: 'Session expired',
        });
      }
    };

    initAuth();
  }, []);

  const loginWithGoogle = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const user = await AuthService.loginWithGoogle();

      if (user) {
        setState({
          user,
          isLoading: false,
          isAuthenticated: true,
          error: null,
        });
      } else {
        // User cancelled
        setState(prev => ({ ...prev, isLoading: false }));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Google login failed';
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, []);

  const loginWithFacebook = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const user = await AuthService.loginWithFacebook();

      if (user) {
        setState({
          user,
          isLoading: false,
          isAuthenticated: true,
          error: null,
        });
      } else {
        // User cancelled
        setState(prev => ({ ...prev, isLoading: false }));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Facebook login failed';
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, []);

  const loginWithTwitter = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const user = await AuthService.loginWithTwitter();

      if (user) {
        setState({
          user,
          isLoading: false,
          isAuthenticated: true,
          error: null,
        });
      } else {
        // User cancelled
        setState(prev => ({ ...prev, isLoading: false }));
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Twitter login failed';
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: message,
      }));
    }
  }, []);

  // Keep login() as alias for Google for backward compatibility
  const login = loginWithGoogle;

  const logout = useCallback(async () => {
    setState(prev => ({ ...prev, isLoading: true }));

    await AuthService.logout();

    setState({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      error: null,
    });
  }, []);

  const refreshUser = useCallback(async () => {
    const user = await AuthService.getCurrentUser();
    setState(prev => ({
      ...prev,
      user,
      isAuthenticated: !!user,
    }));
  }, []);

  const value: AuthContextType = {
    ...state,
    login,
    loginWithGoogle,
    loginWithFacebook,
    loginWithTwitter,
    logout,
    refreshUser,
  };

  return (
    <AuthContext.Provider value= { value } >
    { children }
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

/**
 * Check if user has a specific role.
 */
export function useHasRole(...roles: Array<'admin' | 'editor' | 'reader'>): boolean {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated || !user) return false;
  return roles.includes(user.role);
}

/**
 * Check if user can perform admin actions.
 */
export function useIsAdmin(): boolean {
  return useHasRole('admin');
}

/**
 * Check if user can perform editor actions.
 */
export function useIsEditor(): boolean {
  return useHasRole('admin', 'editor');
}

/**
 * Check if user can read books and use chat.
 */
export function useCanRead(): boolean {
  return useHasRole('admin', 'editor', 'reader');
}

export default useAuth;
