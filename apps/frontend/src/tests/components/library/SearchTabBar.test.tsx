import { SearchTabBar } from '@/src/components/library/SearchTabBar';
import { SEARCH_TABS } from '@/src/components/library/searchTabsConfig';
import { I18nContext } from '@/src/i18n/I18nContext';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderTabBar = (activeTab = 'ask') => {
  const onChange = vi.fn();
  render(
    <I18nContext.Provider value={i18nValue}>
      <SearchTabBar activeTab={activeTab as any} onChange={onChange} />
    </I18nContext.Provider>
  );
  return { onChange };
};

test('renders all 11 tabs on page 1 without pagination toggle', () => {
  renderTabBar();

  SEARCH_TABS.forEach((tabDef) => {
    expect(screen.getByText(tabDef.labelKey)).toBeInTheDocument();
  });
  expect(screen.queryByTestId('search-tab-page-toggle')).not.toBeInTheDocument();
});

test('marks the active tab as pressed', () => {
  renderTabBar('quran');
  expect(screen.getByText('home.tabs.quran').closest('button')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('home.tabs.ask').closest('button')).toHaveAttribute('aria-pressed', 'false');
});

test('clicking a tab calls onChange with its key', () => {
  const { onChange } = renderTabBar('ask');
  fireEvent.click(screen.getByText('home.tabs.dictionary'));
  expect(onChange).toHaveBeenCalledWith('dictionary');
});

test('selecting any tab calls onChange correctly', () => {
  const { onChange } = renderTabBar();
  fireEvent.click(screen.getByText('home.tabs.synonyms'));
  expect(onChange).toHaveBeenCalledWith('synonyms');
});

test('places synonyms tab before spell-check tab', () => {
  const synonymIndex = SEARCH_TABS.findIndex((tab) => tab.key === 'synonyms');
  const spellCheckIndex = SEARCH_TABS.findIndex((tab) => tab.key === 'spell-check');
  expect(synonymIndex).toBeLessThan(spellCheckIndex);
});
