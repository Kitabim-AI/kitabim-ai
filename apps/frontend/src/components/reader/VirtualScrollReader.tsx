import { Loader2 } from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useScrollStabilizer } from '../../hooks/useScrollStabilizer';
import { useScrollToPage } from '../../hooks/useScrollToPage';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { PageItem } from './PageItem';
import { GuestAuthWall } from './GuestAuthWall';

const GUEST_PAGE_LIMIT = 20;

interface VirtualScrollReaderProps {
  bookId: string;
  totalPages: number;
  fontSize: number;
  contentFontFamily?: string;
  contentFontClassName?: string;
  initialPage?: number;
  onPageChange?: (page: number) => void;
  scrollParentRef?: React.RefObject<HTMLDivElement>;
  isFullscreen?: boolean;
  isChatCollapsed?: boolean;
  editingPageNum?: number | null;
  tempPageText?: string;
  bookTitle?: string;
  bookAuthor?: string;
  pendingQuoteHighlight?: string | null;
  onQuoteHighlightApplied?: () => void;
  onEdit?: (pageNum: number, text: string) => void;
  onReprocess?: (pageNum: number) => void;
  onTempTextChange?: (text: string) => void;
  onSave?: (pageNum: number, text: string) => void;
  onCancel?: () => void;
  onSetStartPage?: (pageNum: number) => void;
  onToggleToc?: (pageNum: number, nextIsToc: boolean) => void;
  onLlmSpellCheck?: (pageNum: number) => void;
  isSaving?: boolean;
  selectedBookPages?: any[];
  contentPageOffset?: number;
  onTocPageClick?: (targetPage: number) => void;
}

