import { screen } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { LibraryView } from '@/src/components/library/LibraryView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';
import * as AppContextModule from '@/src/context/AppContext';

vi.mock('@/src/components/common/ProverbDisplay', () => ({
  ProverbDisplay: () => <div>proverb</div>,
}));

const mockBooks: Book[] = [
  { id: '1', title: 'Book 1', author: 'Author 1', totalPages: 10, pages: [], status: 'ready', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h1' },
  { id: '2', title: 'Book 2', author: 'Author 2', totalPages: 20, pages: [], status: 'ocr_processing', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h2' }
];

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return {
    ...actual as any,
    useAppContext: vi.fn(),
  };
});

test('LibraryView renders books and header', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
  } as any);

  render(<LibraryView />);

  expect(screen.getByText(/library\.title/i)).toBeInTheDocument();
  expect(screen.getAllByText('Book 1').length).toBeGreaterThan(0);
});

test('LibraryView shows empty state', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: [],
    totalReady: 0,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
  } as any);

  render(<LibraryView />);

  expect(screen.getByText('library.empty.title')).toBeInTheDocument();
});
