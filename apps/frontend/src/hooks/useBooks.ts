import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Book, PaginatedBooks } from '@shared/types';
import { PersistenceService } from '../services/persistenceService';

export const useBooks = (view: string, searchQuery: string, pageSize: number, page: number, category?: string) => {
  const [books, setBooks] = useState<Book[]>([]);
  const [totalBooks, setTotalBooks] = useState(0);
  const [totalReady, setTotalReady] = useState(0);
  const [isLoadingMoreShelf, setIsLoadingMoreShelf] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMoreShelf, setHasMoreShelf] = useState(true);
  const [shelfPage, setShelfPage] = useState(1);
  const COLLECTION_PAGE_SIZE = 40; // Increased to show more results at once

  const [sortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'uploadDate', direction: 'desc' });

  // Helper to determine if we should use shelf-style (infinite scroll) behavior
  const isShelfView = useMemo(() => {
    return view === 'library' || view === 'global-chat' || view === 'admin' || (view === 'home' && (searchQuery.trim().length > 0 || category));
  }, [view, searchQuery, category]);

  // Internal Polling for Processing Books (only on admin page)
  useEffect(() => {
    const hasProcessing = books.some(b => b.status === 'processing');
    if (hasProcessing && view === 'admin') {
      const interval = setInterval(async () => {
        try {
          const currentSize = isShelfView ? Math.max(books.length, COLLECTION_PAGE_SIZE) : pageSize;
          const currentPage = isShelfView ? 1 : page;
          const sortBy = isShelfView ? 'uploadDate' : sortConfig.key;
          const order = isShelfView ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

          const response = await PersistenceService.getGlobalLibrary(currentPage, currentSize, searchQuery, sortBy, order, isShelfView, category);

          setBooks(prev => {
            return response.books;
          });
          setTotalBooks(response.total);
          setTotalReady(response.totalReady);
        } catch (e) {
          console.error("Polling failed", e);
        }
      }, 10000);
      return () => clearInterval(interval);
    }
  }, [view, books.length, books.some(b => b.status === 'processing'), isShelfView, searchQuery, sortConfig, pageSize, page, category]);

  const refreshLibrary = useCallback(async () => {
    setIsLoading(true);
    try {
      const currentViewSize = isShelfView ? COLLECTION_PAGE_SIZE : pageSize;
      const currentViewPage = isShelfView ? 1 : page;

      const sortBy = isShelfView ? 'uploadDate' : sortConfig.key;
      const order = isShelfView ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

      const response = await PersistenceService.getGlobalLibrary(currentViewPage, currentViewSize, searchQuery, sortBy, order, isShelfView, category);
      setBooks(response.books);
      setTotalBooks(response.total);
      setTotalReady(response.totalReady);

      if (isShelfView) {
        setShelfPage(1);
        setHasMoreShelf(response.books.length < response.total);
      }
    } catch (err) {
      console.error("Manual refresh failed", err);
    } finally {
      setIsLoading(false);
    }
  }, [isShelfView, page, pageSize, searchQuery, sortConfig, category]);

  const loadMoreShelf = useCallback(async () => {
    if (isLoadingMoreShelf || !hasMoreShelf || !isShelfView) return;

    setIsLoadingMoreShelf(true);
    const nextPage = shelfPage + 1;
    try {
      const response = await PersistenceService.getGlobalLibrary(nextPage, COLLECTION_PAGE_SIZE, searchQuery, 'uploadDate', -1, true, category);
      if (response.books.length > 0) {
        setBooks(prev => {
          const existingIds = prev.map(b => b.id);
          const newBooks = response.books.filter(b => !existingIds.includes(b.id));
          const updated = [...prev, ...newBooks];
          setHasMoreShelf(updated.length < response.total);
          return updated;
        });
        setShelfPage(nextPage);
      } else {
        setHasMoreShelf(false);
      }
    } catch (err) {
      console.error("Failed to load more items", err);
    } finally {
      setIsLoadingMoreShelf(false);
    }
  }, [shelfPage, hasMoreShelf, isLoadingMoreShelf, isShelfView, searchQuery]);

  const sortedBooks = useMemo(() => {
    if (isShelfView) {
      return books;
    }

    return [...books].sort((a, b) => {
      const aVal = (a as any)[sortConfig.key] || '';
      const bVal = (b as any)[sortConfig.key] || '';
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [books, sortConfig, isShelfView]);

  return {
    books,
    setBooks,
    totalBooks,
    setTotalBooks,
    totalReady,
    setTotalReady,
    sortedBooks,
    sortConfig,
    refreshLibrary,
    loadMoreShelf,
    isLoading,
    isLoadingMoreShelf,
    hasMoreShelf,
  };
};
