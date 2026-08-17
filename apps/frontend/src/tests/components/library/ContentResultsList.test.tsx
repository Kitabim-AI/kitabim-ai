import { ContentResultsList } from '@/src/components/library/ContentResultsList';
import * as AuthModule from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { ContentSearchHit } from '@/src/services/searchTabsService';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

const mockHits: ContentSearchHit[] = [
  {
    id: 'hit-1',
    bookId: 'book-1',
    bookTitle: 'Sample Book',
    bookAuthor: 'Sample Author',
    pageNumber: 5,
    snippet: 'This is a test search result snippet text.',
  },
];

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderContentResultsList = () =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <ContentResultsList
        hits={mockHits}
        isLoading={false}
        hasQuery={true}
        query="test"
        onOpenHit={vi.fn()}
      />
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
});

test('disables selection and prevents copy for guest users', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: false,
    user: null,
  } as any);

  renderContentResultsList();

  const snippetElement = screen.getByTestId('snippet-container');
  expect(snippetElement).toHaveClass('select-none');

  const copyEvent = new Event('copy', { bubbles: true, cancelable: true });
  const preventDefaultSpy = vi.spyOn(copyEvent, 'preventDefault');
  fireEvent(snippetElement, copyEvent);
  expect(preventDefaultSpy).toHaveBeenCalled();
});

test('allows selection and copying for authenticated users', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { role: 'reader' },
  } as any);

  renderContentResultsList();

  const snippetElement = screen.getByTestId('snippet-container');
  expect(snippetElement).not.toHaveClass('select-none');

  const copyEvent = new Event('copy', { bubbles: true, cancelable: true });
  const preventDefaultSpy = vi.spyOn(copyEvent, 'preventDefault');
  fireEvent(snippetElement, copyEvent);
  expect(preventDefaultSpy).not.toHaveBeenCalled();
});

test('renders share button as icon-only at top header and opens share modal on click', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { role: 'reader' },
  } as any);

  renderContentResultsList();

  const shareButton = screen.getByTitle('share.shareSearchResult');
  expect(shareButton).toBeInTheDocument();
  expect(shareButton.textContent).toBe('');

  fireEvent.click(shareButton);
  expect(screen.getAllByText('Sample Book').length).toBeGreaterThan(1);
});

