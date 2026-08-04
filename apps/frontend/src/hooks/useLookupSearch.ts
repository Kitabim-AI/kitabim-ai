import { useEffect, useRef, useState } from 'react';

interface UseLookupSearchReturn<T> {
  results: T[];
  isLoading: boolean;
}

export function useLookupSearch<T>(
  searchFn: (q: string, limit: number) => Promise<T[]>,
  query: string,
  minLength: number = 1,
  limit: number = 20
): UseLookupSearchReturn<T> {
  const [results, setResults] = useState<T[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < minLength) {
      setResults([]);
      setIsLoading(false);
      return;
    }

    const requestId = ++requestIdRef.current;
    setIsLoading(true);
    const timer = setTimeout(async () => {
      const data = await searchFn(trimmed, limit);
      if (requestIdRef.current === requestId) {
        setResults(data);
        setIsLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, minLength, limit, searchFn]);

  return { results, isLoading };
}
