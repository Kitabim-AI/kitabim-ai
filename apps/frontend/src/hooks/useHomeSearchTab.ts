import { useCallback, useState } from 'react';
import { DEFAULT_SEARCH_TAB, HOME_SEARCH_TAB_STORAGE_KEY, SEARCH_TABS, SearchTabKey } from '../components/library/searchTabsConfig';

const VALID_KEYS = new Set<string>(SEARCH_TABS.map((t) => t.key));

function readStoredTab(): SearchTabKey {
  try {
    const stored = window.localStorage.getItem(HOME_SEARCH_TAB_STORAGE_KEY);
    if (stored && VALID_KEYS.has(stored)) return stored as SearchTabKey;
  } catch {
    // localStorage unavailable (private browsing, disabled storage, etc.) — fall back to default.
  }
  return DEFAULT_SEARCH_TAB;
}

interface UseHomeSearchTabReturn {
  activeTab: SearchTabKey;
  setActiveTab: (tab: SearchTabKey) => void;
}

export function useHomeSearchTab(): UseHomeSearchTabReturn {
  const [activeTab, setActiveTabState] = useState<SearchTabKey>(readStoredTab);

  const setActiveTab = useCallback((tab: SearchTabKey) => {
    setActiveTabState(tab);
    try {
      window.localStorage.setItem(HOME_SEARCH_TAB_STORAGE_KEY, tab);
    } catch {
      // ignore — persistence is a nice-to-have, not required for the tab to work this session.
    }
  }, []);

  return { activeTab, setActiveTab };
}
