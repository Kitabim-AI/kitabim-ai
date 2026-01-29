import { render, screen, fireEvent } from '@testing-library/react';
import { BookCard } from '../components/library/BookCard';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '../types';

const mockBook: Book = {
  id: '1',
  title: 'Test Book',
  author: 'Test Author',
  totalPages: 100,
  results: [],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'hash123'
};

test('BookCard renders book details correctly', () => {
  render(<BookCard book={mockBook} onClick={vi.fn()} onDelete={vi.fn()} />);

  expect(screen.getAllByText('Test Book').length).toBeGreaterThan(0);
  expect(screen.getByText('Test Author')).toBeInTheDocument();
});

test('BookCard appends volume to title when present', () => {
  const volumeBook: Book = { ...mockBook, volume: 1 };
  render(<BookCard book={volumeBook} onClick={vi.fn()} onDelete={vi.fn()} />);

  expect(screen.getAllByText('Test Book (1-قىسىم)').length).toBeGreaterThan(0);
});

test('BookCard handles click event', () => {
  const onClick = vi.fn();
  render(<BookCard book={mockBook} onClick={onClick} onDelete={vi.fn()} />);

  fireEvent.click(screen.getAllByText('Test Book')[0]);
  expect(onClick).toHaveBeenCalledWith(mockBook);
});

test('BookCard handles delete event', () => {
  const onDelete = vi.fn();
  render(<BookCard book={mockBook} onClick={vi.fn()} onDelete={onDelete} />);

  // The trash button is initially hidden (opacity-0), but we can find it in the DOM
  const deleteBtn = screen.getByRole('button');
  fireEvent.click(deleteBtn);
  expect(onDelete).toHaveBeenCalledWith('1');
});

test('BookCard shows processing state', () => {
  const processingBook: Book = { ...mockBook, status: 'processing' };
  render(<BookCard book={processingBook} onClick={vi.fn()} onDelete={vi.fn()} />);

  expect(screen.getAllByText('PROCESSING').length).toBeGreaterThan(0);
  // Lucide loader should be present
  // Note: Finding by SVG or internal class is brittle, but checking for text is good.
});
