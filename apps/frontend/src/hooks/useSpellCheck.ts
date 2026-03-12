import { useState, useCallback } from 'react';
import { authFetch } from '../services/authService';

export interface SpellIssue {
  id: number;
  word: string;
  char_offset: number | null;
  char_end: number | null;
  ocr_corrections: string[];
  status: 'open' | 'corrected' | 'ignored';
}

const API_BASE = '/api';

export const useSpellCheck = (bookId: string, pageNumber: number) => {
  const [isLoading, setIsLoading] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const [issues, setIssues] = useState<SpellIssue[]>([]);
  const [hasLoaded, setHasLoaded] = useState(false);

  const loadIssues = useCallback(async () => {
    if (!bookId || !pageNumber) return;
    setHasLoaded(false); // Bug 4 fix: reset so stale issues don't flash on page change
    setIssues([]);        // Bug 4 fix
    setIsLoading(true);
    try {
      const res = await authFetch(`${API_BASE}/books/${bookId}/pages/${pageNumber}/spell-check`);
      if (!res.ok) throw new Error('Failed to load spell check issues');
      const data: { milestone: string | null; issues: SpellIssue[] } = await res.json();
      setIssues(data.issues.filter((i) => i.status === 'open'));
      setHasLoaded(true);
    } catch (err) {
      console.error('Spell check load error:', err);
    } finally {
      setIsLoading(false);
    }
  }, [bookId, pageNumber]);

  const triggerRecheck = useCallback(async () => {
    if (!bookId || !pageNumber) return;
    setIsScanning(true);
    try {
      const res = await authFetch(
        `${API_BASE}/books/${bookId}/pages/${pageNumber}/spell-check/trigger`,
        { method: 'POST' }
      );
      if (res.ok) {
        // Trigger runs inline on the backend — just reload the fresh results
        await loadIssues();
      }
    } catch (err) {
      console.error('Failed to trigger recheck:', err);
    } finally {
      setIsScanning(false);
    }
  }, [bookId, pageNumber, loadIssues]);

  const applyCorrection = useCallback(
    async (issueId: number, correctedWord: string, options?: { isPhrase?: boolean; range?: [number, number] }) => {
      try {
        const body = options?.isPhrase && options.range
          ? { corrections: [{ issue_id: issueId, corrected_word: correctedWord, range: options.range }] }
          : { corrections: [{ issue_id: issueId, corrected_word: correctedWord }] };

        const res = await authFetch(
          `${API_BASE}/books/${bookId}/pages/${pageNumber}/spell-check/apply`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          }
        );
        if (res.ok) {
          setIssues((prev) => prev.filter((i) => i.id !== issueId));
          return true;
        }
      } catch (err) {
        console.error('Failed to apply correction:', err);
      }
      return false;
    },
    [bookId, pageNumber]
  );

  const ignoreIssue = useCallback(
    async (issueId: number) => {
      try {
        const res = await authFetch(
          `${API_BASE}/books/${bookId}/pages/${pageNumber}/spell-check/ignore`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ issue_ids: [issueId] }),
          }
        );
        if (res.ok) {
          setIssues((prev) => prev.filter((i) => i.id !== issueId));
        }
      } catch (err) {
        console.error('Failed to ignore issue:', err);
      }
    },
    [bookId, pageNumber]
  );

  const updateLocalOffsets = useCallback((afterOffset: number, shift: number) => {
    setIssues((prev) =>
      prev.map((issue) => {
        if (issue.char_offset !== null && issue.char_offset >= afterOffset) {
          return {
            ...issue,
            char_offset: issue.char_offset + shift,
            char_end: (issue.char_end !== null ? issue.char_end + shift : null),
          };
        }
        return issue;
      })
    );
  }, []);

  const reset = useCallback(() => {
    setIssues([]);
    setHasLoaded(false);
    setIsScanning(false);
  }, []);

  return { isLoading, isScanning, issues, hasLoaded, loadIssues, triggerRecheck, applyCorrection, ignoreIssue, updateLocalOffsets, reset };
};
