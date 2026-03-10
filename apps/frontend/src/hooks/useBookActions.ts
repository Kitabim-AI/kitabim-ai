import React, { useState, useRef } from 'react';
import { Book } from '@shared/types';
import { PersistenceService } from '../services/persistenceService';
import { useNotification } from '../context/NotificationContext';
import { useI18n } from '../i18n/I18nContext';

export const useBookActions = (
  refreshLibrary: () => Promise<void>,
  setBooks: (books: Book[] | ((prev: Book[]) => Book[])) => void,
  setSelectedBook: (book: Book | null | ((prev: Book | null) => Book | null)) => void,
  setView: (view: any) => void,
  setModal: (modal: any) => void,
  setChatMessages: (messages: any[]) => void,
  setCurrentPage: (page: number) => void
) => {
  const { addNotification } = useNotification();
  const { t } = useI18n();
  const [isCheckingGlobal, setIsCheckingGlobal] = useState(false);
  const cancelledBooks = useRef<Set<string>>(new Set());

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    const ALLOWED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
    if (!file || (!ALLOWED_TYPES.includes(file.type) && !file.name.toLowerCase().endsWith('.docx'))) return;

    setIsCheckingGlobal(true);
    setView('admin');

    try {
      const result = await PersistenceService.uploadPdf(file);
      await refreshLibrary();
      setIsCheckingGlobal(false);

      if (result?.status === 'existing') {
        addNotification(t('common.uploadExisting'), 'info');
      } else {
        addNotification(t('common.uploadSuccess'), 'success');
      }
    } catch (err) {
      setIsCheckingGlobal(false);
      const errorMsg = err instanceof Error ? err.message : "An unknown error occurred.";
      setModal({
        isOpen: true,
        title: t('modal.uploadError.title'),
        message: t('modal.uploadError.message', { error: errorMsg }),
        type: 'alert'
      });
    }
  };

  const handleResetFailedPages = (bookId: string) => {
    setModal({
      isOpen: true,
      title: t('modal.resetFailed.title'),
      message: t('modal.resetFailed.message'),
      type: 'confirm',
      confirmText: t('modal.resetFailed.confirm'),
      onConfirm: async () => {
        try {
          const result = await PersistenceService.resetFailedPages(bookId);
          await refreshLibrary();
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          if (result.count === 0) {
            addNotification(t('common.noFailedPages'), "info");
          } else {
            addNotification(t('common.resetFailedSuccess', { count: result.count }), "success");
          }
        } catch (err) {
          setModal({
            isOpen: true,
            title: t('modal.resetFailedError.title'),
            message: t('modal.resetFailedError.message'),
            type: 'alert'
          });
        }
      }
    });
  };

  const handleReProcessPage = (bookId: string, pageNum: number) => {
    setModal({
      isOpen: true,
      title: t('modal.resetPage.title'),
      message: t('modal.resetPage.message', { pageNum }),
      type: 'confirm',
      confirmText: t('modal.resetPage.confirm'),
      onConfirm: async () => {
        let previousSelected: Book | null = null;
        let previousBooks: Book[] | null = null;

        // Optimistic UI update: show spinner immediately
        setSelectedBook(prev => {
          previousSelected = prev;
          if (!prev || prev.id !== bookId) return prev;
          return {
            ...prev,
            status: 'pending', // Match backend
            pages: (prev.pages || []).map(r =>
              r.pageNumber === pageNum
                ? { ...r, status: 'pending', text: '', isVerified: false, pipelineStep: null, milestone: null }
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
              status: 'pending',
              pages: (b.pages || []).map(r =>
                r.pageNumber === pageNum
                  ? { ...r, status: 'pending', text: '', isVerified: false, pipelineStep: null, milestone: null }
                  : r
              ),
            };
          });
        });

        setModal(prev => ({ ...prev, isOpen: false }));

        try {
          await PersistenceService.resetPage(bookId, pageNum);
          refreshLibrary();
          addNotification(t('common.pageResetSuccess', { pageNum }), 'success');
        } catch (err) {
          if (previousSelected) setSelectedBook(previousSelected);
          if (previousBooks) setBooks(previousBooks);
          console.error("Failed to reset page", err);
          addNotification(t('common.pageResetError', { pageNum }), 'error');
        }
      }
    });
  };



  const handleTriggerSpellCheck = (bookId: string) => {
    setModal({
      isOpen: true,
      title: t('modal.triggerSpellCheck.title'),
      message: t('modal.triggerSpellCheck.message'),
      type: 'confirm',
      confirmText: t('modal.triggerSpellCheck.confirm'),
      onConfirm: async () => {
        try {
          const result = await PersistenceService.triggerSpellCheck(bookId);
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('common.spellCheckStarted', { count: result.queued }), "success");
        } catch (err) {
          const message = err instanceof Error ? err.message : t('modal.triggerSpellCheckError.message');
          setModal({
            isOpen: true,
            title: t('modal.triggerSpellCheckError.title'),
            message,
            type: 'alert'
          });
        }
      }
    });
  };

  const handleReindexBook = (bookId: string) => {
    setModal({
      isOpen: true,
      title: t('modal.reindex.title'),
      message: t('modal.reindex.message'),
      type: 'confirm',
      confirmText: t('modal.reindex.confirm'),
      onConfirm: async () => {
        try {
          await PersistenceService.reindexBook(bookId);
          setBooks(prev => prev.map(b => b.id === bookId ? { ...b, status: 'ocr_processing', processingStep: 'rag' } : b));
          await refreshLibrary();
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('common.reindexStarted'), "success");
        } catch (err) {
          setModal({
            isOpen: true,
            title: t('modal.reindexError.title'),
            message: t('modal.reindexError.message'),
            type: 'alert'
          });
        }
      }
    });
  };

  const handleUpdatePage = async (bookId: string, pageNum: number, newText: string, setEditingPageNum: any) => {
    try {
      await PersistenceService.updatePage(bookId, pageNum, newText);

      setSelectedBook(prev => {
        if (!prev || prev.id !== bookId) return prev;

        const existingPages = prev.pages || [];
        const pageExists = existingPages.some(r => r.pageNumber === pageNum);

        let newPages;
        if (pageExists) {
          newPages = existingPages.map(r =>
            r.pageNumber === pageNum ? { ...r, text: newText, isVerified: true, status: 'ocr_done' } : r
          );
        } else {
          newPages = [...existingPages, {
            pageNumber: pageNum,
            text: newText,
            isVerified: true,
            status: 'ocr_done'
          }].sort((a, b) => a.pageNumber - b.pageNumber);
        }

        return {
          ...prev,
          pages: newPages as any,
          lastUpdated: new Date()
        };
      });

      setEditingPageNum(null);
      await refreshLibrary();
      addNotification(t('common.pageUpdated', { pageNum }), "success");
    } catch (err) {
      console.error("Failed to update page", err);
      setModal({
        isOpen: true,
        title: t('modal.updateError.title'),
        message: t('modal.updateError.message'),
        type: 'alert'
      });
    }
  };

  const openReader = async (book: Book) => {
    try {
      const fullBook = await PersistenceService.getBookById(book.id);
      if (!fullBook) throw new Error("Could not load book content");

      // Ensure pages is an array
      if (!fullBook.pages) fullBook.pages = [];

      setSelectedBook(fullBook);
      setChatMessages([]);
      setView('reader');
      setCurrentPage(1);
    } catch (err) {
      console.error("Error opening reader:", err);
      setModal({
        isOpen: true,
        title: t('modal.loadError.title'),
        message: t('modal.loadError.message'),
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

      // 2. Build pages array directly from parsed content
      // This ensures ALL pages from editContent are included, not just the ones in selectedBook.pages
      const updatedPages = Array.from(newPageMap.entries()).map(([pageNumber, text]) => ({
        pageNumber,
        text,
        status: 'ocr_done' as const,
        isVerified: true
      }));

      if (updatedPages.length === 0) {
        addNotification(t('common.noPagesToSave'), "error");
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
      addNotification(t('common.saveSuccess'), "success");
    } catch (err) {
      console.error("Failed to save global corrections", err);
      setModal({
        isOpen: true,
        title: t('modal.saveError.title'),
        message: t('modal.saveError.message'),
        type: 'alert'
      });
    }
  };

  const handleDeleteBook = (bookId: string, selectedBookId: string | undefined) => {
    setModal({
      isOpen: true,
      title: t('modal.delete.title'),
      message: t('modal.delete.message'),
      type: 'confirm',
      confirmText: t('modal.delete.confirm'),
      destructive: true,
      onConfirm: async () => {
        cancelledBooks.current.add(bookId);
        await PersistenceService.deleteBook(bookId);
        setBooks(prev => prev.filter(b => b.id !== bookId));
        if (selectedBookId === bookId) {
          setSelectedBook(null);
          setView('library');
        }
        setModal((prev: any) => ({ ...prev, isOpen: false }));
        addNotification(t('common.deleteSuccess'), "success");
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
      addNotification(t('common.tagsUpdateSuccess'), "success");
    } catch (e) {
      console.error("Failed to save tags", e);
      addNotification(t('common.tagsUpdateError'), "error");
    }
  };


  const handleSaveCategories = async (bookId: string, categoriesArray: string[], setEditingId: any, setEditingList: any) => {
    try {
      const categories = categoriesArray.map(t => t.trim()).filter(Boolean);
      await PersistenceService.updateBookMetadata(bookId, { categories });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, categories } : b));
      setEditingId(null);
      setEditingList([]);
      addNotification(t('common.categoriesUpdateSuccess'), "success");
    } catch (e) {
      console.error("Failed to save categories", e);
      addNotification(t('common.categoriesUpdateError'), "error");
    }
  };

  const handleSaveAuthor = async (bookId: string, author: string, setEditingId: any, setTempAuthor: any) => {
    try {
      const trimmedAuthor = author.trim();
      await PersistenceService.updateBookMetadata(bookId, { author: trimmedAuthor });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, author: trimmedAuthor } : b));
      setEditingId(null);
      setTempAuthor('');
      addNotification(t('common.authorUpdateSuccess'), "success");
    } catch (e) {
      console.error("Failed to save author", e);
      addNotification(t('common.authorUpdateError'), "error");
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
      addNotification(t('common.titleUpdateSuccess'), "success");
    } catch (e) {
      console.error("Failed to save title", e);
      addNotification(t('common.titleUpdateError'), "error");
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
      addNotification(t('common.volumeUpdateSuccess'), "success");
    } catch (e) {
      console.error("Failed to save volume", e);
      addNotification(t('common.volumeUpdateError'), "error");
    }
  };

  const handleSaveBookRow = async (
    bookId: string,
    data: {
      title?: string;
      author?: string;
      volume?: number | null;
      categories?: string[];
    }
  ) => {
    try {
      await PersistenceService.updateBookMetadata(bookId, data);
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, ...data } : b));
      addNotification(t('common.saveSuccess'), "success");
      return true;
    } catch (err) {
      console.error("Failed to save book metadata", err);
      addNotification(t('common.error'), "error");
      return false;
    }
  };

  const handleToggleVisibility = async (bookId: string, currentVisibility: string) => {
    try {
      const newVisibility = currentVisibility === 'public' ? 'private' : 'public';
      await PersistenceService.updateBookMetadata(bookId, { visibility: newVisibility });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, visibility: newVisibility } : b));
      addNotification(t('common.visibilityUpdated', { visibility: newVisibility }), "success");
    } catch (e) {
      console.error("Failed to toggle visibility", e);
      setModal({
        isOpen: true,
        title: t('modal.visibilityError.title'),
        message: t('modal.visibilityError.message'),
        type: 'alert'
      });
    }
  };

  const handleReplaceCover = async (bookId: string, file: File) => {
    try {
      const { coverUrl } = await PersistenceService.updateBookCover(bookId, file);
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, coverUrl, lastUpdated: new Date() } : b));
      addNotification(t('common.saveSuccess'), "success");
    } catch (err) {
      console.error("Failed to replace cover", err);
      addNotification(t('common.error'), "error");
    }
  };

  return {
    isCheckingGlobal,
    handleFileUpload,
    handleResetFailedPages,
    handleReProcessPage,
    handleTriggerSpellCheck,
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
    handleSaveBookRow,
    handleToggleVisibility,
    handleReplaceCover,
  };
};
