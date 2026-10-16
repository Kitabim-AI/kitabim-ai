import { useCallback, useEffect, useRef, useState } from 'react';
import { PersistenceService } from '../services/persistenceService';

export interface LlmSpellCheckPreview {
  baselineText: string | null;
  isChecking: boolean;
  error: string | null;
  runCheck: () => Promise<void>;
  reset: () => void;
}

/**
 * Edit-mode LLM spell check: sends the editor's current text to the
 * non-persisting preview endpoint, swaps the corrected text into the editor,
 * and remembers the pre-check text so changed words can be highlighted.
 */
export const useLlmSpellCheckPreview = (
  bookId: string | undefined,
  pageNumber: number,
  tempText: string,
  onTempTextChange: (text: string) => void,
): LlmSpellCheckPreview => {
  const [baselineText, setBaselineText] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBaselineText(null);
    setIsChecking(false);
    setError(null);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const runCheck = useCallback(async () => {
    if (!bookId || abortRef.current) return;
    const snapshot = tempText;
    const controller = new AbortController();
    abortRef.current = controller;
    setIsChecking(true);
    setError(null);
    try {
      const corrected = await PersistenceService.previewLlmSpellCheck(bookId, pageNumber, snapshot, controller.signal);
      if (controller.signal.aborted) return;
      setBaselineText(snapshot);
      onTempTextChange(corrected);
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsChecking(false);
      }
    }
  }, [bookId, pageNumber, tempText, onTempTextChange]);

  return { baselineText, isChecking, error, runCheck, reset };
};