const VirtualScrollReader: React.FC<VirtualScrollReaderProps> = ({
  bookId,
  totalPages,
  fontSize,
  contentFontFamily,
  contentFontClassName,
  initialPage = 1,
  onPageChange,
  scrollParentRef,
  isFullscreen = false,
  isChatCollapsed = false,
  editingPageNum = null,
  tempPageText = '',
  bookTitle,
  bookAuthor,
  pendingQuoteHighlight = null,
  onQuoteHighlightApplied,
  onEdit,
  onReprocess,
  onTempTextChange,
  onSave,
  onCancel,
  onSetStartPage,
  onToggleToc,
  onLlmSpellCheck,
  isSaving = false,
  selectedBookPages = [],
  contentPageOffset,
  onTocPageClick,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const isGuest = !isAuthenticated;
  const effectiveTotalPages = isGuest ? Math.min(totalPages, GUEST_PAGE_LIMIT) : totalPages;
  const sanitizedInitialPage = isGuest ? Math.min(initialPage || 1, GUEST_PAGE_LIMIT) : (initialPage || 1);
  const [pages, setPages] = useState<Map<number, any>>(new Map());
  const [currentCenterPage, setCurrentCenterPage] = useState(sanitizedInitialPage);

  // Sync updated pages from selectedBook into cache map
  useEffect(() => {
    if (selectedBookPages && selectedBookPages.length > 0) {
      setPages(prev => {
        const next = new Map(prev);
        let changed = false;
        selectedBookPages.forEach((p: any) => {
          const existing = next.get(p.pageNumber);
          if (!existing || existing.text !== p.text || existing.status !== p.status) {
            next.set(p.pageNumber, p);
            loadedPagesRef.current.add(p.pageNumber);
            changed = true;
          }
        });
        return changed ? next : prev;
      });
    }
  }, [selectedBookPages]);

  // Refs for transient tracking — mutations here never cause observer rebuilds
  const loadingPagesRef = useRef<Set<number>>(new Set());
  const loadedPagesRef = useRef<Set<number>>(new Set());
  const currentCenterPageRef = useRef(sanitizedInitialPage);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const lastFetchTimeRef = useRef<Map<number, number>>(new Map());
  const isInitialMount = useRef(true);

  // Jump & initial scroll support — see useScrollToPage for how it stays aligned
  // while nearby placeholder pages resolve to real content after the jump.
  const targetPage = sanitizedInitialPage || 1;
  const isScrollingToTargetRef = useScrollToPage({
    containerRef: scrollParentRef as React.RefObject<HTMLElement>,
    getPageElement: useCallback((page: number) => pageRefs.current.get(page), []),
    targetPage,
    targetKey: `${bookId}:${targetPage}`,
    currentCenterPage,
    onScrolled: useCallback((page: number) => {
      currentCenterPageRef.current = page;
      setCurrentCenterPage(page);
    }, []),
  });

  const isEditingAny = editingPageNum !== null;

  // Exiting edit mode (save or cancel) remounts every OTHER page at once (see
  // pageNumbersToRender below) and rebuilds both IntersectionObservers below —
  // exactly the same "content around the target resizes right after a jump"
  // situation useScrollToPage exists for, so reuse it here instead of a
  // one-shot scroll that has nothing to correct itself if something resizes
  // (or the center-detection observer misfires) after its single attempt.
  const [editExitTarget, setEditExitTarget] = useState<{ page: number; key: string } | null>(null);
  const lastEditingPageRef = useRef<number | null>(null);
  useEffect(() => {
    if (editingPageNum !== null) {
      lastEditingPageRef.current = editingPageNum;
    } else if (lastEditingPageRef.current !== null) {
      const page = lastEditingPageRef.current;
      lastEditingPageRef.current = null;
      setEditExitTarget({ page, key: `edit-exit:${bookId}:${page}:${Date.now()}` });
    }
  }, [editingPageNum, bookId]);

  const isScrollingToEditExitTargetRef = useScrollToPage({
    containerRef: scrollParentRef as React.RefObject<HTMLElement>,
    // Inert until a real edit-exit has happened — otherwise this would race
    // the initial jump-to-page scroll above on first mount.
    getPageElement: useCallback(
      (page: number) => (editExitTarget ? pageRefs.current.get(page) : null),
      [editExitTarget]
    ),
    targetPage: editExitTarget?.page ?? 1,
    targetKey: editExitTarget?.key ?? 'edit-exit:none',
    currentCenterPage,
    onScrolled: useCallback((page: number) => {
      currentCenterPageRef.current = page;
      setCurrentCenterPage(page);
      onPageChange?.(page);
    }, [onPageChange]),
  });

  // Dedicated jump target for Table of Contents navigation.
  // Using a unique timestamped key ensures clicks always trigger immediate alignment
  // even if the target page matches where the user was previously centered.
  const [tocJumpTarget, setTocJumpTarget] = useState<{ page: number; key: string } | null>(null);

  const isScrollingToTocJumpTargetRef = useScrollToPage({
    containerRef: scrollParentRef as React.RefObject<HTMLElement>,
    getPageElement: useCallback(
      (page: number) => (tocJumpTarget ? pageRefs.current.get(page) : null),
      [tocJumpTarget]
    ),
    targetPage: tocJumpTarget?.page ?? 1,
    targetKey: tocJumpTarget?.key ?? 'toc-jump:none',
    currentCenterPage,
    onScrolled: useCallback((page: number) => {
      currentCenterPageRef.current = page;
      setCurrentCenterPage(page);
      onPageChange?.(page);
    }, [onPageChange]),
  });

  // Keeps the visible page stationary as off-screen-above placeholders resolve
  // to real content during ordinary scrolling (useScrollToPage handles the
  // equivalent for the initial jump-to-page, edit-exit, and toc-jump settle windows,
  // hence the suppression).
  const isAnyScrollAlignmentActiveRef = useRef<{ current: boolean }>({
    get current() {
      return isScrollingToTargetRef.current || isScrollingToEditExitTargetRef.current || isScrollingToTocJumpTargetRef.current;
    },
  } as React.MutableRefObject<boolean>).current;
  useScrollStabilizer({
    containerRef: scrollParentRef as React.RefObject<HTMLElement>,
    itemsRef: pageRefs,
    suppressedRef: isAnyScrollAlignmentActiveRef,
    resubscribeKey: `${effectiveTotalPages}:${isEditingAny}`,
  });

  const isGuestRef = useRef(isGuest);
  isGuestRef.current = isGuest;

  const RATE_LIMIT_MS = 300;

  // fetchPage depends on bookId and isGuest — stable across page/loading state changes,
  // but updates properly when user logs in from guest mode.
  const fetchPage = useCallback(async (pageNumber: number) => {
    if (isGuestRef.current && pageNumber > GUEST_PAGE_LIMIT) return;
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
  }, [bookId, isGuest]);

  // When a guest logs in, proactively fetch current center page and next pages
  const prevIsGuestRef = useRef(isGuest);
  useEffect(() => {
    const wasGuest = prevIsGuestRef.current;
    prevIsGuestRef.current = isGuest;
    if (wasGuest && !isGuest) {
      const center = currentCenterPageRef.current || 1;
      [center, center + 1, center + 2].forEach(p => {
        if (p <= totalPages) {
          fetchPage(p);
        }
      });
    }
  }, [isGuest, totalPages, fetchPage]);

  // Loading observer — rebuilt when scroll root, page count, or edit mode state changes
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
      rootMargin: '1200px 0px 1200px 0px',
      threshold: 0,
    });

    const currentRefs = pageRefs.current;
    currentRefs.forEach(el => { if (el) loadObserver.observe(el); });
    return () => loadObserver.disconnect();
  }, [effectiveTotalPages, scrollParentRef, fetchPage, isEditingAny]);

  // Center detection observer — reads currentCenterPageRef so it never needs
  // to be rebuilt when the visible page changes (no currentCenterPage in deps)
  useEffect(() => {
    const centerObserver = new IntersectionObserver((entries) => {
      if (isAnyScrollAlignmentActiveRef.current) return;

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
  }, [effectiveTotalPages, scrollParentRef, onPageChange, isEditingAny]);

  // Evict pages far from the current viewport back to unloaded placeholders. Without
  // this, `pages` only ever grows over a reading session — every page ever scrolled
  // past stays fully mounted (and gets fully re-rendered on every subsequent scroll
  // update), which is what drives sustained CPU/battery cost on long books. The window
  // is far wider than the loadObserver's rootMargin so it can't fight with eager-loading.
  const EVICTION_WINDOW = 40;
  useEffect(() => {
    if (isEditingAny || isAnyScrollAlignmentActiveRef.current) return;
    setPages(prev => {
      if (prev.size === 0) return prev;
      let changed = false;
      const next = new Map(prev);
      prev.forEach((_, pageNum) => {
        if (Math.abs(pageNum - currentCenterPage) > EVICTION_WINDOW) {
          next.delete(pageNum);
          loadedPagesRef.current.delete(pageNum);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [currentCenterPage, isEditingAny, isAnyScrollAlignmentActiveRef]);

  // Reset pages cache when bookId changes
  useEffect(() => {
    setPages(new Map());
    loadingPagesRef.current.clear();
    loadedPagesRef.current.clear();
    lastFetchTimeRef.current.clear();
    currentCenterPageRef.current = initialPage;
    setCurrentCenterPage(initialPage);
    isInitialMount.current = true;
  }, [bookId]);

  // Ensure target page is fetched if editing starts
  useEffect(() => {
    if (editingPageNum !== null && !pages.has(editingPageNum)) {
      fetchPage(editingPageNum);
    }
  }, [editingPageNum, pages, fetchPage]);

  const allPageNumbers = React.useMemo(() => Array.from({ length: effectiveTotalPages }, (_, i) => i + 1), [effectiveTotalPages]);
  const pageNumbersToRender = isEditingAny ? [editingPageNum] : allPageNumbers;

  const handlePageSetActive = useCallback(() => { }, []);

  const handlePageEdit = useCallback((pageNum: number, text: string) => {
    onEdit?.(pageNum, text);
  }, [onEdit]);

  const handlePageReprocess = useCallback((pageNum: number) => {
    onReprocess?.(pageNum);
  }, [onReprocess]);

  const handlePageSetStartPage = useCallback((pageNum: number) => {
    onSetStartPage?.(pageNum);
  }, [onSetStartPage]);

  const handlePageToggleToc = useCallback((pageNum: number, nextIsToc: boolean) => {
    onToggleToc?.(pageNum, nextIsToc);
  }, [onToggleToc]);

  const handlePageLlmSpellCheck = useCallback((pageNum: number) => {
    onLlmSpellCheck?.(pageNum);
  }, [onLlmSpellCheck]);

  const handlePageSave = useCallback((pageNum: number, text: string) => {
    setPages(prev => {
      const existing = prev.get(pageNum);
      if (!existing) return prev;
      return new Map(prev).set(pageNum, { ...existing, text });
    });
    onSave?.(pageNum, text);
  }, [onSave]);

  const handlePageCancel = useCallback(() => {
    onCancel?.();
  }, [onCancel]);

  const handleTocPageClick = useCallback((targetPageNum: number) => {
    const safeTarget = isGuestRef.current ? Math.min(targetPageNum, GUEST_PAGE_LIMIT) : targetPageNum;

    // Immediately pre-fetch the target page and its immediate neighbors
    fetchPage(safeTarget);
    if (safeTarget > 1) fetchPage(safeTarget - 1);
    if (safeTarget < effectiveTotalPages) fetchPage(safeTarget + 1);

    setTocJumpTarget({ page: safeTarget, key: `toc-jump:${bookId}:${safeTarget}:${Date.now()}` });
    onTocPageClick?.(targetPageNum);
  }, [bookId, effectiveTotalPages, fetchPage, onTocPageClick]);

  return (
    <div
      data-testid="reader-container"
      className={`w-full mx-auto flex flex-col items-center transition-all duration-300 ${
        isGuest ? 'select-none' : ''
      } ${isChatCollapsed ? 'max-w-6xl' : 'max-w-4xl'} ${
        isEditingAny ? 'h-full flex-1 flex flex-col min-h-0' : ''
      }`}
      onContextMenu={isGuest ? (e) => e.preventDefault() : undefined}
      onCopy={isGuest ? (e) => e.preventDefault() : undefined}
    >
      <div className={`w-full flex flex-col items-center ${isEditingAny ? 'h-full flex-1 flex flex-col min-h-0' : 'space-y-4 pb-64'}`}>
        {pageNumbersToRender.map(pageNum => {
          const page = pages.get(pageNum);
          const isEditingThisPage = editingPageNum === pageNum;
          return (
            <div
              key={`page-${pageNum}`}
              ref={el => { if (el) pageRefs.current.set(pageNum, el); else pageRefs.current.delete(pageNum); }}
              data-page-number={pageNum}
              className={`scroll-mt-32 w-full ${isEditingThisPage ? 'h-full flex-1 flex flex-col min-h-0' : 'min-h-[300px]'}`}
            >
              {page ? (
                <PageItem
                  page={page}
                  fontSize={fontSize}
                  contentFontFamily={contentFontFamily}
                  contentFontClassName={contentFontClassName}
                  isActive={pageNum === currentCenterPage}
                  isEditing={isEditingThisPage}
                  bookId={bookId}
                  bookTitle={bookTitle}
                  bookAuthor={bookAuthor}
                  highlightQuote={pageNum === currentCenterPage ? (pendingQuoteHighlight ?? undefined) : undefined}
                  onHighlightApplied={onQuoteHighlightApplied}
                  onSetActive={handlePageSetActive}
                  onEdit={() => handlePageEdit(pageNum, page.text || '')}
                  onReprocess={() => handlePageReprocess(pageNum)}
                  onSetStartPage={onSetStartPage ? () => handlePageSetStartPage(pageNum) : undefined}
                  onToggleToc={onToggleToc ? (nextIsToc) => handlePageToggleToc(pageNum, nextIsToc) : undefined}
                  onLlmSpellCheck={onLlmSpellCheck ? () => handlePageLlmSpellCheck(pageNum) : undefined}
                  tempText={isEditingThisPage ? tempPageText : ''}
                  onTempTextChange={onTempTextChange}
                  onSave={() => handlePageSave(pageNum, tempPageText)}
                  onCancel={handlePageCancel}
                  isLoading={page.status === 'processing' || page.status === 'indexing'}
                  isSaving={isSaving}
                  isFullscreen={isFullscreen}
                  contentPageOffset={contentPageOffset}
                  onTocPageClick={handleTocPageClick}
                />
              ) : (
                <div className="flex flex-col items-center justify-center min-h-[400px] bg-white/30 dark:bg-slate-900/30 rounded-[32px] border border-dashed border-[#0369a1]/10 dark:border-[#38bdf8]/10">
                  <div className="w-8 h-8 rounded-full border border-[#0369a1]/15 dark:border-[#38bdf8]/15 mb-3 flex items-center justify-center">
                    <span className="text-[10px] font-mono font-bold text-slate-400 dark:text-slate-500">{pageNum}</span>
                  </div>
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 font-bold uppercase tracking-[0.2em]">
                    {t('admin.table.loading')} {pageNum}
                  </p>
                </div>
              )}
            </div>
          );
        })}
        {isGuest && totalPages > GUEST_PAGE_LIMIT && !isEditingAny && (
          <GuestAuthWall />
        )}
      </div>
    </div>
  );
};

export { VirtualScrollReader };
export default VirtualScrollReader;
