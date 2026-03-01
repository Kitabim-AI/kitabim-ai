import { render, screen, fireEvent } from '@testing-library/react';
import { ReaderView } from '../components/reader/ReaderView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';

const mockUseSpellCheck = vi.fn();
vi.mock('../hooks/useSpellCheck', () => ({
  useSpellCheck: (...args: any[]) => mockUseSpellCheck(...args),
}));

const mockBook: Book = {
  id: '1',
  title: 'Reader Book',
  author: 'Author',
  totalPages: 2,
  pages: [
    { pageNumber: 1, text: 'Page 1 content', status: 'ocr_done' },
    { pageNumber: 2, text: 'Page 2 content', status: 'ocr_done' }
  ],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'hash',
  tags: ['History']
};

const baseSpellCheck = {
  isChecking: false,
  spellCheckResult: null,
  appliedCorrections: new Set<string>(),
  ignoredCorrections: new Set<string>(),
  runSpellCheck: vi.fn(),
  applyCorrection: vi.fn((_c: any, text: string) => text),
  ignoreCorrection: vi.fn(),
  resetSpellCheck: vi.fn(),
};

test('ReaderView renders book content and controls', () => {
  mockUseSpellCheck.mockReturnValue(baseSpellCheck);
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
      setModal={vi.fn()}
    />
  );

  expect(screen.getByText('Reader Book')).toBeInTheDocument();
  expect(screen.getByText('History')).toBeInTheDocument();
  expect(screen.getByText('Page 1 content')).toBeInTheDocument();
  expect(screen.getByText('Page 2 content')).toBeInTheDocument();
});

test('ReaderView handles font size changes', () => {
  mockUseSpellCheck.mockReturnValue(baseSpellCheck);
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
      setModal={vi.fn()}
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
  mockUseSpellCheck.mockReturnValue(baseSpellCheck);
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
      setModal={vi.fn()}
    />
  );

  const editBtn = screen.getByText('EDIT BOOK');
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
      setModal={vi.fn()}
    />
  );

  expect(screen.getByDisplayValue('Sample Edit')).toBeInTheDocument();
  expect(screen.getByText('UPDATE KNOWLEDGE BASE')).toBeInTheDocument();
});

test('ReaderView saves and cancels page edits', () => {
  const resetSpellCheck = vi.fn();
  mockUseSpellCheck.mockReturnValue({ ...baseSpellCheck, resetSpellCheck });

  const setEditingPageNum = vi.fn();
  const onUpdatePage = vi.fn();
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
      onReProcessPage={vi.fn()}
      onUpdatePage={onUpdatePage}
      currentPage={1}
      setCurrentPage={vi.fn()}
      editingPageNum={1}
      setEditingPageNum={setEditingPageNum}
      tempPageText="Edited text"
      setTempPageText={vi.fn()}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
      setModal={vi.fn()}
    />
  );

  fireEvent.click(screen.getByText(/SAVE & VERIFY PAGE/i));
  expect(onUpdatePage).toHaveBeenCalledWith('1', 1, 'Edited text');
  expect(resetSpellCheck).toHaveBeenCalled();

  fireEvent.click(screen.getByText(/CANCEL/i));
  expect(setEditingPageNum).toHaveBeenCalledWith(null);
});

test('ReaderView triggers page actions and close logic', () => {
  mockUseSpellCheck.mockReturnValue({ ...baseSpellCheck });

  const setEditingPageNum = vi.fn();
  const setTempPageText = vi.fn();
  const onReProcessPage = vi.fn();
  const onClose = vi.fn();
  const setModal = vi.fn();
  const setIsEditing = vi.fn();
  const ref = { current: document.createElement('div') };

  const verifiedBook: Book = {
    ...mockBook,
    pages: [{ pageNumber: 1, text: 'Page 1 content', status: 'ocr_done', isVerified: true }]
  };

  render(
    <ReaderView
      selectedBook={verifiedBook}
      isEditing={false}
      setIsEditing={setIsEditing}
      editContent=""
      setEditContent={vi.fn()}
      onSaveCorrections={vi.fn()}
      fontSize={18}
      setFontSize={vi.fn()}
      onClose={onClose}
      onReProcessPage={onReProcessPage}
      onUpdatePage={vi.fn()}
      currentPage={1}
      setCurrentPage={vi.fn()}
      editingPageNum={null}
      setEditingPageNum={setEditingPageNum}
      tempPageText=""
      setTempPageText={setTempPageText}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
      setModal={setModal}
    />
  );

  fireEvent.click(screen.getByText(/RE-OCR PAGE/i));
  expect(setModal).toHaveBeenCalled();
  const modalConfig = setModal.mock.calls[0][0];
  modalConfig.onConfirm();
  expect(onReProcessPage).toHaveBeenCalledWith('1', 1);

  fireEvent.click(screen.getByText(/EDIT PAGE/i));
  expect(setEditingPageNum).toHaveBeenCalledWith(1);
  expect(setTempPageText).toHaveBeenCalledWith('Page 1 content');

  fireEvent.click(screen.getByText(/SPELL CHECK/i));
  expect(setEditingPageNum).toHaveBeenCalledWith(1);
  expect(setTempPageText).toHaveBeenCalledWith('Page 1 content');

  fireEvent.click(screen.getByLabelText('Close Reader'));
  expect(onClose).toHaveBeenCalled();
});
