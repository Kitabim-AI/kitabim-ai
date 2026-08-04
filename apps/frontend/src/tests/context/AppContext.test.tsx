import React from 'react';
import { AppProvider, useAppContext } from '@/src/context/AppContext';
import { AuthProvider } from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { NotificationProvider } from '@/src/context/NotificationContext';
import { act, renderHook } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

const i18nMockValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <NotificationProvider>
    <AuthProvider>
      <I18nContext.Provider value={i18nMockValue}>
        <AppProvider>{children}</AppProvider>
      </I18nContext.Provider>
    </AuthProvider>
  </NotificationProvider>
);

test('home search tab and query survive opening and closing the reader', () => {
  const { result } = renderHook(() => useAppContext(), { wrapper });

  act(() => {
    result.current.setHomeActiveTab('content');
    result.current.setHomeSearchText('tarikh');
  });
  expect(result.current.homeActiveTab).toBe('content');
  expect(result.current.homeSearchText).toBe('tarikh');

  // AppProvider stays mounted for the whole SPA session — only HomeView unmounts when
  // the reader opens and remounts when it closes — so the home search session must survive.
  act(() => {
    result.current.setView('reader');
  });
  act(() => {
    result.current.setView(result.current.previousView);
  });

  expect(result.current.view).toBe('home');
  expect(result.current.homeActiveTab).toBe('content');
  expect(result.current.homeSearchText).toBe('tarikh');
});

test('home search tab and query reset when explicitly navigating away from home', () => {
  const { result } = renderHook(() => useAppContext(), { wrapper });

  act(() => {
    result.current.setHomeActiveTab('content');
    result.current.setHomeSearchText('tarikh');
  });

  act(() => {
    result.current.setView('join-us');
  });

  expect(result.current.homeActiveTab).toBe('ask');
  expect(result.current.homeSearchText).toBe('');
});
