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
    const trimmedQuery = searchQuery.trim();
    return view === 'library' || view === 'global-chat' || view === 'admin' || (view === 'home' && (trimmedQuery.length >= 3 || !!category));
  }, [view, searchQuery, category]);

  // Reset shelf state whenever the search query or category changes
  useEffect(() => {
    if (isShelfView) {
      setBooks([]);
      setShelfPage(1);
      setHasMoreShelf(true);
    }
  }, [searchQuery, category]); // eslint-disable-line react-hooks/exhaustive-deps

  // Internal Polling for Processing Books (only on admin page)
  useEffect(() => {
    const hasProcessing = books.some(b => 
      (b.pipelineStep && b.pipelineStep !== 'ready') || 
      (b.pipelineStats && Object.entries(b.pipelineStats).some(([k, v]) => k.endsWith('_active') && (v as number) > 0))
    );
    
    if (hasProcessing && view === 'admin') {
      const interval = setInterval(async () => {
        try {
          const currentSize = isShelfView ? Math.max(books.length, COLLECTION_PAGE_SIZE) : pageSize;
          const currentPage = isShelfView ? 1 : page;
          const sortBy = isShelfView ? 'uploadDate' : sortConfig.key;
          const order = isShelfView ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

          const response = await PersistenceService.getGlobalLibrary(currentPage, currentSize, searchQuery, sortBy, order, isShelfView, category);

          setBooks(response.books);
          setTotalBooks(response.total);
          setTotalReady(response.totalReady);
        } catch (e) {
          console.error("Polling failed", e);
        }
      }, 5000); // Poll every 5 seconds for better responsiveness
      return () => clearInterval(interval);
    }
  }, [view, books, isShelfView, searchQuery, sortConfig, pageSize, page, category]);

  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const refreshLibrary = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const trimmedQuery = searchQuery.trim();
    if (trimmedQuery.length > 0 && trimmedQuery.length < 3) {
      setBooks([]);
      setTotalBooks(0);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    try {
      const currentViewSize = isShelfView ? COLLECTION_PAGE_SIZE : pageSize;
      const currentViewPage = isShelfView ? 1 : page;

      const sortBy = isShelfView ? 'uploadDate' : sortConfig.key;
      const order = isShelfView ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

      const response = await PersistenceService.getGlobalLibrary(currentViewPage, currentViewSize, searchQuery, sortBy, order, isShelfView, category, abortController.signal);

      if (abortController.signal.aborted) return;

      setBooks(response.books);
      setTotalBooks(response.total);
      setTotalReady(response.totalReady);

      if (isShelfView) {
        setShelfPage(1);
        setHasMoreShelf(response.books.length < response.total);
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      console.error("Manual refresh failed", err);
    } finally {
      if (!abortController.signal.aborted) {
        setIsLoading(false);
      }
    }
  }, [isShelfView, page, pageSize, searchQuery, sortConfig, category]);

  const loadMoreShelf = useCallback(async () => {
    if (isLoadingMoreShelf || !hasMoreShelf || !isShelfView) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const trimmedQuery = searchQuery.trim();
    if (trimmedQuery.length > 0 && trimmedQuery.length < 3) {
      return;
    }

    setIsLoadingMoreShelf(true);
    const nextPage = shelfPage + 1;
    try {
      const response = await PersistenceService.getGlobalLibrary(nextPage, COLLECTION_PAGE_SIZE, searchQuery, 'uploadDate', -1, true, category, abortController.signal);
      
      if (abortController.signal.aborted) return;

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
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }
      console.error("Failed to load more items", err);
    } finally {
      if (!abortController.signal.aborted) {
        setIsLoadingMoreShelf(false);
      }
    }
  }, [shelfPage, hasMoreShelf, isLoadingMoreShelf, isShelfView, searchQuery, category]);

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
