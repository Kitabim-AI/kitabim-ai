import { renderHook, act } from '@testing-library/react';
import { useBookActions } from '../hooks/useBookActions';
import { PersistenceService } from '../services/persistenceService';
import { expect, test, vi, beforeEach } from 'vitest';
import { Book } from '../types';

vi.mock('../services/persistenceService', () => ({
  PersistenceService: {
    uploadPdf: vi.fn(),
    reprocessBook: vi.fn(),
    getBookById: vi.fn(),
    saveBookGlobally: vi.fn(),
    deleteBook: vi.fn(),
    updateBookTags: vi.fn(),
  }
}));

// Mock global fetch for handleReProcessPage and handleUpdatePage
global.fetch = vi.fn() as any;

const mockBook: Book = {
  id: '1', title: 'T', author: 'A', totalPages: 1, results: [{ pageNumber: 1, status: 'completed' }], status: 'ready', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h'
};

beforeEach(() => {
  vi.clearAllMocks();
});

test('useBookActions handles file upload', async () => {
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

test('useBookActions handles openReader', async () => {
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

test('useBookActions handles handleDeleteBook', async () => {
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
