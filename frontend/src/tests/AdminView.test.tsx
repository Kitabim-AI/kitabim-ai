import { render, screen, fireEvent } from '@testing-library/react';
import { AdminView } from '../components/admin/AdminView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '../types';

const mockBooks: Book[] = [
  {
    id: '1',
    title: 'Admin Book',
    author: 'Author',
    totalPages: 5,
    results: [
      { pageNumber: 1, status: 'completed' },
      { pageNumber: 2, status: 'completed' }
    ],
    status: 'ready',
    uploadDate: new Date(),
    lastUpdated: new Date(),
    contentHash: 'h',
    series: ['Series1'],
    categories: ['Cat1']
  }
];

test('AdminView renders table and data', () => {
  render(
    <AdminView
      books={mockBooks}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onReprocess={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookSeriesId={null} setEditingBookSeriesId={vi.fn()}
      editingSeriesList={[]} setEditingSeriesList={vi.fn()}
      tempSeries="" setTempSeries={vi.fn()} handleSaveSeries={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  expect(screen.getByText('Kitabim Processing Pipeline')).toBeInTheDocument();
  expect(screen.getByText('Admin Book')).toBeInTheDocument();
  expect(screen.getByText('Series1')).toBeInTheDocument();
  expect(screen.getByText('Cat1')).toBeInTheDocument();
  expect(screen.getByText('2/5 pages')).toBeInTheDocument(); // Progress
});

test('AdminView shows upload state', () => {
  render(
    <AdminView
      books={[]}
      isCheckingGlobal={true}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={0}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onReprocess={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookSeriesId={null} setEditingBookSeriesId={vi.fn()}
      editingSeriesList={[]} setEditingSeriesList={vi.fn()}
      tempSeries="" setTempSeries={vi.fn()} handleSaveSeries={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  expect(screen.getByText(/Uploading to Server/i)).toBeInTheDocument();
});

test('AdminView handles sorting', () => {
  const toggleSort = vi.fn();
  render(
    <AdminView
      books={mockBooks}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={toggleSort}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onReprocess={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookSeriesId={null} setEditingBookSeriesId={vi.fn()}
      editingSeriesList={[]} setEditingSeriesList={vi.fn()}
      tempSeries="" setTempSeries={vi.fn()} handleSaveSeries={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const docHeader = screen.getByText('Document');
  fireEvent.click(docHeader);
  expect(toggleSort).toHaveBeenCalledWith('title');
});

test('AdminView enters series edit mode', () => {
  const setEditingBookSeriesId = vi.fn();
  render(
    <AdminView
      books={mockBooks}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onReprocess={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookSeriesId={null} setEditingBookSeriesId={setEditingBookSeriesId}
      editingSeriesList={[]} setEditingSeriesList={vi.fn()}
      tempSeries="" setTempSeries={vi.fn()} handleSaveSeries={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const seriesArea = screen.getByText('Series1');
  fireEvent.click(seriesArea);
  expect(setEditingBookSeriesId).toHaveBeenCalledWith('1');
});
