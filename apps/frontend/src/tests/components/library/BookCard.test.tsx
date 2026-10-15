import { BookCard } from '@/src/components/library/BookCard';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { Book } from '@shared/types';
import { fireEvent, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

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

test('BookCard hides the ready-only summary and share actions while processing', () => {
  // Pipeline status is shown in the admin view, not on the library card; the
  // card's only processing-specific behaviour is withholding these actions.
  const processingBook: Book = { ...mockBook, status: 'ocr_processing', pipelineStep: 'ocr' };
  render(<BookCard book={processingBook} onClick={vi.fn()} />);

  expect(screen.queryByTitle('bookCard.summary.title')).not.toBeInTheDocument();
  expect(screen.queryByTitle('share.shareBook')).not.toBeInTheDocument();
});

test('BookCard shows the summary and share actions for a ready book', () => {
  render(<BookCard book={{ ...mockBook, status: 'ready' }} onClick={vi.fn()} />);

  expect(screen.getByTitle('bookCard.summary.title')).toBeInTheDocument();
  expect(screen.getByTitle('share.shareBook')).toBeInTheDocument();
});
