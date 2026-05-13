import { ReaderView } from '@/src/components/reader/ReaderView';
import * as AppContextModule from '@/src/context/AppContext';
import * as AuthModule from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { PersistenceService } from '@/src/services/persistenceService';
import { Book } from '@shared/types';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: vi.fn(),
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
  useIsEditor: vi.fn(),
}));

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookContent: vi.fn(),
    getBookPages: vi.fn(),
    downloadBook: vi.fn(),
  }
}));

vi.mock('@/src/components/chat/ChatInterface', () => ({
  ChatInterface: () => <div>chat-panel</div>,
}));

vi.mock('@/src/components/ui/GlassPanel', () => ({
  GlassPanel: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/src/components/reader/VirtualScrollReader', () => ({
  default: () => <div>virtual-reader</div>,
}));

vi.mock('@/src/components/reader/PageItem', () => ({
  PageItem: ({
    page,
    isEditing,
    onEdit,
    onSave,
    onCancel,
    onReprocess,
  }: any) => (
    <div>
      <div>{page.text}</div>
      {!isEditing && <button onClick={onEdit}>edit-{page.pageNumber}</button>}
      {isEditing && <button onClick={onSave}>save-{page.pageNumber}</button>}
      {isEditing && <button onClick={onCancel}>cancel-{page.pageNumber}</button>}
      <button onClick={onReprocess}>reprocess-{page.pageNumber}</button>
    </div>
  ),
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

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string, params?: Record<string, string | number>) => {
    if (params) {
      return Object.entries(params).reduce(
        (value, [paramKey, paramValue]) => value.replace(`{{${paramKey}}}`, String(paramValue)),
        key
      );
    }
    return key;
  },
};

const createContextValue = () => ({
  selectedBook: mockBook,
  view: 'reader',
  setView: vi.fn(),
  previousView: 'library',
  currentPage: 1,
  setCurrentPage: vi.fn(),
  chat: {
    chatMessages: [],
    chatInput: '',
    setChatInput: vi.fn(),
    handleSendMessage: vi.fn(),
    isChatting: false,
    streamingMessage: '',
    usageStatus: null,
    chatContainerRef: { current: document.createElement('div') },
  },
  bookActions: {
    saveCorrections: vi.fn(),
    handleUpdatePage: vi.fn().mockResolvedValue(undefined),
    handleReProcessPage: vi.fn(),
  },
  setModal: vi.fn(),
  setIsReaderFullscreen: vi.fn(),
  fontSize: 18,
  setFontSize: vi.fn(),
});

const renderReader = () =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <ReaderView />
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'IntersectionObserver', {
    writable: true,
    value: class {
      observe() {}
      disconnect() {}
      unobserve() {}
    }
  });
  window.scrollTo = vi.fn();
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { role: 'editor' },
  } as any);
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
});

test('ReaderView renders book content and controls', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(createContextValue() as any);

  renderReader();

  expect(screen.getByText('Reader Book')).toBeInTheDocument();
  expect(screen.getByText('Page 1 content')).toBeInTheDocument();
  expect(screen.getByText('Page 2 content')).toBeInTheDocument();
  expect(screen.getByText('chat-panel')).toBeInTheDocument();
});

test('ReaderView handles font size changes', () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);

  renderReader();

  const fontControls = screen.getByText('18').parentElement;
  const buttons = fontControls?.querySelectorAll('button') || [];
  fireEvent.click(buttons[0] as HTMLButtonElement);
  fireEvent.click(buttons[1] as HTMLButtonElement);

  expect(context.setFontSize).toHaveBeenCalledTimes(3);
});

test('ReaderView enters global edit mode and saves corrections', async () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);
  vi.mocked(PersistenceService.getBookContent).mockResolvedValue('[[PAGE 1]]\nFetched content' as any);

  renderReader();

  fireEvent.click(screen.getByText('reader.editBook'));

  await waitFor(() => {
    expect(PersistenceService.getBookContent).toHaveBeenCalledWith('1');
  });

  const textarea = await screen.findByRole('textbox');
  expect(textarea).toHaveValue('[[PAGE 1]]\nFetched content');

  fireEvent.click(screen.getByText('common.save'));
  expect(context.bookActions.saveCorrections).toHaveBeenCalledWith(
    mockBook,
    '[[PAGE 1]]\nFetched content',
    expect.any(Function)
  );
});

test('ReaderView saves and cancels page edits', async () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);

  renderReader();

  fireEvent.click(screen.getByText('edit-1'));
  fireEvent.click(await screen.findByText('save-1'));

  await waitFor(() => {
    expect(context.bookActions.handleUpdatePage).toHaveBeenCalledWith('1', 1, 'Page 1 content', expect.any(Function));
  });

  fireEvent.click(screen.getByText('cancel-1'));
});

test('ReaderView triggers page reprocess actions', () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);

  renderReader();

  fireEvent.click(screen.getByText('reprocess-1'));
  expect(context.bookActions.handleReProcessPage).toHaveBeenCalledWith('1', 1);
});
