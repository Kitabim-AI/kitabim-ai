import React, { useState, useRef } from 'react';
import { Book } from '../types';
import { PersistenceService } from '../services/persistenceService';

export const useBookActions = (
  refreshLibrary: () => Promise<void>,
  setBooks: (books: Book[] | ((prev: Book[]) => Book[])) => void,
  setSelectedBook: (book: Book | null | ((prev: Book | null) => Book | null)) => void,
  setView: (view: any) => void,
  setModal: (modal: any) => void
) => {
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

  const handleReprocess = async (bookId: string) => {
    try {
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, status: 'processing', processingStep: 'ocr' } : b));
      await PersistenceService.reprocessBook(bookId);
      refreshLibrary();
    } catch (err) {
      setModal({
        isOpen: true,
        title: "Process Error",
        message: "Failed to start reprocessing. Please try again.",
        type: 'alert'
      });
    }
  };

  const handleReProcessPage = async (bookId: string, pageNum: number) => {
    try {
      await fetch(`/api/books/${bookId}/pages/${pageNum}/reset`, { method: 'POST' });
      refreshLibrary();
    } catch (err) {
      console.error("Failed to reset page", err);
    }
  };

  const handleUpdatePage = async (bookId: string, pageNum: number, newText: string, setEditingPageNum: any) => {
    try {
      await fetch(`/api/books/${bookId}/pages/${pageNum}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newText })
      });
      setEditingPageNum(null);
      refreshLibrary();
    } catch (err) {
      console.error("Failed to update page", err);
    }
  };

  const openReader = async (book: Book, setEditContent: any, setChatMessages: any, setCurrentPage: any) => {
    try {
      const fullBook = await PersistenceService.getBookById(book.id);
      if (!fullBook) throw new Error("Could not load book content");

      setSelectedBook(fullBook);
      setEditContent(fullBook.content);
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
      const lines = editContent.split('\n');
      const linesPerPage = Math.max(1, Math.ceil(lines.length / (selectedBook.results.length || 1)));

      const updatedResults = selectedBook.results.map((res, i) => {
        const start = i * linesPerPage;
        const end = start + linesPerPage;
        const pageLines = lines.slice(start, end);
        return {
          ...res,
          text: pageLines.join('\n').trim(),
          status: 'completed' as const
        };
      });

      const cleanResults = updatedResults.map(({ embedding, ...rest }: any) => rest);

      const updatedBook = {
        ...selectedBook,
        content: editContent,
        results: cleanResults as any,
        lastUpdated: new Date()
      };

      await PersistenceService.saveBookGlobally(updatedBook);
      await refreshLibrary();
      setIsEditing(false);
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
      onConfirm: async () => {
        cancelledBooks.current.add(bookId);
        await PersistenceService.deleteBook(bookId);
        setBooks(prev => prev.filter(b => b.id !== bookId));
        if (selectedBookId === bookId) {
          setSelectedBook(null);
          setView('library');
        }
        setModal((prev: any) => ({ ...prev, isOpen: false }));
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
    } catch (e) {
      console.error("Failed to save tags", e);
    }
  };

  const handleSaveSeries = async (bookId: string, seriesArray: string[], setEditingId: any, setEditingList: any) => {
    try {
      const series = seriesArray.map(t => t.trim()).filter(Boolean);
      await PersistenceService.updateBookMetadata(bookId, { series });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, series } : b));
      setEditingId(null);
      setEditingList([]);
    } catch (e) {
      console.error("Failed to save series", e);
    }
  };

  const handleSaveCategories = async (bookId: string, categoriesArray: string[], setEditingId: any, setEditingList: any) => {
    try {
      const categories = categoriesArray.map(t => t.trim()).filter(Boolean);
      await PersistenceService.updateBookMetadata(bookId, { categories });
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, categories } : b));
      setEditingId(null);
      setEditingList([]);
    } catch (e) {
      console.error("Failed to save categories", e);
    }
  };

  return {
    isCheckingGlobal,
    handleFileUpload,
    handleReprocess,
    handleReProcessPage,
    handleUpdatePage,
    openReader,
    saveCorrections,
    handleDeleteBook,
    handleSaveTags,
    handleSaveSeries,
    handleSaveCategories,
  };
};
