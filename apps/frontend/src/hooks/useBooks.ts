import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Book, PaginatedBooks } from '@shared/types';
import { PersistenceService } from '../services/persistenceService';

export const useBooks = (view: string, searchQuery: string, pageSize: number, page: number) => {
  const [books, setBooks] = useState<Book[]>([]);
  const [totalBooks, setTotalBooks] = useState(0);
  const [totalReady, setTotalReady] = useState(0);
  const [isLoadingMoreShelf, setIsLoadingMoreShelf] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMoreShelf, setHasMoreShelf] = useState(true);
  const [shelfPage, setShelfPage] = useState(1);
  const SHELF_PAGE_SIZE = 12;

  const [sortConfig, setSortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>(() => {
    const saved = sessionStorage.getItem('kitabim_sort_config');
    if (saved) {
      const parsed = JSON.parse(saved);
      if (parsed.key === 'lastUpdated') return { key: 'uploadDate', direction: 'desc' };
      return parsed;
    }
    return { key: 'uploadDate', direction: 'desc' };
  });

  useEffect(() => {
    sessionStorage.setItem('kitabim_sort_config', JSON.stringify(sortConfig));
  }, [sortConfig]);

  // Internal Polling for Processing Books
  useEffect(() => {
    const hasProcessing = books.some(b => b.status === 'processing');
    if (hasProcessing) {
      const interval = setInterval(async () => {
        try {
          const isShelf = view === 'library';
          const currentSize = isShelf ? Math.max(books.length, SHELF_PAGE_SIZE) : pageSize;
          const currentPage = isShelf ? 1 : page;
          const sortBy = isShelf ? 'uploadDate' : sortConfig.key;
          const order = isShelf ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

          const response = await PersistenceService.getGlobalLibrary(currentPage, currentSize, searchQuery, sortBy, order, isShelf);

          setBooks(prev => {
            // Match and update statuses rather than full replacement if possible, 
            // but for simplicity we replace with the same count.
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
  }, [books.length, books.some(b => b.status === 'processing'), view, searchQuery, sortConfig, pageSize, page]);

  const refreshLibrary = useCallback(async () => {
    setIsLoading(true);
    try {
      const isShelf = view === 'library';
      const currentViewSize = isShelf ? SHELF_PAGE_SIZE : pageSize;
      const currentViewPage = isShelf ? 1 : page;

      const sortBy = isShelf ? 'uploadDate' : sortConfig.key;
      const order = isShelf ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

      const response = await PersistenceService.getGlobalLibrary(currentViewPage, currentViewSize, searchQuery, sortBy, order, isShelf);
      setBooks(response.books);
      setTotalBooks(response.total);
      setTotalReady(response.totalReady);

      if (isShelf) {
        setShelfPage(1);
        setHasMoreShelf(response.books.length < response.total);
      }
    } catch (err) {
      console.error("Manual refresh failed", err);
    } finally {
      setIsLoading(false);
    }
  }, [view, page, pageSize, searchQuery, sortConfig]);

  const loadMoreShelf = useCallback(async () => {
    if (isLoadingMoreShelf || !hasMoreShelf || view !== 'library') return;

    setIsLoadingMoreShelf(true);
    const nextPage = shelfPage + 1;
    try {
      const response = await PersistenceService.getGlobalLibrary(nextPage, SHELF_PAGE_SIZE, searchQuery, 'uploadDate', -1, true);
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
      console.error("Failed to load more shelf items", err);
    } finally {
      setIsLoadingMoreShelf(false);
    }
  }, [shelfPage, hasMoreShelf, isLoadingMoreShelf, view, searchQuery]);

  const sortedBooks = useMemo(() => {
    // For shelf, we follow the backend SORT (uploadDate DESC) to keep pagination stable
    if (view === 'library') {
      return books;
    }

    return [...books].sort((a, b) => {
      const aVal = (a as any)[sortConfig.key] || '';
      const bVal = (b as any)[sortConfig.key] || '';
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [books, sortConfig, view]);

  const toggleSort = (key: string) => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  return {
    books,
    setBooks,
    totalBooks,
    setTotalBooks,
    totalReady,
    setTotalReady,
    sortedBooks,
    sortConfig,
    toggleSort,
    refreshLibrary,
    loadMoreShelf,
    isLoading,
    isLoadingMoreShelf,
    hasMoreShelf,
  };
};
