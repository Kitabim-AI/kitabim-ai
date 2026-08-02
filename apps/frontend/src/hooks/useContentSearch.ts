import { useCallback, useEffect, useRef, useState } from 'react';
import { ContentSearchHit, SearchTabsService } from '../services/searchTabsService';

interface UseContentSearchReturn {
  hits: ContentSearchHit[];
  total: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  loadMore: () => void;
}

const MIN_QUERY_LENGTH = 2;

export function useContentSearch(query: string, pageSize: number): UseContentSearchReturn {
  const [hits, setHits] = useState<ContentSearchHit[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      setHits([]);
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
        setHits(result.hits || []);
        setTotal(result.total || 0);
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
    setHits((prev) => {
      const existingIds = new Set(prev.map((h) => h.id));
      const newHits = (result.hits || []).filter((h) => !existingIds.has(h.id));
      return [...prev, ...newHits];
    });
    setTotal(result.total || 0);
    setPage(nextPage);
    setIsLoadingMore(false);
  }, [query, page, pageSize, isLoadingMore]);

  const hasMore = hits.length < total;

  return { hits, total, isLoading, isLoadingMore, hasMore, loadMore };
}

