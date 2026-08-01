import { useCallback, useEffect, useRef, useState } from 'react';
import { Book } from '@shared/types';
import { SearchTabsService } from '../services/searchTabsService';

interface UseContentSearchReturn {
  books: Book[];
  total: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  loadMore: () => void;
}

const MIN_QUERY_LENGTH = 2;

export function useContentSearch(query: string, pageSize: number): UseContentSearchReturn {
  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setBooks([]);
      setTotal(0);
      setPage(1);
      setIsLoading(false);
      return;
    }

    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    const timer = setTimeout(async () => {
      const result = await SearchTabsService.searchBookContent(trimmed, 1, pageSize);
      if (requestIdRef.current === requestId) {
        setBooks(result.books);
        setTotal(result.total);
        setPage(1);
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query, pageSize]);

  const loadMore = useCallback(async () => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH || isLoadingMore) return;

    setIsLoadingMore(true);
    const nextPage = page + 1;
    const result = await SearchTabsService.searchBookContent(trimmed, nextPage, pageSize);
    setBooks((prev) => {
      const existingIds = new Set(prev.map((b) => b.id));
      return [...prev, ...result.books.filter((b) => !existingIds.has(b.id))];
    });
    setTotal(result.total);
    setPage(nextPage);
    setIsLoadingMore(false);
  }, [query, page, pageSize, isLoadingMore]);

  const hasMore = books.length < total;

  return { books, total, isLoading, isLoadingMore, hasMore, loadMore };
}
