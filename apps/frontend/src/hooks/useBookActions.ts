import React, { useState, useRef } from 'react';
import { Book } from '@shared/types';
import { PersistenceService } from '../services/persistenceService';
import { useNotification } from '../context/NotificationContext';

export const useBookActions = (
  refreshLibrary: () => Promise<void>,
  setBooks: (books: Book[] | ((prev: Book[]) => Book[])) => void,
  setSelectedBook: (book: Book | null | ((prev: Book | null) => Book | null)) => void,
  setView: (view: any) => void,
  setModal: (modal: any) => void
) => {
  const { addNotification } = useNotification();
  const [isCheckingGlobal, setIsCheckingGlobal] = useState(false);
  const cancelledBooks = useRef<Set<string>>(new Set());

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || file.type !== 'application/pdf') return;

    setIsCheckingGlobal(true);
    setView('admin');

    try {
      await PersistenceService.uploadPdf(file);
      await refreshLibrary();
      setIsCheckingGlobal(false);
      addNotification("Document uploaded successfully.", "success");
    } catch (err) {
      setIsCheckingGlobal(false);
      const errorMsg = err instanceof Error ? err.message : "An unknown error occurred.";
      setModal({
        isOpen: true,
        title: "Upload Error",
        message: `Error uploading document: ${errorMsg}`,
        type: 'alert'
      });
    }
  };

  const handleStartOcr = (bookId: string) => {
    setModal({
      isOpen: true,
      title: "Confirm OCR Start",
      message: `Are you sure you want to start Gemini OCR? This will analyze the document and extract text.`,
      type: 'confirm',
      confirmText: "Start Processing",
      onConfirm: async () => {
        try {
          setBooks(prev => prev.map(b => b.id === bookId ? { ...b, status: 'processing', processingStep: 'ocr' } : b));
          await PersistenceService.startOcr(bookId);
          await refreshLibrary();
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification("OCR process started successfully.", "success");
        } catch (err) {
          addNotification("Failed to start OCR process.", "error");
          setModal({
            isOpen: true,
            title: "Process Error",
            message: "Failed to start OCR. Please try again.",
            type: 'alert'
          });
        }
      }
    });
  };

  const handleRetryFailedOcr = async (book: Book) => {
    const hasFailedPages = (book.errorCount ?? 0) > 0 || (book.pages?.some(r => r.status === 'error') ?? false);

    if (!hasFailedPages && book.status !== 'error') {
      setModal({
        isOpen: true,
        title: "No Failed Pages",
        message: "This book has no failed OCR pages to retry.",
        type: 'alert'
      });
      return;
    }

    const effectiveProvider = 'gemini';
    let previousSelected: Book | null = null;
    let previousBooks: Book[] | null = null;

    setSelectedBook(prev => {
      previousSelected = prev;
      if (!prev || prev.id !== book.id) return prev;
      return {
        ...prev,
        status: 'processing',
        processingStep: 'ocr',
        lastUpdated: new Date(),
        pages: (prev.pages || []).map(r =>
          r.status === 'error'
            ? { ...r, status: 'pending', text: '', error: undefined, isVerified: false }
            : r
        ),
      };
    });

    setBooks(prev => {
      previousBooks = prev;
      return prev.map(b => {
        if (b.id !== book.id) return b;
        return {
          ...b,
          status: 'processing',
          processingStep: 'ocr',
          lastUpdated: new Date(),
          pages: (b.pages || []).map(r =>
            r.status === 'error'
              ? { ...r, status: 'pending', text: '', error: undefined, isVerified: false }
              : r
          ),
        };
      });
    });

    try {
      await PersistenceService.retryFailedOcr(book.id);
      refreshLibrary();
    } catch (err) {
      if (previousSelected) setSelectedBook(previousSelected);
      if (previousBooks) setBooks(previousBooks);
      console.error("Failed to retry OCR", err);
      setModal({
        isOpen: true,
        title: "Retry Error",
        message: "Failed to retry OCR for failed pages. Please try again.",
        type: 'alert'
      });
    }
  };

  const handleReProcessPage = async (bookId: string, pageNum: number) => {
    let previousSelected: Book | null = null;
    let previousBooks: Book[] | null = null;

    setSelectedBook(prev => {
      previousSelected = prev;
      if (!prev || prev.id !== bookId) return prev;
      return {
        ...prev,
        status: 'processing',
        lastUpdated: new Date(),
        pages: (prev.pages || []).map(r =>
          r.pageNumber === pageNum
            ? { ...r, status: 'pending', text: '', isVerified: false }
            : r
        ),
      };
    });

    setBooks(prev => {
      previousBooks = prev;
      return prev.map(b => {
        if (b.id !== bookId) return b;
        return {
          ...b,
          status: 'processing',
          lastUpdated: new Date(),
          pages: (b.pages || []).map(r =>
            r.pageNumber === pageNum
              ? { ...r, status: 'pending', text: '', isVerified: false }
              : r
          ),
        };
      });
    });

    try {
      await PersistenceService.resetPage(bookId, pageNum);
      refreshLibrary();
    } catch (err) {
      if (previousSelected) setSelectedBook(previousSelected);
      if (previousBooks) setBooks(previousBooks);
      console.error("Failed to reset page", err);
      setModal({
        isOpen: true,
        title: "Re-OCR Error",
        message: "Failed to start re-OCR for this page. Please try again.",
        type: 'alert'
      });
    }
  };



  const handleReindexBook = (bookId: string) => {
    setModal({
      isOpen: true,
      title: "Confirm Re-Index",
      message: "Are you sure you want to re-chunk and re-embed all pages in this book? This is useful for model upgrades or fixing search issues. Existing content will be preserved.",
      type: 'confirm',
      confirmText: "Re-Index Book",
      onConfirm: async () => {
        try {
          await PersistenceService.reindexBook(bookId);
          setBooks(prev => prev.map(b => b.id === bookId ? { ...b, status: 'processing', processingStep: 'rag' } : b));
          await refreshLibrary();
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification("Book re-indexing started.", "success");
        } catch (err) {
          setModal({
            isOpen: true,
            title: "Re-Index Error",
            message: "Failed to start re-indexing. Please try again.",
            type: 'alert'
          });
        }
      }
    });
  };

  const handleUpdatePage = async (bookId: string, pageNum: number, newText: string, setEditingPageNum: any) => {
    try {
      await PersistenceService.updatePage(bookId, pageNum, newText);
      setEditingPageNum(null);
      setSelectedBook(prev => {
        if (!prev || prev.id !== bookId) return prev;
        return {
          ...prev,
          pages: (prev.pages || []).map(r => r.pageNumber === pageNum ? { ...r, text: newText, isVerified: true } : r),
          lastUpdated: new Date()
        };
      });
      // Don't call refreshLibrary() here - it can race with polling and overwrite our update
      // The polling in App.tsx will sync the data within a few seconds
      addNotification(`Page ${pageNum} updated.`, "success");
    } catch (err) {
      console.error("Failed to update page", err);
      setModal({
        isOpen: true,
        title: "Update Error",
        message: "Failed to save page changes. Please try again.",
        type: 'alert'
      });
    }
  };

  const openReader = async (book: Book, setEditContent: any, setChatMessages: any, setCurrentPage: any) => {
    try {
      const fullBook = await PersistenceService.getBookById(book.id);
      if (!fullBook) throw new Error("Could not load book content");

      // We do NOT fetch the full content string here.
      // The ReaderView will fetch pages for reading,
      // and only fetch full content if/when the user clicks "Edit Book".

      setSelectedBook(fullBook);
      setEditContent(''); // Intentionally empty to start fast
      setChatMessages([]);
      setView('reader');
      setCurrentPage(1);
    } catch (err) {
      setModal({
        isOpen: true,
        title: "Load Error",
        message: "Failed to load book content. Please try again.",
        type: 'alert'
      });
    }
  };

  const saveCorrections = async (selectedBook: Book | null, editContent: string, setIsEditing: any) => {
    if (!selectedBook) return;
    try {
      // 1. Extract content by markers
      const segments = editContent.split(/\[\[PAGE \d+\]\]/);
      const markers = editContent.match(/\[\[PAGE (\d+)\]\]/g);

      const newPageMap = new Map<number, string>();
      if (markers) {
        markers.forEach((m, i) => {
          const match = m.match(/\d+/);
          if (match) {
            const pageNum = parseInt(match[0]);
            newPageMap.set(pageNum, (segments[i + 1] || "").trim());
          }
        });
      }

      // 2. Identify changes and build updated results
      let hasChanges = false;
      const updatedPages = (selectedBook.pages || []).map(res => {
        const newText = newPageMap.get(res.pageNumber);

        // If marker exists and text is different, update
        if (newText !== undefined && newText !== (res.text || "")) {
          hasChanges = true;
          return {
            ...res,
            text: newText,
            status: 'completed' as const,
            isVerified: true
          };
        }
        // Otherwise keep original (avoids re-verifying or re-syncing unchanged pages)
        return res;
      });

      if (!hasChanges) {
        setIsEditing(false);
        return;
      }

      const cleanPages = updatedPages.map(({ embedding, ...rest }: any) => rest);

      const updatedBook = {
        ...selectedBook,
        pages: cleanPages as any,
        lastUpdated: new Date()
      };

      await PersistenceService.saveBookGlobally(updatedBook);
      setSelectedBook(updatedBook);
      await refreshLibrary();
      setIsEditing(false);
      addNotification("Global corrections saved.", "success");
    } catch (err) {
      console.error("Failed to save global corrections", err);
      setModal({
        isOpen: true,
        title: "Save Error",
        message: "Failed to save global changes. Please try again.",
        type: 'alert'
      });
    }
  };

  const handleDeleteBook = (bookId: string, selectedBookId: string | undefined) => {
    setModal({
      isOpen: true,
      title: "Confirm Deletion",
      message: "Are you sure you want to delete this book? This will permanently remove it from the global library platform.",
      type: 'confirm',
      confirmText: "Delete Permanently",
      onConfirm: async () => {
        cancelledBooks.current.add(bookId);
        await PersistenceService.deleteBook(bookId);
        setBooks(prev => prev.filter(b => b.id !== bookId));
        if (selectedBookId === bookId) {
          setSelectedBook(null);
          setView('library');
        }
        setModal((prev: any) => ({ ...prev, isOpen: false }));
        addNotification("Book deleted successfully.", "success");
      }
    });
  };

  const handleSaveTags = async (bookId: string, tagsArray: string[], setEditingBookTagsId: any, setEditingTagsList: any) => {
    try {
      const tags = tagsArray.map(t => t.trim()).filter(Boolean);
      await PersistenceService.updateBookMetadata(bookId, { tags });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, tags } : b));
      setEditingBookTagsId(null);
      setEditingTagsList([]);
      addNotification("Tags updated successfully.", "success");
    } catch (e) {
      console.error("Failed to save tags", e);
      addNotification("Failed to update tags.", "error");
    }
  };


  const handleSaveCategories = async (bookId: string, categoriesArray: string[], setEditingId: any, setEditingList: any) => {
    try {
      const categories = categoriesArray.map(t => t.trim()).filter(Boolean);
      await PersistenceService.updateBookMetadata(bookId, { categories });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, categories } : b));
      setEditingId(null);
      setEditingList([]);
      addNotification("Categories updated successfully.", "success");
    } catch (e) {
      console.error("Failed to save categories", e);
      addNotification("Failed to update categories.", "error");
    }
  };

  const handleSaveAuthor = async (bookId: string, author: string, setEditingId: any, setTempAuthor: any) => {
    try {
      const trimmedAuthor = author.trim();
      await PersistenceService.updateBookMetadata(bookId, { author: trimmedAuthor });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, author: trimmedAuthor } : b));
      setEditingId(null);
      setTempAuthor('');
      addNotification("Author updated successfully.", "success");
    } catch (e) {
      console.error("Failed to save author", e);
      addNotification("Failed to update author.", "error");
    }
  };

  const handleSaveTitle = async (bookId: string, title: string, setEditingId: any, setTempTitle: any) => {
    try {
      const trimmedTitle = title.trim();
      if (!trimmedTitle) return;
      await PersistenceService.updateBookMetadata(bookId, { title: trimmedTitle });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, title: trimmedTitle } : b));
      setEditingId(null);
      setTempTitle('');
      addNotification("Title updated successfully.", "success");
    } catch (e) {
      console.error("Failed to save title", e);
      addNotification("Failed to update title.", "error");
    }
  };

  const handleSaveVolume = async (bookId: string, volumeInput: string, setEditingId: any, setTempVolume: any) => {
    try {
      const trimmed = volumeInput.trim();
      let volume: number | null = null;

      if (trimmed.length > 0) {
        const parsed = Number(trimmed);
        if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 0) {
          console.error("Invalid volume value:", volumeInput);
          return;
        }
        volume = parsed;
      }

      await PersistenceService.updateBookMetadata(bookId, { volume });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, volume } : b));
      setEditingId(null);
      setTempVolume('');
      addNotification("Volume updated successfully.", "success");
    } catch (e) {
      console.error("Failed to save volume", e);
      addNotification("Failed to update volume.", "error");
    }
  };

  const handleToggleVisibility = async (bookId: string, currentVisibility: string) => {
    try {
      const newVisibility = currentVisibility === 'public' ? 'private' : 'public';
      await PersistenceService.updateBookMetadata(bookId, { visibility: newVisibility });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, visibility: newVisibility } : b));
      addNotification(`Book made ${newVisibility}.`, "success");
    } catch (e) {
      console.error("Failed to toggle visibility", e);
      setModal({
        isOpen: true,
        title: "Visibility Error",
        message: "Failed to update book visibility. Please try again.",
        type: 'alert'
      });
    }
  };

  return {
    isCheckingGlobal,
    handleFileUpload,
    handleStartOcr,
    handleRetryFailedOcr,
    handleReProcessPage,
    handleReindexBook,
    handleUpdatePage,
    openReader,
    saveCorrections,
    handleDeleteBook,
    handleSaveTags,
    handleSaveCategories,
    handleSaveAuthor,
    handleSaveTitle,
    handleSaveVolume,
    handleToggleVisibility,
  };
};
