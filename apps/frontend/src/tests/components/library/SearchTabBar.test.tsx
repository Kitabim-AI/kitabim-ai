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

test('renders the first 6 tabs plus a page toggle on page 1', () => {
  renderTabBar();

  SEARCH_TABS.slice(0, 6).forEach((tabDef) => {
    expect(screen.getByText(tabDef.labelKey)).toBeInTheDocument();
  });
  SEARCH_TABS.slice(6).forEach((tabDef) => {
    expect(screen.queryByText(tabDef.labelKey)).not.toBeInTheDocument();
  });
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('...');
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

test('clicking the toggle swaps to page 2, revealing the remaining tabs with a back control', () => {
  renderTabBar();
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));

  SEARCH_TABS.slice(6).forEach((tabDef) => {
    expect(screen.getByText(tabDef.labelKey)).toBeInTheDocument();
  });
  SEARCH_TABS.slice(0, 6).forEach((tabDef) => {
    expect(screen.queryByText(tabDef.labelKey)).not.toBeInTheDocument();
  });
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('common.back');
});

test('clicking back on page 2 returns to page 1', () => {
  renderTabBar();
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));

  expect(screen.getByText('home.tabs.ask')).toBeInTheDocument();
  expect(screen.queryByText('home.tabs.enUg')).not.toBeInTheDocument();
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('...');
});

test('selecting a tab on page 2 calls onChange correctly', () => {
  const { onChange } = renderTabBar();
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));
  fireEvent.click(screen.getByText('home.tabs.proverbs'));
  expect(onChange).toHaveBeenCalledWith('proverbs');
});

test('the page toggle never carries aria-pressed and never calls onChange', () => {
  const { onChange } = renderTabBar();
  const toggle = screen.getByTestId('search-tab-page-toggle');
  expect(toggle).not.toHaveAttribute('aria-pressed');
  fireEvent.click(toggle);
  expect(onChange).not.toHaveBeenCalled();
});

test('always starts on page 1 even when the active tab is on page 2', () => {
  renderTabBar('proverbs');
  expect(screen.getByText('home.tabs.ask')).toBeInTheDocument();
  expect(screen.queryByText('home.tabs.proverbs')).not.toBeInTheDocument();
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('...');
});
