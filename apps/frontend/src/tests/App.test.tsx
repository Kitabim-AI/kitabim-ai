import { render, screen, fireEvent } from '@testing-library/react';
import App from '../App';
import { expect, test, vi } from 'vitest';
import React from 'react';

const mockUseBooks = vi.fn();
const mockUseChat = vi.fn();
const mockUseBookActions = vi.fn();

vi.mock('../hooks/useBooks', () => ({
  useBooks: (...args: any[]) => mockUseBooks(...args)
}));

vi.mock('../hooks/useChat', () => ({
  useChat: (...args: any[]) => mockUseChat(...args)
}));

vi.mock('../hooks/useBookActions', () => ({
  useBookActions: (...args: any[]) => mockUseBookActions(...args)
}));

test('App renders and navigates between views', () => {
  mockUseBooks.mockReturnValue({
    books: [],
    sortedBooks: [],
    totalBooks: 0,
    totalReady: 0,
    sortConfig: { key: 'title', direction: 'asc' },
    toggleSort: vi.fn(),
    refreshLibrary: vi.fn(),
    loadMoreShelf: vi.fn(),
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    setBooks: vi.fn(),
    isLoading: false
  });

  mockUseChat.mockReturnValue({
    chatMessages: [],
    chatInput: '',
    setChatInput: vi.fn(),
    isChatting: false,
    handleSendMessage: vi.fn(),
    clearChat: vi.fn(),
    chatContainerRef: { current: null }
  });

  mockUseBookActions.mockReturnValue({
    isCheckingGlobal: false,
    handleFileUpload: vi.fn(),
    handleResetFailedPages: vi.fn(),
    handleReProcessPage: vi.fn(),
    handleRevertBook: vi.fn(),
    handleUpdatePage: vi.fn(),
    openReader: vi.fn(),
    saveCorrections: vi.fn(),
    handleDeleteBook: vi.fn(),
    handleSaveTags: vi.fn(),
    handleSaveCategories: vi.fn(),
    handleSaveAuthor: vi.fn(),
    handleSaveTitle: vi.fn(),
    handleSaveVolume: vi.fn()
  });

  render(<App />);

  // Starts in library view
  expect(screen.getByText(/Global Knowledge Base/i)).toBeInTheDocument();

  // Navigate to Admin
  const adminBtn = screen.getByText(/Management/i);
  fireEvent.click(adminBtn);
  expect(screen.getByText(/Kitabim Processing Pipeline/i)).toBeInTheDocument();

  // Navigate to Global Chat
  const chatBtn = screen.getByText(/Global Assistant/i);
  fireEvent.click(chatBtn);
  expect(screen.getAllByText(/كىتابىم خەزىنىسى/i).length).toBeGreaterThan(0);
});

test('App opens reader from library click', () => {
  const book = {
    id: '1',
    title: 'Reader Book',
    author: 'Author',
    totalPages: 1,
    pages: [{ pageNumber: 1, text: 'Page', status: 'ocr_done' }],
    status: 'ready',
    uploadDate: new Date(),
    lastUpdated: new Date(),
    contentHash: 'hash'
  };

  mockUseBooks.mockReturnValue({
    books: [book],
    sortedBooks: [book],
    totalBooks: 1,
    totalReady: 1,
    sortConfig: { key: 'title', direction: 'asc' },
    toggleSort: vi.fn(),
    refreshLibrary: vi.fn(),
    loadMoreShelf: vi.fn(),
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    setBooks: vi.fn(),
    isLoading: false
  });

  mockUseChat.mockReturnValue({
    chatMessages: [],
    chatInput: '',
    setChatInput: vi.fn(),
    isChatting: false,
    handleSendMessage: vi.fn(),
    clearChat: vi.fn(),
    chatContainerRef: { current: null }
  });

  mockUseBookActions.mockImplementation((_refresh: any, _setBooks: any, setSelectedBook: any, setView: any) => ({
    isCheckingGlobal: false,
    handleFileUpload: vi.fn(),
    handleResetFailedPages: vi.fn(),
    handleReProcessPage: vi.fn(),
    handleRevertBook: vi.fn(),
    handleUpdatePage: vi.fn(),
    openReader: (b: any, _setEditContent: any, _setChatMessages: any, _setCurrentPage: any) => {
      setSelectedBook(b);
      setView('reader');
    },
    saveCorrections: vi.fn(),
    handleDeleteBook: vi.fn(),
    handleSaveTags: vi.fn(),
    handleSaveCategories: vi.fn(),
    handleSaveAuthor: vi.fn(),
    handleSaveTitle: vi.fn(),
    handleSaveVolume: vi.fn()
  }));

  render(<App />);

  fireEvent.click(screen.getAllByText('Reader Book')[0]);
  expect(screen.getByText(/EDIT BOOK/i)).toBeInTheDocument();
});

test('App shows loading overlay', () => {
  mockUseBooks.mockReturnValue({
    books: [],
    sortedBooks: [],
    totalBooks: 0,
    totalReady: 0,
    sortConfig: { key: 'title', direction: 'asc' },
    toggleSort: vi.fn(),
    refreshLibrary: vi.fn(),
    loadMoreShelf: vi.fn(),
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    setBooks: vi.fn(),
    isLoading: true
  });

  mockUseChat.mockReturnValue({
    chatMessages: [],
    chatInput: '',
    setChatInput: vi.fn(),
    isChatting: false,
    handleSendMessage: vi.fn(),
    clearChat: vi.fn(),
    chatContainerRef: { current: null }
  });

  mockUseBookActions.mockReturnValue({
    isCheckingGlobal: false,
    handleFileUpload: vi.fn(),
    handleResetFailedPages: vi.fn(),
    handleReProcessPage: vi.fn(),
    handleRevertBook: vi.fn(),
    handleUpdatePage: vi.fn(),
    openReader: vi.fn(),
    saveCorrections: vi.fn(),
    handleDeleteBook: vi.fn(),
    handleSaveTags: vi.fn(),
    handleSaveCategories: vi.fn(),
    handleSaveAuthor: vi.fn(),
    handleSaveTitle: vi.fn(),
    handleSaveVolume: vi.fn()
  });

  render(<App />);
  expect(screen.getByText(/Loading Library/i)).toBeInTheDocument();
});
