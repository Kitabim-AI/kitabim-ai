import { render, screen } from '@testing-library/react';
import { LibraryView } from '../components/library/LibraryView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';

const mockBooks: Book[] = [
  { id: '1', title: 'Book 1', author: 'Author 1', totalPages: 10, results: [], status: 'ready', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h1' },
  { id: '2', title: 'Book 2', author: 'Author 2', totalPages: 20, results: [], status: 'processing', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h2' }
];

test('LibraryView renders books and header', () => {
  const ref = { current: document.createElement('div') };
  render(
    <LibraryView
      books={mockBooks}
      isLoadingMore={false}
      hasMore={false}
      searchQuery=""
      onBookClick={vi.fn()}
      onDeleteBook={vi.fn()}
      loaderRef={ref}
      loadMore={vi.fn()}
    />
  );

  expect(screen.getByText(/Global Knowledge Base/i)).toBeInTheDocument();
  expect(screen.getAllByText('Book 1').length).toBeGreaterThan(0);
  expect(screen.getAllByText('Book 2').length).toBeGreaterThan(0);
});

test('LibraryView shows empty state', () => {
  const ref = { current: document.createElement('div') };
  render(
    <LibraryView
      books={[]}
      isLoadingMore={false}
      hasMore={false}
      searchQuery=""
      onBookClick={vi.fn()}
      onDeleteBook={vi.fn()}
      loaderRef={ref}
      loadMore={vi.fn()}
    />
  );

  expect(screen.getByText(/No books indexed in the global database yet/i)).toBeInTheDocument();
});

test('LibraryView shows search empty state', () => {
  const ref = { current: document.createElement('div') };
  render(
    <LibraryView
      books={[]}
      isLoadingMore={false}
      hasMore={false}
      searchQuery="unknown book"
      onBookClick={vi.fn()}
      onDeleteBook={vi.fn()}
      loaderRef={ref}
      loadMore={vi.fn()}
    />
  );

  expect(screen.getByText(/No books match your search/i)).toBeInTheDocument();
});

test('LibraryView shows loading state', () => {
  const ref = { current: document.createElement('div') };
  render(
    <LibraryView
      books={mockBooks}
      isLoadingMore={true}
      hasMore={true}
      searchQuery=""
      onBookClick={vi.fn()}
      onDeleteBook={vi.fn()}
      loaderRef={ref}
      loadMore={vi.fn()}
    />
  );

  expect(screen.getByText(/Loading more treasures/i)).toBeInTheDocument();
});
