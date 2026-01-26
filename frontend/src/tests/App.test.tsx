import { render, screen, fireEvent, act } from '@testing-library/react';
import App from '../App';
import { expect, test, vi } from 'vitest';
import React from 'react';

// Mock the hooks
vi.mock('../hooks/useBooks', () => ({
  useBooks: () => ({
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
    setBooks: vi.fn()
  })
}));

vi.mock('../hooks/useChat', () => ({
  useChat: () => ({
    chatMessages: [],
    chatInput: '',
    setChatInput: vi.fn(),
    isChatting: false,
    handleSendMessage: vi.fn(),
    clearChat: vi.fn(),
    chatContainerRef: { current: null }
  })
}));

vi.mock('../hooks/useBookActions', () => ({
  useBookActions: () => ({
    isCheckingGlobal: false,
    handleFileUpload: vi.fn(),
    handleReprocess: vi.fn(),
    handleReProcessPage: vi.fn(),
    handleUpdatePage: vi.fn(),
    openReader: vi.fn(),
    saveCorrections: vi.fn(),
    handleDeleteBook: vi.fn(),
    handleSaveTags: vi.fn()
  })
}));

test('App renders and navigates between views', () => {
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
  expect(screen.getByText(/Kitabim Global Mind/i)).toBeInTheDocument();
});
