import { HOME_SEARCH_TAB_STORAGE_KEY } from '@/src/components/library/searchTabsConfig';
import { useHomeSearchTab } from '@/src/hooks/useHomeSearchTab';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, test } from 'vitest';

beforeEach(() => {
  window.localStorage.clear();
});

test('defaults to the "ask" tab when nothing is stored', () => {
  const { result } = renderHook(() => useHomeSearchTab());
  expect(result.current.activeTab).toBe('ask');
});

test('restores the last-used tab from localStorage on mount', () => {
  window.localStorage.setItem(HOME_SEARCH_TAB_STORAGE_KEY, 'quran');
  const { result } = renderHook(() => useHomeSearchTab());
  expect(result.current.activeTab).toBe('quran');
});

test('falls back to default for an unrecognized stored value', () => {
  window.localStorage.setItem(HOME_SEARCH_TAB_STORAGE_KEY, 'not-a-real-tab');
  const { result } = renderHook(() => useHomeSearchTab());
  expect(result.current.activeTab).toBe('ask');
});

test('persists the active tab to localStorage when changed', () => {
  const { result } = renderHook(() => useHomeSearchTab());

  act(() => {
    result.current.setActiveTab('dictionary');
  });

  expect(result.current.activeTab).toBe('dictionary');
  expect(window.localStorage.getItem(HOME_SEARCH_TAB_STORAGE_KEY)).toBe('dictionary');
});
