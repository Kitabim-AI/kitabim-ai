import App from '@/src/App';
import * as AppContextModule from '@/src/context/AppContext';
import { PersistenceService } from '@/src/services/persistenceService';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/context/AppContext', () => ({
  AppProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAppContext: vi.fn(),
}));

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookById: vi.fn(),
  }
}));

vi.mock('@/src/components/layout/Shell', () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/src/components/library/HomeView', () => ({
  HomeView: () => <div>home-view</div>,
}));

vi.mock('@/src/components/library/LibraryView', () => ({
  LibraryView: () => <div>library-view</div>,
}));

vi.mock('@/src/components/admin/AdminView', () => ({
  AdminView: () => <div>admin-view</div>,
}));

vi.mock('@/src/components/admin/AdminTabs', () => ({
  AdminTabs: ({ bookManagementPanel }: { bookManagementPanel: React.ReactNode }) => <div>{bookManagementPanel}</div>,
}));

vi.mock('@/src/components/reader/ReaderView', () => ({
  ReaderView: () => <div>reader-view</div>,
}));

vi.mock('@/src/components/chat/ChatInterface', () => ({
  ChatInterface: ({ onClose }: { onClose?: () => void }) => (
    <div>
      <div>chat-view</div>
      <button onClick={onClose}>close-chat</button>
    </div>
  ),
}));

vi.mock('@/src/components/pages/JoinUsView', () => ({
  default: () => <div>join-us-view</div>,
}));

vi.mock('@/src/components/spell-check', () => ({
  SpellCheckView: () => <div>spell-check-view</div>,
}));

const baseContext = {
  view: 'home',
  selectedBook: null,
  setSelectedBook: vi.fn(),
  books: [],
  totalReady: 0,
  chat: {
    chatMessages: [],
    chatInput: '',
    setChatInput: vi.fn(),
    handleSendMessage: vi.fn(),
    isChatting: false,
    streamingMessage: '',
    usageStatus: null,
    chatContainerRef: { current: null },
  },
  refreshLibrary: vi.fn(),
  setView: vi.fn(),
  previousView: 'library',
};

beforeEach(() => {
  vi.clearAllMocks();
});

test('App renders the active view from app context', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  const { rerender } = render(<App />);

  expect(screen.getByText('home-view')).toBeInTheDocument();

  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'admin',
  } as any);
  rerender(<App />);
  expect(screen.getByText('admin-view')).toBeInTheDocument();

  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'reader',
    selectedBook: { id: '1' },
  } as any);
  rerender(<App />);
  expect(screen.getByText('reader-view')).toBeInTheDocument();
});

test('App closes global chat back to the previous view', () => {
  const setView = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'global-chat',
    previousView: 'library',
    setView,
  } as any);

  render(<App />);

  fireEvent.click(screen.getByText('close-chat'));
  expect(setView).toHaveBeenCalledWith('library');
});

test('App polls selected book immediately while admin view is processing', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue({ id: '1', status: 'ready', pages: [] } as any);
  const setSelectedBook = vi.fn();

  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'admin',
    setSelectedBook,
    selectedBook: {
      id: '1',
      status: 'ocr_processing',
      pages: [{ pageNumber: 1, status: 'pending' }],
    },
  } as any);

  render(<App />);

  await waitFor(() => {
    expect(PersistenceService.getBookById).toHaveBeenCalledWith('1');
    expect(setSelectedBook).toHaveBeenCalledWith({ id: '1', status: 'ready', pages: [] });
  });
});
