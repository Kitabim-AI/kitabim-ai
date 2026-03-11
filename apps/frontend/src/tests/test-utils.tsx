import { render as tlRender } from '@testing-library/react';
import React from 'react';
import { I18nContext } from '@/src/i18n/I18nContext';
import { AppProvider } from '@/src/context/AppContext';
import { NotificationProvider } from '@/src/context/NotificationContext';
import { AuthProvider } from '@/src/hooks/useAuth';
import { vi } from 'vitest';

export function renderWithProviders(ui: React.ReactElement, options = {}) {
  const i18nMockValue = {
    language: 'en' as const,
    setLanguage: vi.fn(),
    t: (key: string, params?: Record<string, string | number>) => {
      if (params) {
        return Object.entries(params).reduce(
          (s, [k, v]) => s.replace(`{{${k}}}`, String(v)),
          key
        );
      }
      return key;
    }
  };

  const Wrapper = ({ children }: { children: React.ReactNode }) => {
    return (
      <NotificationProvider>
        <AuthProvider>
          <I18nContext.Provider value={i18nMockValue}>
            <AppProvider>
              {children}
            </AppProvider>
          </I18nContext.Provider>
        </AuthProvider>
      </NotificationProvider>
    );
  };
  
  return tlRender(ui, { wrapper: Wrapper, ...options });
}
