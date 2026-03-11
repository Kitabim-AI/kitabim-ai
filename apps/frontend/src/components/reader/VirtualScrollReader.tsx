import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2 } from 'lucide-react';
import { PageItem } from './PageItem';
import { PersistenceService } from '../../services/persistenceService';
import { useI18n } from '../../i18n/I18nContext';

interface VirtualScrollReaderProps {
  bookId: string;
  totalPages: number;
  fontSize: number;
  initialPage?: number;
  onPageChange?: (page: number) => void;
  scrollParentRef?: React.RefObject<HTMLDivElement>;
  isFullscreen?: boolean;
}

const VirtualScrollReader: React.FC<VirtualScrollReaderProps> = ({
  bookId,
  totalPages,
  fontSize,
  initialPage = 1,
  onPageChange,
  scrollParentRef,
  isFullscreen = false,
}) => {
  const { t } = useI18n();
  const [pages, setPages] = useState<Map<number, any>>(new Map());
  const [currentCenterPage, setCurrentCenterPage] = useState(initialPage);

  // Refs for transient tracking — mutations here never cause observer rebuilds
  const loadingPagesRef = useRef<Set<number>>(new Set());
  const loadedPagesRef = useRef<Set<number>>(new Set());
  const currentCenterPageRef = useRef(initialPage);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const lastFetchTimeRef = useRef<Map<number, number>>(new Map());
  const isInitialMount = useRef(true);
  const isProgrammaticScroll = useRef(false);

  const RATE_LIMIT_MS = 300;

  // fetchPage only depends on bookId — stable across page/loading state changes,
  // so the loading observer is never torn down just because a page finished loading.
  const fetchPage = useCallback(async (pageNumber: number) => {
    const now = Date.now();
    const lastFetch = lastFetchTimeRef.current.get(pageNumber) || 0;

    if (now - lastFetch < RATE_LIMIT_MS) return;
    if (loadingPagesRef.current.has(pageNumber) || loadedPagesRef.current.has(pageNumber)) return;

    loadingPagesRef.current.add(pageNumber);
    lastFetchTimeRef.current.set(pageNumber, now);

    try {
      const result = await PersistenceService.getBookPages(bookId, pageNumber - 1, 1);
      if (result && result.length > 0) {
        loadedPagesRef.current.add(pageNumber);
        setPages(prev => new Map(prev).set(pageNumber, result[0]));
      }
    } catch (error) {
      console.error(`Failed to fetch page ${pageNumber}:`, error);
    } finally {
      loadingPagesRef.current.delete(pageNumber);
    }
  }, [bookId]);

  // Loading observer — only rebuilt when scroll root or page count changes
  useEffect(() => {
    const loadObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const pageNum = parseInt(entry.target.getAttribute('data-page-number') || '0');
          if (pageNum > 0) fetchPage(pageNum);
        }
      });
    }, {
      root: scrollParentRef?.current || null,
      rootMargin: '1000px 0px 1000px 0px',
      threshold: 0,
    });

    const currentRefs = pageRefs.current;
    currentRefs.forEach(el => { if (el) loadObserver.observe(el); });
    return () => loadObserver.disconnect();
  }, [totalPages, scrollParentRef, fetchPage]);

  // Center detection observer — reads currentCenterPageRef so it never needs
  // to be rebuilt when the visible page changes (no currentCenterPage in deps)
  useEffect(() => {
    const centerObserver = new IntersectionObserver((entries) => {
      if (isProgrammaticScroll.current) return;

      let mostVisiblePage = -1;
      let maxRatio = 0;

      entries.forEach(entry => {
        if (entry.isIntersecting && entry.intersectionRatio > maxRatio) {
          const pageNum = parseInt(entry.target.getAttribute('data-page-number') || '0');
          if (pageNum > 0) {
            maxRatio = entry.intersectionRatio;
            mostVisiblePage = pageNum;
          }
        }
      });

      if (mostVisiblePage !== -1 && mostVisiblePage !== currentCenterPageRef.current) {
        currentCenterPageRef.current = mostVisiblePage;
        setCurrentCenterPage(mostVisiblePage);
        onPageChange?.(mostVisiblePage);
      }
    }, {
      root: scrollParentRef?.current || null,
      rootMargin: '-45% 0px -45% 0px',
      threshold: [0, 0.5, 1],
    });

    const currentRefs = pageRefs.current;
    currentRefs.forEach(el => { if (el) centerObserver.observe(el); });
    return () => centerObserver.disconnect();
  }, [totalPages, scrollParentRef, onPageChange]);

  // Handle initialPage changes (Jump support)
  useEffect(() => {
    if (isInitialMount.current || initialPage !== currentCenterPageRef.current) {
      const target = pageRefs.current.get(initialPage);
      if (target) {
        isProgrammaticScroll.current = true;
        target.scrollIntoView({ behavior: isInitialMount.current ? 'auto' : 'smooth', block: 'start' });
        currentCenterPageRef.current = initialPage;
        setCurrentCenterPage(initialPage);

        setTimeout(() => {
          isProgrammaticScroll.current = false;
        }, 1000);
      }
      isInitialMount.current = false;
    }
  }, [initialPage]);

  const allPageNumbers = Array.from({ length: totalPages }, (_, i) => i + 1);

  return (
    <div className="w-full max-w-4xl mx-auto select-none flex flex-col items-center" onContextMenu={(e) => e.preventDefault()}>
      <div className="w-full space-y-16 pb-64 flex flex-col items-center">
        {allPageNumbers.map(pageNum => {
          const page = pages.get(pageNum);
          return (
            <div
              key={`page-${pageNum}`}
              ref={el => { if (el) pageRefs.current.set(pageNum, el); else pageRefs.current.delete(pageNum); }}
              data-page-number={pageNum}
              className="scroll-mt-32 min-h-[300px] w-full"
            >
              {page ? (
                <PageItem
                  page={page}
                  fontSize={fontSize}
                  isActive={pageNum === currentCenterPage}
                  isEditing={false}
                  onSetActive={() => { }}
                  onEdit={() => { }}
                  onReprocess={() => { }}
                  tempText=""
                  onTempTextChange={() => { }}
                  onSave={() => { }}
                  onCancel={() => { }}
                  isLoading={false}
                  isSaving={false}
                  isFullscreen={isFullscreen}
                />
              ) : (
                <div className="flex flex-col items-center justify-center min-h-[400px] bg-white/30 rounded-[32px] border border-dashed border-[#0369a1]/10 animate-pulse">
                  <Loader2 className="animate-spin text-[#0369a1]/20 mb-4" size={32} />
                  <p className="text-[10px] text-slate-300 font-black uppercase tracking-[0.2em]">
                    {t('admin.table.loading')} {pageNum}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default VirtualScrollReader;
