import { renderHook, act } from '@testing-library/react';
import { useBookActions } from '@/src/hooks/useBookActions';
import { PersistenceService } from '@/src/services/persistenceService';
import { expect, test, vi, beforeEach } from 'vitest';
import { Book } from '@shared/types';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    uploadPdf: vi.fn(),
    reprocessBook: vi.fn(),
    resetFailedPages: vi.fn(),
    revertBook: vi.fn(),
    getBookById: vi.fn(),
    saveBookGlobally: vi.fn(),
    deleteBook: vi.fn(),
    updateBookTags: vi.fn(),
    updateBookMetadata: vi.fn(),
  }
}));

// Mock global fetch for handleReProcessPage and handleUpdatePage
global.fetch = vi.fn() as any;

const mockBook: Book = {
  id: '1', title: 'T', author: 'A', totalPages: 1, pages: [{ pageNumber: 1, status: 'ocr_done' }], status: 'ready', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h'
};

beforeEach(() => {
  vi.clearAllMocks();
});

test.skip('useBookActions handles file upload', async () => {
  const refreshLibrary = vi.fn();
  const setView = vi.fn();
  const { result } = renderHook(() => useBookActions(refreshLibrary, vi.fn(), vi.fn(), setView, vi.fn()));

  const file = new File(['%PDF-1.4'], 'test.pdf', { type: 'application/pdf' });
  const event = { target: { files: [file] } } as any;

  await act(async () => {
    await result.current.handleFileUpload(event);
  });

  expect(PersistenceService.uploadPdf).toHaveBeenCalledWith(file);
  expect(refreshLibrary).toHaveBeenCalled();
  expect(setView).toHaveBeenCalledWith('admin');
});

test.skip('useBookActions ignores non-pdf uploads and handles upload errors', async () => {
  const refreshLibrary = vi.fn();
  const setView = vi.fn();
  const setModal = vi.fn();
  const { result } = renderHook(() => useBookActions(refreshLibrary, vi.fn(), vi.fn(), setView, setModal));

  const badFile = new File(['data'], 'test.txt', { type: 'text/plain' });
  const badEvent = { target: { files: [badFile] } } as any;

  await act(async () => {
    await result.current.handleFileUpload(badEvent);
  });
  expect(PersistenceService.uploadPdf).not.toHaveBeenCalled();

  (PersistenceService.uploadPdf as any).mockRejectedValueOnce(new Error('fail'));
  const pdfFile = new File(['%PDF-1.4'], 'test.pdf', { type: 'application/pdf' });
  const pdfEvent = { target: { files: [pdfFile] } } as any;

  await act(async () => {
    await result.current.handleFileUpload(pdfEvent);
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({ type: 'alert' }));
});

test.skip('useBookActions handles openReader', async () => {
  (PersistenceService.getBookById as any).mockResolvedValue(mockBook);
  const setSelectedBook = vi.fn();
  const setView = vi.fn();

  const { result } = renderHook(() => useBookActions(vi.fn(), vi.fn(), setSelectedBook, setView, vi.fn()));

  await act(async () => {
    await result.current.openReader(mockBook, vi.fn(), vi.fn(), vi.fn());
  });

  expect(setSelectedBook).toHaveBeenCalledWith(mockBook);
  expect(setView).toHaveBeenCalledWith('reader');
});

test.skip('useBookActions handles handleDeleteBook', async () => {
  const setModal = vi.fn();
  const { result } = renderHook(() => useBookActions(vi.fn(), vi.fn(), vi.fn(), vi.fn(), setModal));

  act(() => {
    result.current.handleDeleteBook('1', '1');
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({
    isOpen: true,
    type: 'confirm'
  }));

  // Test confirmation callback
  const onConfirm = setModal.mock.calls[0][0].onConfirm;
  await act(async () => {
    await onConfirm();
  });

  expect(PersistenceService.deleteBook).toHaveBeenCalledWith('1');
});

test.skip('useBookActions handles reset failed pages', async () => {
  const setModal = vi.fn();
  const refreshLibrary = vi.fn();
  (PersistenceService.resetFailedPages as any).mockResolvedValue({ status: 'reset', count: 3 });
  const { result } = renderHook(() => useBookActions(refreshLibrary, vi.fn(), vi.fn(), vi.fn(), setModal));

  act(() => {
    result.current.handleResetFailedPages('1');
  });

  expect(setModal).toHaveBeenCalledWith(expect.objectContaining({ type: 'confirm' }));

  const onConfirm = setModal.mock.calls[0][0].onConfirm;
  await act(async () => {
    await onConfirm();
  });
  expect(PersistenceService.resetFailedPages).toHaveBeenCalledWith('1');
  expect(refreshLibrary).toHaveBeenCalled();
});

test.skip('useBookActions updates page text and saves corrections', async () => {
  const setSelectedBook = vi.fn();
  const setEditingPageNum = vi.fn();
  const fetchMock = vi.fn().mockResolvedValue({ ok: true });
  // @ts-expect-error test mock
  global.fetch = fetchMock;

  const { result } = renderHook(() => useBookActions(vi.fn(), vi.fn(), setSelectedBook, vi.fn(), vi.fn()));

  await act(async () => {
    await result.current.handleUpdatePage('1', 1, 'New Text', setEditingPageNum);
  });

  expect(fetchMock).toHaveBeenCalledWith('/api/books/1/pages/1/update/', expect.any(Object));
  expect(setEditingPageNum).toHaveBeenCalledWith(null);
  expect(setSelectedBook).toHaveBeenCalled();

  const setIsEditing = vi.fn();
  const bookForSave: Book = {
    id: '1',
    title: 'T',
    author: 'A',
    totalPages: 2,
    pages: [
      { pageNumber: 1, text: 'a', status: 'ocr_done' },
      { pageNumber: 2, text: 'b', status: 'ocr_done' }
    ],
    status: 'ready',
    uploadDate: new Date(),
    lastUpdated: new Date(),
    contentHash: 'h'
  };

  await act(async () => {
    await result.current.saveCorrections(bookForSave, 'line1\\nline2', setIsEditing);
  });

  expect(PersistenceService.saveBookGlobally).toHaveBeenCalled();
  expect(setIsEditing).toHaveBeenCalledWith(false);
});

test.skip('useBookActions updates title, author, and categories', async () => {
  const setBooks = vi.fn();
  const { result } = renderHook(() => useBookActions(vi.fn(), setBooks, vi.fn(), vi.fn(), vi.fn()));

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

test.skip('useBookActions validates volume input', async () => {
  const { result } = renderHook(() => useBookActions(vi.fn(), vi.fn(), vi.fn(), vi.fn(), vi.fn()));

  await act(async () => {
    await result.current.handleSaveVolume('1', '2', vi.fn(), vi.fn());
  });
  expect(PersistenceService.updateBookMetadata).toHaveBeenCalledWith('1', { volume: 2 });

  vi.clearAllMocks();

  await act(async () => {
    await result.current.handleSaveVolume('1', '2.5', vi.fn(), vi.fn());
  });
  expect(PersistenceService.updateBookMetadata).not.toHaveBeenCalled();
});
