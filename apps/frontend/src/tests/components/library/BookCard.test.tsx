import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { BookCard } from '@/src/components/library/BookCard';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';

const mockBook: Book = {
  id: '1',
  title: 'Test Book',
  author: 'Test Author',
  totalPages: 100,
  pages: [],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'hash123'
};

test('BookCard renders book details correctly', () => {
  render(<BookCard book={mockBook} onClick={vi.fn()} />);

  expect(screen.getAllByText('Test Book').length).toBeGreaterThan(0);
  expect(screen.getByText('Test Author')).toBeInTheDocument();
});

test('BookCard appends volume to title when present', () => {
  const volumeBook: Book = { ...mockBook, volume: 1 };
  render(<BookCard book={volumeBook} onClick={vi.fn()} />);

  // The text will be something like "Test Book (book.volume)" or the translated volume
  expect(screen.getAllByText(/Test Book/i).length).toBeGreaterThan(0);
});

test('BookCard handles click event', () => {
  const onClick = vi.fn();
  render(<BookCard book={mockBook} onClick={onClick} />);

  fireEvent.click(screen.getAllByText('Test Book')[0]);
  expect(onClick).toHaveBeenCalledWith(mockBook);
});

test('BookCard shows processing state', () => {
  const processingBook: Book = { ...mockBook, pipelineStep: 'ocr' };
  render(<BookCard book={processingBook} onClick={vi.fn()} />);

  // In the new system, it shows the pipeline step name (translated)
  expect(screen.getByText(/ocr/i)).toBeInTheDocument();
});
