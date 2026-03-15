import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Book, PaginatedBooks } from '@shared/types';
import { PersistenceService } from '../services/persistenceService';
import { useAuth } from './useAuth';

export const useBooks = (view: string, searchQuery: string, pageSize: number, page: number, category?: string) => {
  const { isAuthenticated } = useAuth();
  const [books, setBooks] = useState<Book[]>([]);
  const [totalBooks, setTotalBooks] = useState(0);
  const [totalReady, setTotalReady] = useState(0);
  const [isLoadingMoreShelf, setIsLoadingMoreShelf] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMoreShelf, setHasMoreShelf] = useState(true);
  const [shelfPage, setShelfPage] = useState(1);
  const COLLECTION_PAGE_SIZE = 40;

  const [sortConfig] = useState<{ key: string; direction: 'asc' | 'desc' }>({ key: 'uploadDate', direction: 'desc' });

  // Pipeline stats are now lazy-loaded on-demand (click refresh button) for performance
  const includeStats = false;

  // Helper to determine if we should use shelf-style (infinite scroll) behavior
  const isShelfView = useMemo(() => {
    const trimmedQuery = searchQuery.trim();
    return view === 'library' || view === 'admin' || (view === 'home' && (trimmedQuery.length >= 3 || !!category));
  }, [view, searchQuery, category]);

  // Sorting/Grouping policy: Disabled to show all volumes of multi-volume books
  const groupByWork = useMemo(() => {
    return false; // Show all volumes instead of grouping by work
  }, [view, searchQuery, category]);

  const lastRequestIdRef = useRef(0);
  const lastParamsRef = useRef('');
  const isInitializedRef = useRef(false);

  const fetchBooks = useCallback(async (isManualRefresh = false) => {
    const trimmedQuery = searchQuery.trim();
    const currentParams = `${view}-${searchQuery}-${pageSize}-${page}-${category}-${groupByWork}-${isAuthenticated}`;

    // Skip loading books for views that don't need them
    if (view === 'global-chat' || view === 'reader' || view === 'join-us' || view === 'spell-check') {
      setBooks([]);
      setTotalBooks(0);
      setTotalReady(0);
      lastParamsRef.current = view;
      setIsLoading(false);
      return;
    }

    // For home view, only load books if there's a search query or category filter
    if (view === 'home') {
      if (trimmedQuery.length === 0 && !category) {
        setBooks([]);
        setTotalBooks(0);
        setTotalReady(0);
        lastParamsRef.current = `home-empty`;
        setIsLoading(false);
        return;
      }
    }

    if (trimmedQuery.length > 0 && trimmedQuery.length < 3) {
      setBooks([]);
      setTotalBooks(0);
      setTotalReady(0);
      lastParamsRef.current = `query-short`;
      setIsLoading(false);
      return;
    }

    if (!isManualRefresh && currentParams === lastParamsRef.current) {
      return;
    }
    lastParamsRef.current = currentParams;

    const requestId = ++lastRequestIdRef.current;
    setIsLoading(true);
    isInitializedRef.current = false; 
    
    if (!isManualRefresh) {
      setBooks([]);
      setTotalBooks(0);
      setTotalReady(0);
      setShelfPage(1);
    }

    try {
      const currentViewSize = isShelfView ? COLLECTION_PAGE_SIZE : pageSize;
      const currentViewPage = isShelfView ? 1 : page;
      const sortBy = isShelfView ? 'uploadDate' : sortConfig.key;
      const order = isShelfView ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

      const response = await PersistenceService.getGlobalLibrary(
        currentViewPage,
        currentViewSize,
        searchQuery,
        sortBy,
        order,
        groupByWork,
        category,
        includeStats
      );

      if (requestId !== lastRequestIdRef.current) return;

      setBooks(response.books);
      setTotalBooks(response.total);
      setTotalReady(response.totalReady);

      if (isShelfView) {
        setHasMoreShelf(response.books.length < response.total);
      }
      isInitializedRef.current = true;
    } catch (err) {
      if (requestId !== lastRequestIdRef.current) return;
      console.error("Fetch books failed", err);
    } finally {
      if (requestId === lastRequestIdRef.current) {
        setIsLoading(false);
      }
    }
  }, [view, isShelfView, groupByWork, page, pageSize, searchQuery, sortConfig, category, COLLECTION_PAGE_SIZE, isAuthenticated]);

  useEffect(() => {
    fetchBooks();
  }, [fetchBooks]);

  const refreshLibrary = useCallback(() => {
    fetchBooks(true);
  }, [fetchBooks]);

  const loadMoreShelf = useCallback(async () => {
    if (isLoadingMoreShelf || !hasMoreShelf || !isShelfView || isLoading || !isInitializedRef.current || books.length === 0) {
      return;
    }

    setIsLoadingMoreShelf(true);
    const nextPage = shelfPage + 1;
    const requestId = lastRequestIdRef.current; 

    try {
      const sortBy = isShelfView ? 'uploadDate' : sortConfig.key;
      const order = isShelfView ? -1 : (sortConfig.direction === 'asc' ? 1 : -1);

      const response = await PersistenceService.getGlobalLibrary(
        nextPage,
        COLLECTION_PAGE_SIZE,
        searchQuery,
        sortBy,
        order,
        groupByWork,
        category,
        includeStats
      );
      
      if (requestId !== lastRequestIdRef.current) return;

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
  }, [shelfPage, hasMoreShelf, isLoadingMoreShelf, isShelfView, groupByWork, searchQuery, sortConfig, category, COLLECTION_PAGE_SIZE, isLoading]);

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
