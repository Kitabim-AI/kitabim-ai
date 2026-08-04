import { LookupItem, LookupResultsList } from '@/src/components/library/LookupResultsList';
import { I18nContext } from '@/src/i18n/I18nContext';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { expect, test, vi } from 'vitest';

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const items: LookupItem[] = [
  { id: 1, primary: 'قۇتادغۇبىلىك (Qutadghu Bilig)', secondary: 'Ottoman-era wisdom text' },
];

const renderList = (query: string) =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <LookupResultsList items={items} isLoading={false} hasQuery={true} query={query} />
    </I18nContext.Provider>
  );

test('highlights the matched query inside the primary text', () => {
  renderList('Qutadghu');
  const mark = screen.getByText('Qutadghu');
  expect(mark.tagName).toBe('MARK');
});

test('highlights the matched query inside the secondary text', () => {
  renderList('wisdom');
  const mark = screen.getByText('wisdom');
  expect(mark.tagName).toBe('MARK');
});

test('renders plain text with no <mark> when query does not match', () => {
  renderList('nomatch');
  expect(screen.getByText('قۇتادغۇبىلىك (Qutadghu Bilig)')).toBeInTheDocument();
  expect(document.querySelector('mark')).toBeNull();
});
