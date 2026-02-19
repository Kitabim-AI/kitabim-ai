import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { PageItem } from './PageItem';
import { PersistenceService } from '../../services/persistenceService';

interface VirtualScrollReaderProps {
  bookId: string;
  totalPages: number;
  fontSize: number;
  initialPage?: number;
}

const VirtualScrollReader: React.FC<VirtualScrollReaderProps> = ({
  bookId,
  totalPages,
  fontSize,
  initialPage = 1
}) => {
  const [pages, setPages] = useState<Map<number, any>>(new Map());
  const [currentCenterPage, setCurrentCenterPage] = useState(initialPage);
  const [loadingPages, setLoadingPages] = useState<Set<number>>(new Set());

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const lastFetchTimeRef = useRef<Map<number, number>>(new Map());

  const RATE_LIMIT_MS = 500; // Min time between requests for same page

  // Calculate which pages should be in the window
  const getPageWindow = useCallback((centerPage: number) => {
    const start = Math.max(1, centerPage - 2);
    const end = Math.min(totalPages, centerPage + 2);
    return Array.from({ length: end - start + 1 }, (_, i) => start + i);
  }, [totalPages]);

  // Rate-limited page fetch
  const fetchPage = useCallback(async (pageNumber: number) => {
    const now = Date.now();
    const lastFetch = lastFetchTimeRef.current.get(pageNumber) || 0;

    if (now - lastFetch < RATE_LIMIT_MS) {
      return; // Rate limit
    }

    if (loadingPages.has(pageNumber) || pages.has(pageNumber)) {
      return; // Already loading or loaded
    }

    setLoadingPages(prev => new Set(prev).add(pageNumber));
    lastFetchTimeRef.current.set(pageNumber, now);

    try {
      const result = await PersistenceService.getBookPages(
        bookId,
        pageNumber - 1,
        1
      );

      if (result && result.length > 0) {
        setPages(prev => {
          const newPages = new Map(prev);
          newPages.set(pageNumber, result[0]);
          return newPages;
        });
      }
    } catch (error) {
      console.error(`Failed to fetch page ${pageNumber}:`, error);
    } finally {
      setLoadingPages(prev => {
        const next = new Set(prev);
        next.delete(pageNumber);
        return next;
      });
    }
  }, [bookId, pages, loadingPages]);

  // Load pages in the current window
  const loadWindowPages = useCallback(async (centerPage: number) => {
    const windowPages = getPageWindow(centerPage);

    for (const pageNum of windowPages) {
      if (!pages.has(pageNum) && !loadingPages.has(pageNum)) {
        await fetchPage(pageNum);
      }
    }
  }, [getPageWindow, pages, loadingPages, fetchPage]);

  // Cleanup pages outside the window
  const cleanupOutsideWindow = useCallback((centerPage: number) => {
    const windowPages = new Set(getPageWindow(centerPage));

    setPages(prev => {
      const newPages = new Map();
      for (const [pageNum, page] of prev.entries()) {
        if (windowPages.has(pageNum)) {
          newPages.set(pageNum, page);
        }
      }
      return newPages;
    });

    // Cleanup refs
    for (const [pageNum] of pageRefs.current.entries()) {
      if (!windowPages.has(pageNum)) {
        pageRefs.current.delete(pageNum);
      }
    }
  }, [getPageWindow]);

  // Intersection observer for detecting which page is centered
  useEffect(() => {
    const options = {
      root: null, // Use viewport since parent handles scrolling
      rootMargin: '-20% 0px -20% 0px', // Center detection zone
      threshold: [0, 0.25, 0.5, 0.75, 1]
    };

    const callback = (entries: IntersectionObserverEntry[]) => {
      let mostVisiblePage = currentCenterPage;
      let maxRatio = 0;

      for (const entry of entries) {
        if (entry.isIntersecting && entry.intersectionRatio > maxRatio) {
          const pageNum = parseInt(entry.target.getAttribute('data-page-number') || '0');
          if (pageNum > 0) {
            maxRatio = entry.intersectionRatio;
            mostVisiblePage = pageNum;
          }
        }
      }

      if (maxRatio > 0) {
        setCurrentCenterPage(mostVisiblePage);
      }
    };

    const observer = new IntersectionObserver(callback, options);

    // Observe all page elements
    pageRefs.current.forEach((element) => {
      if (element) {
        observer.observe(element);
      }
    });

    return () => observer.disconnect();
  }, [pages, currentCenterPage]);

  // Load pages when center page changes
  useEffect(() => {
    loadWindowPages(currentCenterPage);
  }, [currentCenterPage, loadWindowPages]);

  // Cleanup old pages
  useEffect(() => {
    cleanupOutsideWindow(currentCenterPage);
  }, [currentCenterPage, cleanupOutsideWindow]);

  // Initial load
  useEffect(() => {
    loadWindowPages(initialPage);
  }, []);

  // Preload adjacent pages
  useEffect(() => {
    const windowPages = getPageWindow(currentCenterPage);
    const minPage = Math.min(...windowPages);
    const maxPage = Math.max(...windowPages);

    // Preload previous page
    if (minPage > 1 && !pages.has(minPage - 1) && !loadingPages.has(minPage - 1)) {
      fetchPage(minPage - 1);
    }

    // Preload next page
    if (maxPage < totalPages && !pages.has(maxPage + 1) && !loadingPages.has(maxPage + 1)) {
      fetchPage(maxPage + 1);
    }
  }, [currentCenterPage, getPageWindow, totalPages, pages, loadingPages, fetchPage]);

  const setPageRef = useCallback((pageNumber: number) => (el: HTMLDivElement | null) => {
    if (el) {
      pageRefs.current.set(pageNumber, el);
    } else {
      pageRefs.current.delete(pageNumber);
    }
  }, []);

  const windowPages = getPageWindow(currentCenterPage);

  return (
    <div
      ref={scrollContainerRef}
      className="max-w-4xl mx-auto select-none"
      onContextMenu={(e) => e.preventDefault()}
    >
      {/* Page indicator */}
      <div className="sticky top-0 z-[1000] bg-white/90 backdrop-blur-sm p-2 mb-4 text-center rounded-lg shadow-sm border border-slate-100">
        <p className="text-sm text-slate-500 font-normal">
          Page {currentCenterPage} of {totalPages}
        </p>
      </div>

      <div className="space-y-8">
        {/* Render pages in window */}
        {windowPages.map(pageNum => {
          const page = pages.get(pageNum);
          const isLoadingThisPage = loadingPages.has(pageNum);

          return (
            <div
              key={pageNum}
              ref={setPageRef(pageNum)}
              data-page-number={pageNum}
              className="mb-8 min-h-[400px] scroll-mt-20"
            >
              {isLoadingThisPage && (
                <div className="flex justify-center items-center min-h-[400px]">
                  <Loader2 className="animate-spin text-[#0369a1]" size={32} />
                </div>
              )}

              {!isLoadingThisPage && page && (
                <PageItem
                  key={`page-${pageNum}`}
                  page={page}
                  fontSize={fontSize}
                  isActive={pageNum === currentCenterPage}
                  isEditing={false}
                  onSetActive={() => setCurrentCenterPage(pageNum)}
                  onEdit={() => { }} // Readers can't edit
                  onReprocess={() => { }} // Readers can't reprocess
                  onSpellCheck={() => { }} // Readers can't spell check
                  tempText=""
                  onTempTextChange={() => { }}
                  onSave={() => { }}
                  onCancel={() => { }}
                  spellCheckResult={null}
                  isLoading={false}
                  isSaving={false}
                />
              )}

              {!isLoadingThisPage && !page && (
                <div className="p-8 text-center bg-slate-50 rounded-2xl border border-dashed border-slate-200">
                  <p className="text-slate-400 font-normal">
                    Page {pageNum} could not be loaded
                  </p>
                </div>
              )}
            </div>
          );
        })}

        {/* Loading indicator at bottom */}
        {loadingPages.size > 0 && (
          <div className="flex justify-center p-4">
            <Loader2 className="animate-spin text-[#0369a1]" size={20} />
          </div>
        )}
      </div>
    </div>
  );
};

export default VirtualScrollReader;
