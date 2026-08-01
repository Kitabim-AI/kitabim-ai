import { useEffect, useRef, useState } from 'react';
import { SearchTabsService, SpellingCheckResult } from '../services/searchTabsService';

interface UseSpellingCheckReturn {
  result: SpellingCheckResult | null;
  isLoading: boolean;
}

export function useSpellingCheck(word: string): UseSpellingCheckReturn {
  const [result, setResult] = useState<SpellingCheckResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const trimmed = word.trim();
    if (!trimmed) {
      setResult(null);
      setIsLoading(false);
      return;
    }

    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    const timer = setTimeout(async () => {
      const data = await SearchTabsService.checkSpelling(trimmed);
      if (requestIdRef.current === requestId) {
        setResult(data);
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [word]);

  return { result, isLoading };
}
