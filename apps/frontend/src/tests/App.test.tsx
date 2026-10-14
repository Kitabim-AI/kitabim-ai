import App from '@/src/App';
import * as AppContextModule from '@/src/context/AppContext';
import * as AuthModule from '@/src/hooks/useAuth';
import { AuthProvider } from '@/src/hooks/useAuth';
import { PersistenceService } from '@/src/services/persistenceService';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

// These tests cover which view App renders, not login. Auth is mocked as a
// signed-in editor by default (admin and spell-check are editor-only); the
// real AuthProvider would also fire /api/auth/refresh requests.
vi.mock('@/src/hooks/useAuth', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuth: vi.fn(),
  useIsEditor: vi.fn(),
}));

// Passed as `wrapper` so rerender() keeps it too.
const renderApp = (ui: React.ReactElement) => render(ui, { wrapper: AuthProvider });

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
  vi.mocked(AuthModule.useAuth).mockReturnValue({ isAuthenticated: true, isLoading: false } as any);
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
});

test('App renders the active view from app context', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  const { rerender } = renderApp(<App />);

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

test('App keeps HomeView mounted (hidden) behind the reader when opened from home, so search state and fetched results are not lost', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'reader',
    previousView: 'home',
    selectedBook: { id: '1' },
  } as any);
  renderApp(<App />);

  expect(screen.getByText('reader-view')).toBeInTheDocument();
  const homeView = screen.getByText('home-view');
  expect(homeView).toBeInTheDocument();
  // Hidden, not removed — HomeView's own state (tab, query, fetched results) survives underneath.
  expect(homeView.closest('.hidden')).not.toBeNull();
});

test('App does not keep HomeView mounted when navigating to a different main view', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'library',
    previousView: 'home',
  } as any);
  renderApp(<App />);

  expect(screen.getByText('library-view')).toBeInTheDocument();
  expect(screen.queryByText('home-view')).not.toBeInTheDocument();
});

test('App renders the global chat view', () => {
  // Global chat is a full page left via the navbar; it has no close button
  // (the old onClose → previousView flow was removed with the chat redesign).
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'global-chat',
  } as any);

  renderApp(<App />);

  expect(screen.getByText('chat-view')).toBeInTheDocument();
});

test('App redirects a non-editor away from the admin view', () => {
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(false);
  const setView = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...baseContext,
    view: 'admin',
    setView,
  } as any);

  renderApp(<App />);

  expect(screen.queryByText('admin-view')).not.toBeInTheDocument();
  expect(setView).toHaveBeenCalledWith('home');
});

test('App polls a processing book every 30 seconds in the admin view', async () => {
  vi.useFakeTimers();
  try {
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

    renderApp(<App />);

    // No immediate fetch: the book was just loaded when it was opened.
    expect(PersistenceService.getBookById).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(30000);

    expect(PersistenceService.getBookById).toHaveBeenCalledWith('1');
    expect(setSelectedBook).toHaveBeenCalledWith({ id: '1', status: 'ready', pages: [] });
  } finally {
    vi.useRealTimers();
  }
});
