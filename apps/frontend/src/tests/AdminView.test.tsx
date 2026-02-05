import { render, screen, fireEvent } from '@testing-library/react';
import { AdminView } from '../components/admin/AdminView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';

const mockBooks: Book[] = [
  {
    id: '1',
    title: 'Admin Book',
    author: 'Author',
    volume: 1,
    totalPages: 5,
    results: [
      { pageNumber: 1, status: 'completed' },
      { pageNumber: 2, status: 'completed' }
    ],
    status: 'ready',
    uploadDate: new Date(),
    lastUpdated: new Date(),
    contentHash: 'h',
    categories: ['Cat1'],
  }
];

const mockBooksEmpty: Book[] = [
  {
    id: '2',
    title: 'Empty Book',
    author: 'Unknown Author',
    totalPages: 1,
    results: [{ pageNumber: 1, status: 'completed' }],
    status: 'ready',
    uploadDate: new Date(),
    lastUpdated: new Date(),
    contentHash: 'h2',
    categories: []
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
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  expect(screen.getByText('Kitabim Processing Pipeline')).toBeInTheDocument();
  expect(screen.getByText('Admin Book')).toBeInTheDocument();
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
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  expect(screen.getByText(/Uploading to Server/i)).toBeInTheDocument();
});

test('AdminView edits title and author', () => {
  const handleSaveTitle = vi.fn();
  const handleSaveAuthor = vi.fn();

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
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={'1'} setEditingBookTitleId={vi.fn()}
      tempTitle="New Title" setTempTitle={vi.fn()} handleSaveTitle={handleSaveTitle}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={'1'} setEditingBookAuthorId={vi.fn()}
      tempAuthor="New Author" setTempAuthor={vi.fn()} handleSaveAuthor={handleSaveAuthor}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const saveButtons = screen.getAllByTitle('Save');
  fireEvent.click(saveButtons[0]);
  fireEvent.click(saveButtons[1]);

  expect(handleSaveTitle).toHaveBeenCalledWith('1', 'New Title');
  expect(handleSaveAuthor).toHaveBeenCalledWith('1', 'New Author');
});

test('AdminView disables start OCR when processing', () => {
  const processingBook: Book = { ...mockBooks[0], status: 'processing' };

  render(
    <AdminView
      books={[processingBook]}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const disabledBtns = screen.getAllByTitle('OCR IN PROGRESS');
  expect(disabledBtns.length).toBe(2);
  disabledBtns.forEach(btn => expect(btn).toBeDisabled());
});

test('AdminView opens and closes category editor', () => {
  const setEditingBookCategoriesId = vi.fn();
  const setEditingCategoriesList = vi.fn();

  render(
    <AdminView
      books={mockBooksEmpty}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={setEditingBookCategoriesId}
      editingCategoriesList={[]} setEditingCategoriesList={setEditingCategoriesList}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  fireEvent.click(screen.getByText('Add category...'));
  expect(setEditingBookCategoriesId).toHaveBeenCalledWith('2');
  expect(setEditingCategoriesList).toHaveBeenCalled();
});

test('AdminView renders rag pipeline styling', () => {
  const ragBook: Book = {
    ...mockBooks[0],
    processingStep: 'rag'
  };

  render(
    <AdminView
      books={[ragBook]}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const progressBar = document.querySelector('.bg-amber-500');
  expect(progressBar).not.toBeNull();
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
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const docHeader = screen.getByText('Document');
  fireEvent.click(docHeader);
  expect(toggleSort).toHaveBeenCalledWith('title');
});

test('AdminView enters title edit mode', () => {
  const setEditingBookTitleId = vi.fn();
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
      onStartOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={setEditingBookTitleId}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const titleArea = screen.getByText('Admin Book');
  fireEvent.click(titleArea);
  expect(setEditingBookTitleId).toHaveBeenCalledWith('1');
});

test('AdminView calls action handlers', () => {
  const onOpenReader = vi.fn();
  const onStartOcr = vi.fn();
  const onDeleteBook = vi.fn();
  const onReindex = vi.fn();

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
      onOpenReader={onOpenReader}
      onStartOcr={onStartOcr}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onReindex={onReindex}
      onDeleteBook={onDeleteBook}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={null} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={[]} setEditingCategoriesList={vi.fn()}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  fireEvent.click(screen.getByTitle('VIEW'));
  expect(onOpenReader).toHaveBeenCalledWith(mockBooks[0]);

  fireEvent.click(screen.getByTitle('START LOCAL OCR'));
  expect(onStartOcr).toHaveBeenCalledWith('1', 'local');

  fireEvent.click(screen.getByTitle('START GEMINI OCR'));
  expect(onStartOcr).toHaveBeenCalledWith('1', 'gemini');

  fireEvent.click(screen.getByTitle('RE-INDEX (SEMANTIC CHUNKING)'));
  expect(onReindex).toHaveBeenCalledWith('1');

  fireEvent.click(screen.getByTitle('DELETE'));
  expect(onDeleteBook).toHaveBeenCalledWith('1');
});

test('AdminView saves volume and categories', () => {
  const handleSaveVolume = vi.fn();
  const handleSaveCategories = vi.fn();

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
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={'1'} setEditingBookVolumeId={vi.fn()}
      tempVolume="2" setTempVolume={vi.fn()} handleSaveVolume={handleSaveVolume}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={'1'} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={['Cat1']} setEditingCategoriesList={vi.fn()}
      tempCategories="Cat2" setTempCategories={vi.fn()} handleSaveCategories={handleSaveCategories}
    />
  );

  const saveButtons = screen.getAllByTitle('Save');
  fireEvent.click(saveButtons[0]);
  expect(handleSaveVolume).toHaveBeenCalledWith('1', '2');

  fireEvent.click(saveButtons[1]);
  expect(handleSaveCategories).toHaveBeenCalledWith('1', ['Cat1', 'Cat2']);
});

test('AdminView shows category placeholder and handles backspace', () => {
  const setEditingCategoriesList = vi.fn();

  render(
    <AdminView
      books={mockBooksEmpty}
      isCheckingGlobal={false}
      sortConfig={{ key: 'title', direction: 'asc' }}
      toggleSort={vi.fn()}
      page={1}
      pageSize={10}
      totalBooks={1}
      onPageChange={vi.fn()}
      onPageSizeChange={vi.fn()}
      onOpenReader={vi.fn()}
      onStartOcr={vi.fn()}
      onRetryFailedOcr={vi.fn()}
      onReindex={vi.fn()}
      onDeleteBook={vi.fn()}

      editingBookTitleId={null} setEditingBookTitleId={vi.fn()}
      tempTitle="" setTempTitle={vi.fn()} handleSaveTitle={vi.fn()}

      editingBookVolumeId={null} setEditingBookVolumeId={vi.fn()}
      tempVolume="" setTempVolume={vi.fn()} handleSaveVolume={vi.fn()}

      editingBookAuthorId={null} setEditingBookAuthorId={vi.fn()}
      tempAuthor="" setTempAuthor={vi.fn()} handleSaveAuthor={vi.fn()}

      editingBookCategoriesId={'2'} setEditingBookCategoriesId={vi.fn()}
      editingCategoriesList={['Cat1']} setEditingCategoriesList={setEditingCategoriesList}
      tempCategories="" setTempCategories={vi.fn()} handleSaveCategories={vi.fn()}
    />
  );

  const input = screen.getByPlaceholderText('Add category...');
  fireEvent.keyDown(input, { key: 'Backspace' });
  expect(setEditingCategoriesList).toHaveBeenCalled();
});
