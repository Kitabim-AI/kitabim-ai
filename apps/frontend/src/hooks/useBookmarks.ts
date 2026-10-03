import { Bookmark } from '@shared/types';
import { useCallback, useEffect, useState } from 'react';
import { PersistenceService } from '../services/persistenceService';
import { useAuth } from './useAuth';

export function useBookmarks(bookId?: string) {
  const { isAuthenticated } = useAuth();
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) {
      setBookmarks([]);
      return;
    }
    setIsLoading(true);
    try {
      const result = await PersistenceService.listBookmarks(bookId);
      setBookmarks(result);
    } finally {
      setIsLoading(false);
    }
  }, [bookId, isAuthenticated]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const create = useCallback(async (pageNumber: number, name: string, quoteText?: string) => {
    if (!bookId) throw new Error('bookId is required to create a bookmark');
    const bookmark = await PersistenceService.createBookmark(bookId, pageNumber, name, quoteText);
    setBookmarks(prev => [...prev, bookmark]);
    return bookmark;
  }, [bookId]);

  const rename = useCallback(async (id: string, name: string) => {
    await PersistenceService.renameBookmark(id, name);
    setBookmarks(prev => prev.map(b => (b.id === id ? { ...b, name } : b)));
  }, []);

  const remove = useCallback(async (id: string) => {
    await PersistenceService.deleteBookmark(id);
    setBookmarks(prev => prev.filter(b => b.id !== id));
  }, []);

  return { bookmarks, isLoading, refresh, create, rename, remove };
}
