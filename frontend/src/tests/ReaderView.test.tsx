import { render, screen, fireEvent } from '@testing-library/react';
import { ReaderView } from '../components/reader/ReaderView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '../types';

const mockBook: Book = {
  id: '1',
  title: 'Reader Book',
  author: 'Author',
  totalPages: 2,
  results: [
    { pageNumber: 1, text: 'Page 1 content', status: 'completed' },
    { pageNumber: 2, text: 'Page 2 content', status: 'completed' }
  ],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'hash',
  tags: ['History']
};

test('ReaderView renders book content and controls', () => {
  const ref = { current: document.createElement('div') };
  render(
    <ReaderView
      selectedBook={mockBook}
      isEditing={false}
      setIsEditing={vi.fn()}
      editContent=""
      setEditContent={vi.fn()}
      onSaveCorrections={vi.fn()}
      fontSize={18}
      setFontSize={vi.fn()}
      onClose={vi.fn()}
      onReprocess={vi.fn()}
      onReProcessPage={vi.fn()}
      onUpdatePage={vi.fn()}
      currentPage={1}
      setCurrentPage={vi.fn()}
      editingPageNum={null}
      setEditingPageNum={vi.fn()}
      tempPageText=""
      setTempPageText={vi.fn()}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByText('Reader Book')).toBeInTheDocument();
  expect(screen.getByText('History')).toBeInTheDocument();
  expect(screen.getByText('Page 1 content')).toBeInTheDocument();
  expect(screen.getByText('Page 2 content')).toBeInTheDocument();
});

test('ReaderView handles font size changes', () => {
  const setFontSize = vi.fn();
  const ref = { current: document.createElement('div') };
  render(
    <ReaderView
      selectedBook={mockBook}
      isEditing={false}
      setIsEditing={vi.fn()}
      editContent=""
      setEditContent={vi.fn()}
      onSaveCorrections={vi.fn()}
      fontSize={18}
      setFontSize={setFontSize}
      onClose={vi.fn()}
      onReprocess={vi.fn()}
      onReProcessPage={vi.fn()}
      onUpdatePage={vi.fn()}
      currentPage={1}
      setCurrentPage={vi.fn()}
      editingPageNum={null}
      setEditingPageNum={vi.fn()}
      tempPageText=""
      setTempPageText={vi.fn()}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  const increaseBtn = screen.getByTitle('Increase Font Size');
  const decreaseBtn = screen.getByTitle('Decrease Font Size');

  fireEvent.click(increaseBtn);
  expect(setFontSize).toHaveBeenCalled();

  fireEvent.click(decreaseBtn);
  expect(setFontSize).toHaveBeenCalled();
});

test('ReaderView enters and exits global edit mode', () => {
  const setIsEditing = vi.fn();
  const ref = { current: document.createElement('div') };
  const { rerender } = render(
    <ReaderView
      selectedBook={mockBook}
      isEditing={false}
      setIsEditing={setIsEditing}
      editContent=""
      setEditContent={vi.fn()}
      onSaveCorrections={vi.fn()}
      fontSize={18}
      setFontSize={vi.fn()}
      onClose={vi.fn()}
      onReprocess={vi.fn()}
      onReProcessPage={vi.fn()}
      onUpdatePage={vi.fn()}
      currentPage={1}
      setCurrentPage={vi.fn()}
      editingPageNum={null}
      setEditingPageNum={vi.fn()}
      tempPageText=""
      setTempPageText={vi.fn()}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  const editBtn = screen.getByText('Global Edit');
  fireEvent.click(editBtn);
  expect(setIsEditing).toHaveBeenCalledWith(true);

  rerender(
    <ReaderView
      selectedBook={mockBook}
      isEditing={true}
      setIsEditing={setIsEditing}
      editContent="Sample Edit"
      setEditContent={vi.fn()}
      onSaveCorrections={vi.fn()}
      fontSize={18}
      setFontSize={vi.fn()}
      onClose={vi.fn()}
      onReprocess={vi.fn()}
      onReProcessPage={vi.fn()}
      onUpdatePage={vi.fn()}
      currentPage={1}
      setCurrentPage={vi.fn()}
      editingPageNum={null}
      setEditingPageNum={vi.fn()}
      tempPageText=""
      setTempPageText={vi.fn()}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByDisplayValue('Sample Edit')).toBeInTheDocument();
  expect(screen.getByText('Update Knowledge Base')).toBeInTheDocument();
});
