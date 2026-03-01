import { useState } from 'react';
import { SpellCorrection, SpellCheckResult } from '../components/spell-check/SpellCheckPanel';
import { authFetch } from '../services/authService';

const API_BASE_URL = '/api';

export const useSpellCheck = (bookId: string, pageNumber: number) => {
  const [isChecking, setIsChecking] = useState(false);
  const [spellCheckResult, setSpellCheckResult] = useState<SpellCheckResult | null>(null);
  const [appliedCorrections, setAppliedCorrections] = useState<Set<string>>(new Set());
  const [ignoredCorrections, setIgnoredCorrections] = useState<Set<string>>(new Set());

  const runSpellCheck = async (pageText: string) => {
    if (!pageText.trim()) return;

    setIsChecking(true);
    setSpellCheckResult(null);
    setAppliedCorrections(new Set());
    setIgnoredCorrections(new Set());

    try {
      const response = await authFetch(
        `${API_BASE_URL}/books/${bookId}/pages/${pageNumber}/spell-check`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        throw new Error('Failed to run spell check');
      }

      const result = await response.json();
      setSpellCheckResult(result);
    } catch (error) {
      console.error('Spell check error:', error);
      alert('Failed to run spell check. Please try again.');
    } finally {
      setIsChecking(false);
    }
  };

  const applyCorrection = (correction: SpellCorrection, currentText: string): string => {
    // Mark as applied
    setAppliedCorrections((prev) => new Set(prev).add(correction.original));

    // Apply the correction to all occurrences in the text
    return currentText.replaceAll(correction.original, correction.corrected);
  };

  const ignoreCorrection = (correction: SpellCorrection) => {
    setIgnoredCorrections((prev) => new Set(prev).add(correction.original));
  };

  const resetSpellCheck = () => {
    setSpellCheckResult(null);
    setAppliedCorrections(new Set());
    setIgnoredCorrections(new Set());
  };

  return {
    isChecking,
    spellCheckResult,
    appliedCorrections,
    ignoredCorrections,
    runSpellCheck,
    applyCorrection,
    ignoreCorrection,
    resetSpellCheck,
  };
};
