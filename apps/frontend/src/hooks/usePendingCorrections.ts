import { useCallback, useEffect, useMemo, useState } from 'react';
import { authFetch } from '../services/authService';

export interface PendingCorrection {
  id: string;
  issueId: number;
  bookId: string;
  bookTitle?: string;
  pageNum: number;
  originalWord: string;
  correctedWord: string;
  range?: [number, number];
  isPhrase?: boolean;
  isAutoCorrection?: boolean;
  isDictionaryAddition?: boolean;
  isIgnore?: boolean;
  isSkip?: boolean;
  addedAt: number;
}

export interface ConfirmResult {
  succeededIds: string[];
  failedPageNums: number[];
  failedReason?: string;
}

const API_BASE = '/api';
const STORAGE_KEY = 'spellcheck-pending-v1';

export const usePendingCorrections = () => {
  const [pending, setPending] = useState<PendingCorrection[]>([]);
  const [isConfirming, setIsConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  // Load from global localStorage key on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      setPending(stored ? JSON.parse(stored) : []);
    } catch {
      setPending([]);
    }
  }, []);

  // Persist to localStorage on every change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(pending));
    } catch (err) {
      console.warn('usePendingCorrections: localStorage write failed', err);
    }
  }, [pending]);

  const addPending = useCallback((correction: Omit<PendingCorrection, 'id' | 'addedAt'>) => {
    setPending(prev => {
      if (prev.some(p => p.issueId === correction.issueId && p.bookId === correction.bookId)) return prev;
      return [...prev, { ...correction, id: crypto.randomUUID(), addedAt: Date.now() }];
    });
  }, []);

  const removePending = useCallback((ids: string | string[]) => {
    const idsToRemove = Array.isArray(ids) ? ids : [ids];
    setPending(prev => prev.filter(p => !idsToRemove.includes(p.id)));
  }, []);

  const toggleDictionaryAddition = useCallback((ids: string | string[]) => {
    const idsToToggle = Array.isArray(ids) ? ids : [ids];
    setPending(prev => {
      if (idsToToggle.length === 0) return prev;
      const firstItem = prev.find(p => p.id === idsToToggle[0]);
      if (!firstItem) return prev;
      const targetState = !firstItem.isDictionaryAddition;
      
      return prev.map(p => {
        if (!idsToToggle.includes(p.id)) return p;
        return { 
          ...p, 
          isDictionaryAddition: targetState,
          isIgnore: targetState || p.isIgnore
        };
      });
    });
  }, []);

  const toggleAutoCorrection = useCallback((ids: string | string[]) => {
    const idsToToggle = Array.isArray(ids) ? ids : [ids];
    setPending(prev => {
      if (idsToToggle.length === 0) return prev;
      const firstItem = prev.find(p => p.id === idsToToggle[0]);
      if (!firstItem) return prev;
      const targetState = !firstItem.isAutoCorrection;
      
      return prev.map(p => {
        if (!idsToToggle.includes(p.id)) return p;
        return { ...p, isAutoCorrection: targetState };
      });
    });
  }, []);

  const clearAll = useCallback(() => {
    setPending([]);
  }, []);

  const clearPagePending = useCallback((bookId: string, pageNum: number) => {
    setPending(prev => prev.filter(p => !(p.bookId === bookId && p.pageNum === pageNum)));
  }, []);

  const confirmAll = useCallback(async (): Promise<ConfirmResult> => {
    if (pending.length === 0) {
      return { succeededIds: [], failedPageNums: [] };
    }

    setIsConfirming(true);
    setConfirmError(null);

    const succeededIds: string[] = [];
    const failedPageNums: number[] = [];
    let failedReason: string | undefined;

    // Group by bookId + pageNum, sorted by bookId then pageNum
    const byBookPage = new Map<string, PendingCorrection[]>();
    for (const p of pending) {
      let key = '';
      if (p.isDictionaryAddition) key = `dict::${p.originalWord}`;
      else if (p.isIgnore) key = `ignore::${p.bookId}::${p.pageNum}`;
      else if (p.isSkip) key = `skip::${p.issueId}`; // Skips are local, but we group them to be safe
      else key = `${p.bookId}::${p.pageNum}`;
      
      const arr = byBookPage.get(key) ?? [];
      arr.push(p);
      byBookPage.set(key, arr);
    }
    const sortedKeys = [...byBookPage.keys()].sort();

    outer: for (const key of sortedKeys) {
      const group = byBookPage.get(key)!;
      const { bookId, pageNum } = group[0];
      const corrections = group.map(p => ({
        issue_id: p.issueId,
        corrected_word: p.correctedWord,
        original_word: p.originalWord,
        ...(p.range ? { range: p.range } : {}),
        is_auto_correction: !!p.isAutoCorrection,
        is_dictionary_addition: !!p.isDictionaryAddition,
      }));

      try {
        if (group[0].isDictionaryAddition) {
          const res = await authFetch(`${API_BASE}/spell-check/dictionary`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word: group[0].originalWord }),
          });
          if (res.ok) {
            for (const p of group) succeededIds.push(p.id);
          } else {
            failedPageNums.push(pageNum);
            failedReason = `Dictionary update failed for word ${group[0].originalWord}`;
            break outer;
          }
        } else if (group[0].isIgnore) {
          const res = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNum}/spell-check/ignore`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ issue_ids: group.map(p => p.issueId) }),
          });
          if (res.ok) {
            for (const p of group) succeededIds.push(p.id);
          } else {
            failedPageNums.push(pageNum);
            failedReason = `Failed to ignore issues on page ${pageNum}`;
            break outer;
          }
        } else if (group[0].isSkip) {
          // Skips don't need a backend call — just mark as succeeded to remove from pending
          for (const p of group) succeededIds.push(p.id);
        } else {
          const res = await authFetch(
            `${API_BASE}/books/${bookId}/pages/${pageNum}/spell-check/apply`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ corrections }),
            }
          );
          if (res.ok) {
            for (const p of group) succeededIds.push(p.id);
          } else {
            failedPageNums.push(pageNum);
            failedReason = `Page ${pageNum} returned ${res.status}`;
            break outer;
          }
        }
      } catch (err) {
        failedPageNums.push(pageNum);
        failedReason = err instanceof Error ? err.message : 'Network error';
        break outer;
      }
    }

    if (succeededIds.length > 0) {
      setPending(prev => prev.filter(p => !succeededIds.includes(p.id)));
    }

    if (failedPageNums.length > 0) {
      setConfirmError(failedReason ?? 'Some pages failed to save');
    }

    setIsConfirming(false);
    return { succeededIds, failedPageNums, failedReason };
  }, [pending]);

  return useMemo(() => ({
    pending,
    pendingIssueIds: pending.map(p => p.issueId),
    isConfirming,
    confirmError,
    addPending,
    removePending,
    clearAll,
    clearPagePending,
    confirmAll,
    toggleDictionaryAddition,
    toggleAutoCorrection
  }), [
    pending,
    isConfirming,
    confirmError,
    addPending,
    removePending,
    clearAll,
    clearPagePending,
    confirmAll,
    toggleDictionaryAddition,
    toggleAutoCorrection
  ]);
};
