import { useState, useEffect, useCallback } from 'react';
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

  const removePending = useCallback((id: string) => {
    setPending(prev => prev.filter(p => p.id !== id));
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
      const key = `${p.bookId}::${p.pageNum}`;
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
        ...(p.range ? { range: p.range } : {}),
      }));

      try {
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

  return {
    pending,
    pendingIssueIds: pending.map(p => p.issueId),
    isConfirming,
    confirmError,
    addPending,
    removePending,
    clearAll,
    clearPagePending,
    confirmAll,
  };
};
