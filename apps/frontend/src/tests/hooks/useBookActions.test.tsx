import { useBookActions } from '@/src/hooks/useBookActions';
import { PersistenceService } from '@/src/services/persistenceService';
import { Book } from '@shared/types';
import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    uploadPdf: vi.fn(),
    getBookById: vi.fn(),
    saveBookGlobally: vi.fn(),
    deleteBook: vi.fn(),
    updateBookMetadata: vi.fn(),
    updatePage: vi.fn(),
    resetPage: vi.fn(),
  }
}));

vi.mock('@/src/context/NotificationContext', () => ({
  useNotification: vi.fn(() => ({
    addNotification: vi.fn(),
  })),
}));

vi.mock('@/src/i18n/I18nContext', () => ({
  useI18n: vi.fn(() => ({
    t: (key: string) => key,
  })),
}));

const mockBook: Book = {
  id: '1',
  title: 'T',
  author: 'A',
  totalPages: 1,
  pages: [{ pageNumber: 1, text: 'Old Text', status: 'ocr_done' }],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'h'
};

const createHook = (overrides?: { currentView?: string }) => {
  const refreshLibrary = vi.fn().mockResolvedValue(undefined);
  const setBooks = vi.fn();
  const setSelectedBook = vi.fn();
  const setView = vi.fn();
  const setModal = vi.fn();
  const setChatMessages = vi.fn();
  const setCurrentPage = vi.fn();

  const hook = renderHook(() =>
    useBookActions(
      refreshLibrary,
      setBooks,
      setSelectedBook,
      overrides?.currentView ?? 'library',
      setView,
      setModal,
      setChatMessages,
      setCurrentPage
    )
  );

  return {
    ...hook,
    refreshLibrary,
    setBooks,
    setSelectedBook,
    setView,
    setModal,
    setChatMessages,
    setCurrentPage,
  };
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

test('useBookActions handles file upload', async () => {
  vi.mocked(PersistenceService.uploadPdf).mockResolvedValue({ status: 'uploaded' } as any);
  const { result, refreshLibrary, setView } = createHook({ currentView: 'library' });

  const file = new File(['%PDF-1.4'], 'test.pdf', { type: 'application/pdf' });
  const event = { target: { files: [file], value: 'set' } } as any;

  await act(async () => {
    await result.current.handleFileUpload(event);
  });

  expect(PersistenceService.uploadPdf).toHaveBeenCalledWith(file);
  expect(refreshLibrary).toHaveBeenCalled();
  expect(setView).not.toHaveBeenCalled();
  expect(event.target.value).toBe('');
});

test('useBookActions ignores invalid uploads and handles upload errors', async () => {
  const { result, setModal } = createHook();

  const badFile = new File(['data'], 'test.txt', { type: 'text/plain' });
  const badEvent = { target: { files: [badFile], value: 'set' } } as any;

  await act(async () => {
    await result.current.handleFileUpload(badEvent);
  });

  expect(PersistenceService.uploadPdf).not.toHaveBeenCalled();

  vi.mocked(PersistenceService.uploadPdf).mockRejectedValueOnce(new Error('fail'));
  const pdfFile = new File(['%PDF-1.4'], 'test.pdf', { type: 'application/pdf' });
  const pdfEvent = { target: { files: [pdfFile], value: 'set' } } as any;

  await act(async () => {
    await result.current.handleFileUpload(pdfEvent);
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({ type: 'alert' }));
  expect(pdfEvent.target.value).toBe('');
});

test('useBookActions handles openReader', async () => {
  vi.mocked(PersistenceService.getBookById).mockResolvedValue(mockBook as any);
  const { result, setSelectedBook, setView, setChatMessages, setCurrentPage } = createHook();

  await act(async () => {
    await result.current.openReader(mockBook);
  });

  expect(setSelectedBook).toHaveBeenCalledWith(mockBook);
  expect(setChatMessages).toHaveBeenCalledWith([]);
  expect(setView).toHaveBeenCalledWith('reader');
  expect(setCurrentPage).toHaveBeenCalledWith(1);
});

test('useBookActions handles delete confirmation flow', async () => {
  const { result, setModal } = createHook();

  act(() => {
    result.current.handleDeleteBook('1', '1');
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({
    isOpen: true,
    type: 'confirm'
  }));

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.deleteBook).toHaveBeenCalledWith('1');
});

test('useBookActions handles page reset confirmation flow', async () => {
  const { result, setModal } = createHook();

  act(() => {
    result.current.handleReProcessPage('1', 3);
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({
    isOpen: true,
    type: 'confirm'
  }));

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(PersistenceService.resetPage).toHaveBeenCalledWith('1', 3);
});

test('useBookActions updates page text and saves corrections', async () => {
  vi.mocked(PersistenceService.updatePage).mockResolvedValue(undefined as any);
  vi.mocked(PersistenceService.saveBookGlobally).mockResolvedValue(undefined as any);

  const { result, setSelectedBook, refreshLibrary } = createHook();
  const setEditingPageNum = vi.fn();

  await act(async () => {
    await result.current.handleUpdatePage('1', 1, 'New Text', setEditingPageNum);
  });

  expect(PersistenceService.updatePage).toHaveBeenCalledWith('1', 1, 'New Text');
  expect(setEditingPageNum).toHaveBeenCalledWith(null);
  expect(setSelectedBook).toHaveBeenCalled();
  expect(refreshLibrary).toHaveBeenCalled();

  const setIsEditing = vi.fn();
  const bookForSave: Book = {
    ...mockBook,
    totalPages: 2,
    pages: [
      { pageNumber: 1, text: 'a', status: 'ocr_done' },
      { pageNumber: 2, text: 'b', status: 'ocr_done' }
    ],
  };

  await act(async () => {
    await result.current.saveCorrections(
      bookForSave,
      '[[PAGE 1]]\nline1\n[[PAGE 2]]\nline2',
      setIsEditing
    );
  });

  expect(PersistenceService.saveBookGlobally).toHaveBeenCalled();
  expect(setIsEditing).toHaveBeenCalledWith(false);
});

test('useBookActions updates title, author, and categories', async () => {
  vi.mocked(PersistenceService.updateBookMetadata).mockResolvedValue(undefined as any);
  const { result, setBooks } = createHook();

  await act(async () => {
    await result.current.handleSaveTitle('1', 'New Title', vi.fn(), vi.fn());
    await result.current.handleSaveAuthor('1', 'New Author', vi.fn(), vi.fn());
    await result.current.handleSaveCategories('1', ['History', ' Culture '], vi.fn(), vi.fn());
  });

  expect(PersistenceService.updateBookMetadata).toHaveBeenCalledWith('1', { title: 'New Title' });
  expect(PersistenceService.updateBookMetadata).toHaveBeenCalledWith('1', { author: 'New Author' });
  expect(PersistenceService.updateBookMetadata).toHaveBeenCalledWith('1', { categories: ['History', 'Culture'] });
  expect(setBooks).toHaveBeenCalled();
});

test('useBookActions validates volume input', async () => {
  vi.mocked(PersistenceService.updateBookMetadata).mockResolvedValue(undefined as any);
  const { result } = createHook();

  await act(async () => {
    await result.current.handleSaveVolume('1', '2', vi.fn(), vi.fn());
  });
  expect(PersistenceService.updateBookMetadata).toHaveBeenCalledWith('1', { volume: 2 });

  vi.clearAllMocks();
  vi.mocked(PersistenceService.updateBookMetadata).mockResolvedValue(undefined as any);

  await act(async () => {
    await result.current.handleSaveVolume('1', '2.5', vi.fn(), vi.fn());
  });
  expect(PersistenceService.updateBookMetadata).not.toHaveBeenCalled();
});
