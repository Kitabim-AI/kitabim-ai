import React, { useState, useEffect, useCallback, useRef } from 'react';
import { BookOpenCheck, BookOpen, RefreshCw, AlertCircle, ClipboardList } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';
import { useIsEditor, useIsAdmin } from '../../hooks/useAuth';
import { authFetch } from '../../services/authService';
import { PersistenceService } from '../../services/persistenceService';
import { useSpellCheck, SpellIssue } from '../../hooks/useSpellCheck';
import { usePendingCorrections } from '../../hooks/usePendingCorrections';
import { SpellCheckPanel } from './SpellCheckPanel';
import { ReviewPanel } from './ReviewPanel';
import { useNotification } from '../../context/NotificationContext';

interface BookMeta {
  book_id: string;
  title: string;
  author: string | null;
  volume: number | null;
  total_pages: number;
  total_issues: number;
  pages_with_issues: number[];
  first_issue_page: number;
}

const API_BASE = '/api';

export const SpellCheckView: React.FC = () => {
  const { t } = useI18n();
  const { 
    fontSize, 
    selectedBook, 
    currentPage: readerPage,
    setView,
    setSelectedBook,
    setCurrentPage: setGlobalCurrentPage,
    setModal
  } = useAppContext();
  const { addNotification } = useNotification();
  const isEditor = useIsEditor();
  const isAdmin = useIsAdmin();

  const [bookMeta, setBookMeta] = useState<BookMeta | null>(null);
  const [isLoadingBook, setIsLoadingBook] = useState(false);
  const [bookError, setBookError] = useState(false);
  const [isNetworkError, setIsNetworkError] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pagesWithIssues, setPagesWithIssues] = useState<number[]>([]);
  const [pageIssueCounts, setPageIssueCounts] = useState<Record<number, number>>({});
  const [pageText, setPageText] = useState<string | undefined>(undefined);

  const spellCheck = useSpellCheck(bookMeta?.book_id ?? '', currentPage);
  const pendingCorrections = usePendingCorrections();
  const [showReview, setShowReview] = useState(false);
  
  // Guard Refs to prevent parallel fetches and loops during re-renders
  const isFetchingRef = useRef(false);
  const lastFetchTimeRef = useRef(0);
  
  // Stability Refs for capturing current state in callbacks
  const readerPageRef = useRef(readerPage);
  const selectedBookIdRef = useRef(selectedBook?.id);
  const pagesWithIssuesRef = useRef(pagesWithIssues);
  const pendingLengthRef = useRef(pendingCorrections.pending.length);
  const currentPageRef = useRef(currentPage);

  useEffect(() => { readerPageRef.current = readerPage; }, [readerPage]);
  useEffect(() => { selectedBookIdRef.current = selectedBook?.id; }, [selectedBook?.id]);
  useEffect(() => { pagesWithIssuesRef.current = pagesWithIssues; }, [pagesWithIssues]);
  useEffect(() => { pendingLengthRef.current = pendingCorrections.pending.length; }, [pendingCorrections.pending.length]);
  useEffect(() => { currentPageRef.current = currentPage; }, [currentPage]);

  const fetchRandomBook = useCallback(async (isManual = false) => {
    const now = Date.now();
    
    // Safety guard: prevent parallel fetches
    if (isFetchingRef.current) return;
    
    // Safety guard: debounce auto-fetches to prevent storms
    if (!isManual && (now - lastFetchTimeRef.current) < 2000) return;

    isFetchingRef.current = true;
    lastFetchTimeRef.current = now;
    
    setIsLoadingBook(true);
    setBookError(false);
    setIsNetworkError(false);
    
    setBookMeta(null);
    setPageText(undefined);
    setShowReview(false);
    setPageIssueCounts({});
    
    spellCheck.reset();

    try {
      const res = await authFetch(`${API_BASE}/books/spell-check/random-book`);
      if (res.status === 404) {
        setBookError(true);
        setIsLoadingBook(false);
        isFetchingRef.current = false;
        return;
      }
      if (!res.ok) throw new Error();
      
      const data: BookMeta = await res.json();
      setBookMeta(data);
      setPagesWithIssues(data.pages_with_issues);
      
      const rPage = readerPageRef.current;
      const sId = selectedBookIdRef.current;
      const isSameBook = sId === data.book_id;
      const startPage = isSameBook && rPage
        ? (data.pages_with_issues.find(p => p >= rPage) ?? data.first_issue_page)
        : data.first_issue_page;
      
      setCurrentPage(startPage);
    } catch {
      setBookError(true);
      setIsNetworkError(true);
    } finally {
      setIsLoadingBook(false);
      // Wait for React to finish its update cycle
      setTimeout(() => {
        isFetchingRef.current = false;
      }, 300);
    }
  }, [spellCheck.reset]);

  // Load issues and page text whenever bookMeta or currentPage changes
  useEffect(() => {
    if (!bookMeta?.book_id || !currentPage) return;
    spellCheck.loadIssues();
    setPageText(undefined);
    authFetch(`${API_BASE}/books/${bookMeta.book_id}/pages/${currentPage}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data?.text) setPageText(data.text); })
      .catch(() => { });
  }, [bookMeta?.book_id, currentPage, spellCheck.loadIssues]);

  // Sync fresh text from DB after rescanning
  useEffect(() => {
    if (!spellCheck.isScanning && spellCheck.hasLoaded && bookMeta?.book_id) {
      authFetch(`${API_BASE}/books/${bookMeta.book_id}/pages/${currentPage}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => { if (data?.text) setPageText(data.text); });
    }
  }, [spellCheck.isScanning, spellCheck.hasLoaded, bookMeta?.book_id, currentPage]);

  // Auto-start on mount
  useEffect(() => {
    fetchRandomBook(true);
  }, [fetchRandomBook]);

  // Clean up pagesWithIssues
  useEffect(() => {
    if (spellCheck.hasLoaded && !spellCheck.isLoading && spellCheck.issues.length === 0) {
      setPagesWithIssues(prev => prev.filter(p => p !== currentPage));
    }
  }, [spellCheck.issues.length, spellCheck.hasLoaded, spellCheck.isLoading, currentPage]);

  // Propagation rule for pending corrections in the current session
  useEffect(() => {
    if (!bookMeta || !spellCheck.hasLoaded || spellCheck.issues.length === 0) return;

    const localSolutions = new Map<string, any>(
      pendingCorrections.pending
        .filter(p => p.bookId === bookMeta.book_id && !p.isSkip)
        .map(p => [p.originalWord, p])
    );
    const globalSolutions = new Map<string, any>(
      pendingCorrections.pending
        .filter(p => !p.isSkip && (p.isDictionaryAddition || p.isAutoCorrection))
        .map(p => [p.originalWord, p])
    );

    const existingPendingIds = new Set(pendingCorrections.pending.map(p => p.issueId));

    spellCheck.issues.forEach(issue => {
      if (existingPendingIds.has(issue.id)) return;

      const solution = globalSolutions.get(issue.word) || localSolutions.get(issue.word);
      if (solution) {
        pendingCorrections.addPending({
          issueId: issue.id,
          bookId: bookMeta.book_id,
          bookTitle: bookMeta.volume ? `${bookMeta.title} (${bookMeta.volume}-قىسىم)` : bookMeta.title,
          pageNum: currentPage,
          originalWord: issue.word,
          correctedWord: solution.correctedWord,
          isAutoCorrection: solution.isAutoCorrection,
          isDictionaryAddition: solution.isDictionaryAddition,
          isIgnore: solution.isIgnore
        });
      }
    });
  }, [spellCheck.issues, bookMeta, currentPage, pendingCorrections.pending, spellCheck.hasLoaded, pendingCorrections.addPending]);

  // Track issue count per page
  useEffect(() => {
    if (spellCheck.hasLoaded && !spellCheck.isLoading) {
      setPageIssueCounts(prev => ({ ...prev, [currentPage]: spellCheck.issues.length }));
    }
  }, [spellCheck.hasLoaded, spellCheck.isLoading, spellCheck.issues.length, currentPage]);

  const handleNextPage = useCallback(() => {
    const cPage = currentPageRef.current;
    const pws = pagesWithIssuesRef.current;
    const pLen = pendingLengthRef.current;

    const idx = pws.indexOf(cPage);
    const nextIssuePage = idx >= 0
      ? pws[idx + 1]
      : pws.find(p => p > cPage);

    if (nextIssuePage) {
      setCurrentPage(nextIssuePage);
    } else {
      if (pLen > 0) {
        setShowReview(true);
      } else {
        fetchRandomBook(false);
      }
    }
  }, [fetchRandomBook]);

  const handlePrevPage = useCallback(() => {
    const idx = pagesWithIssues.indexOf(currentPage);
    if (idx > 0) {
      setCurrentPage(pagesWithIssues[idx - 1]);
    } else if (currentPage > 1) {
      setCurrentPage(p => p - 1);
    }
  }, [currentPage, pagesWithIssues]);

  const handleAddPending = useCallback(async (
    issueId: number,
    correctedWord: string,
    originalWord: string,
    options?: { isPhrase?: boolean; range?: [number, number]; isAutoCorrection?: boolean; isDictionaryAddition?: boolean; isIgnore?: boolean; isSkip?: boolean }
  ) => {
    if (!bookMeta) return;

    pendingCorrections.addPending({
      issueId,
      bookId: bookMeta.book_id,
      bookTitle: bookMeta.volume ? `${bookMeta.title} (${bookMeta.volume}-قىسىم)` : bookMeta.title,
      pageNum: currentPage,
      originalWord,
      correctedWord,
      range: options?.range,
      isPhrase: options?.isPhrase,
      isAutoCorrection: options?.isAutoCorrection,
      isDictionaryAddition: options?.isDictionaryAddition,
      isIgnore: options?.isIgnore,
      isSkip: options?.isSkip,
    });
  }, [bookMeta, currentPage, pendingCorrections]);

  const toggleSkip = useCallback(async (issueId: number) => {
    const isAlreadySkipped = pendingCorrections.pending.some(p => p.issueId === issueId && p.isSkip);
    if (isAlreadySkipped) {
      const entry = pendingCorrections.pending.find(p => p.issueId === issueId && p.isSkip);
      if (entry) pendingCorrections.removePending(entry.id);
    } else {
      const issue = spellCheck.issues.find(i => i.id === issueId);
      if (issue && bookMeta) {
        await handleAddPending(issueId, issue.word, issue.word, { isSkip: true });
      }
    }
  }, [pendingCorrections.pending, spellCheck.issues, bookMeta, handleAddPending]);

  const handleConfirmAll = useCallback(async () => {
    if (!bookMeta) return;
    
    const hasGlobalChanges = pendingCorrections.pending.some(
      p => p.isAutoCorrection || p.isDictionaryAddition
    );
    
    const affectedCurrentPageEntries = pendingCorrections.pending.filter(
      p => p.bookId === bookMeta.book_id && p.pageNum === currentPage
    );
    
    const result = await pendingCorrections.confirmAll();
    
    if (result.succeededIds.length > 0) {
      if (affectedCurrentPageEntries.some(p => result.succeededIds.includes(p.id))) {
        spellCheck.loadIssues();
      }
      
      if (!result.failedPageNums?.length) {
        setShowReview(false);
        setModal({
          isOpen: true,
          title: t('common.success'),
          message: hasGlobalChanges 
            ? t('spellCheck.confirmSuccessWithWarning') 
            : t('spellCheck.confirmSuccess'),
          type: 'success',
          confirmText: t('common.ok')
        });
      }
    }
  }, [pendingCorrections, bookMeta, currentPage, spellCheck, setModal, t]);

  const handleOpenInReader = useCallback(async () => {
    if (!bookMeta) return;
    try {
      const fullBook = await PersistenceService.getBookById(bookMeta.book_id);
      if (fullBook) {
        setSelectedBook(fullBook);
        setGlobalCurrentPage(currentPage);
        setView('reader');
      }
    } catch (err) {
      console.error('Failed to open book in reader:', err);
    }
  }, [bookMeta, currentPage, setSelectedBook, setGlobalCurrentPage, setView]);

  if (!isEditor) {
    return (
      <div className="h-[calc(100dvh-72px)] sm:h-[calc(100dvh-88px)] md:h-[calc(100dvh-88px)] lg:h-[calc(100dvh-96px)] w-full lg:max-w-5xl lg:mx-auto flex items-center justify-center px-3" dir="rtl">
        <div className="text-center text-slate-400 font-normal" style={{ fontSize: `${fontSize}px` }}>
          {t('auth.signInMessage')}
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-[calc(100dvh-72px)] sm:h-[calc(100dvh-88px)] md:h-[calc(100dvh-88px)] lg:h-[calc(100dvh-96px)] w-full lg:max-w-5xl lg:mx-auto flex flex-col gap-3 md:gap-4 lg:gap-6 px-3 py-3 sm:px-6 md:px-0 lg:py-4"
      dir="rtl"
      lang="ug"
    >
      <div className="hidden lg:flex bg-white/60 backdrop-blur-2xl px-8 py-4 items-center justify-between border border-[#0369a1]/10 shadow-sm group" style={{ borderRadius: '32px' }}>
        <div className="flex items-center gap-5 flex-1 min-w-0">
          <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 icon-shake">
            <BookOpenCheck size={24} className="md:w-7 md:h-7" strokeWidth={2.5} />
          </div>
          <div>
            {bookMeta ? (
              <div className="flex flex-col gap-1">
                <h1 
                  onClick={handleOpenInReader}
                  className="font-normal text-[#1a1a1a] uyghur-text leading-tight flex items-center flex-wrap gap-2 cursor-pointer hover:text-[#0369a1] transition-colors group/title" 
                  style={{ fontSize: `${fontSize + 4}px` }}
                >
                  <span className="group-hover/title:underline underline-offset-4">{bookMeta.title}</span>
                  {bookMeta.author && (
                    <span className="text-base text-slate-400 font-normal">({bookMeta.author})</span>
                  )}
                </h1>
                {bookMeta.volume && (
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-[#0369a1] font-bold uppercase bg-[#0369a1]/10 px-2 py-0.5 rounded-lg">
                      {t('book.volume', { volume: bookMeta.volume })}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <h1 className="font-normal text-[#1a1a1a]" style={{ fontSize: `${fontSize + 4}px` }}>
                {t('spellCheck.title')}
              </h1>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {bookMeta && (
            <div className="hidden md:flex items-center gap-3 px-6 py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl border border-[#0369a1]/10 shadow-inner whitespace-nowrap shrink-0">
              <BookOpen size={18} strokeWidth={2.5} />
              <span className="text-sm font-normal uppercase">
                {t('spellCheck.issueCount', { count: bookMeta.total_issues })}
              </span>
            </div>
          )}
          {pendingCorrections.pending.length > 0 && (
            <button
              onClick={() => setShowReview(prev => !prev)}
              className="flex items-center gap-2 px-5 py-2.5 bg-amber-500 text-white rounded-2xl text-sm font-normal transition-all hover:bg-amber-600 active:scale-95 shadow-lg shadow-amber-500/20 whitespace-nowrap shrink-0"
            >
              <ClipboardList size={16} strokeWidth={2.5} />
              {t('spellCheck.reviewPending', { count: pendingCorrections.pending.length })}
            </button>
          )}
          <button
            onClick={() => fetchRandomBook(true)}
            disabled={isLoadingBook}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#0369a1] text-white rounded-2xl text-sm font-normal transition-all hover:bg-[#0284c7] active:scale-95 disabled:opacity-50 shadow-lg shadow-[#0369a1]/20 whitespace-nowrap shrink-0"
          >
            <RefreshCw size={16} strokeWidth={2.5} className={isLoadingBook ? 'animate-spin' : ''} />
            {t('spellCheck.nextBook')}
          </button>
        </div>
      </div>

      <div className="lg:hidden flex items-center justify-between px-2 py-1">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
            <BookOpenCheck size={18} strokeWidth={2.5} />
          </div>
          {bookMeta && (
            <span 
              onClick={handleOpenInReader}
              className="font-normal text-[#1a1a1a] uyghur-text text-sm line-clamp-1 cursor-pointer active:text-[#0369a1]"
            >
              {bookMeta.title}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {pendingCorrections.pending.length > 0 && (
            <button
              onClick={() => setShowReview(prev => !prev)}
              className="relative p-2 bg-amber-500 text-white rounded-xl transition-all hover:bg-amber-600 active:scale-95"
            >
              <ClipboardList size={16} strokeWidth={2.5} />
              <span className="absolute -top-1 -left-1 w-4 h-4 bg-white text-amber-500 text-[9px] font-bold rounded-full flex items-center justify-center">
                {pendingCorrections.pending.length}
              </span>
            </button>
          )}
          <button
            onClick={() => fetchRandomBook(true)}
            disabled={isLoadingBook}
            className="p-2 bg-[#0369a1]/10 text-[#0369a1] rounded-xl transition-all hover:bg-[#0369a1] hover:text-white active:scale-95 disabled:opacity-50"
          >
            <RefreshCw size={16} strokeWidth={2.5} className={isLoadingBook ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      <div className="flex-1 glass-panel border border-white/60 rounded-[24px] sm:rounded-[40px] flex flex-col p-4 sm:p-6 lg:p-8">
        {(isLoadingBook || !bookMeta || (spellCheck.isLoading && !spellCheck.hasLoaded)) && !bookError && (
          <div className="flex-1 flex flex-col items-center justify-center gap-6 animate-fade-in">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                <BookOpenCheck size={24} className="animate-pulse" />
              </div>
            </div>
            <p className="font-normal text-slate-400 uppercase text-sm animate-pulse text-center">
              {!bookMeta ? t('spellCheck.loadingBook') : t('spellCheck.checking')}
            </p>
          </div>
        )}

        {!isLoadingBook && bookError && (
          <div className="flex-1 flex flex-col items-center justify-center gap-6 animate-fade-in">
            {isNetworkError ? (
              <>
                <div className="p-8 bg-amber-50 text-amber-400 rounded-[40px] shadow-lg shadow-amber-100">
                  <AlertCircle size={48} strokeWidth={1.5} />
                </div>
                <div className="text-center">
                  <p className="font-normal text-[#1a1a1a] text-lg mb-2">{t('spellCheck.loadError')}</p>
                </div>
                <button
                  onClick={() => fetchRandomBook(true)}
                  className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white rounded-2xl text-sm font-normal transition-all hover:bg-[#0284c7] active:scale-95 shadow-lg shadow-[#0369a1]/20"
                >
                  <RefreshCw size={16} strokeWidth={2.5} />
                  {t('common.refresh')}
                </button>
              </>
            ) : (
              <>
                <div className="p-8 bg-emerald-50 text-emerald-400 rounded-[40px] shadow-lg shadow-emerald-100">
                  <BookOpenCheck size={48} strokeWidth={1.5} />
                </div>
                <div className="text-center">
                  <p className="font-normal text-[#1a1a1a] text-lg mb-2">{t('spellCheck.noBooks')}</p>
                  <p className="text-slate-400 text-sm">{t('spellCheck.noBooksDetail')}</p>
                </div>
              </>
            )}
          </div>
        )}

        {showReview && (
          <ReviewPanel
            pending={pendingCorrections.pending}
            isConfirming={pendingCorrections.isConfirming}
            confirmError={pendingCorrections.confirmError}
            fontSize={fontSize}
            onRemove={pendingCorrections.removePending}
            onClearAll={pendingCorrections.clearAll}
            onConfirmAll={handleConfirmAll}
            onClose={() => setShowReview(false)}
            onUndoSkip={toggleSkip}
            onToggleDictionary={isEditor ? pendingCorrections.toggleDictionaryAddition : undefined}
            onToggleAutoCorrection={isEditor ? pendingCorrections.toggleAutoCorrection : undefined}
          />
        )}

        {!showReview && !isLoadingBook && bookMeta && spellCheck.hasLoaded && (() => {
          const globalIssueOffset = pagesWithIssuesRef.current
            .filter(p => p < currentPage)
            .reduce((sum, p) => sum + (pageIssueCounts[p] ?? 0), 0);
          return (
            <div className="flex flex-col">
              <SpellCheckPanel
                pageNumber={currentPage}
                totalPages={bookMeta.total_pages}
                globalIssueOffset={globalIssueOffset}
                totalBookIssues={bookMeta.total_issues}
                pageText={pageText}
                fontSize={fontSize}
                issues={spellCheck.issues}
                isLoading={spellCheck.isLoading}
                isScanning={spellCheck.isScanning}
                hasLoaded={spellCheck.hasLoaded}
                navigationMode="auto"
                skippedIds={pendingCorrections.pending.filter(p => p.isSkip).map(p => p.issueId)}
                onToggleSkip={toggleSkip}
                onAddPending={handleAddPending}
                pendingIssueIds={pendingCorrections.pending.filter(p => p.bookId === bookMeta.book_id).map(p => p.issueId)}
                onRemoveFromPending={(issueId) => {
                  const entry = pendingCorrections.pending.find(p => p.issueId === issueId && p.bookId === bookMeta.book_id);
                  if (entry) pendingCorrections.removePending(entry.id);
                }}
                onNextPage={handleNextPage}
                onPrevPage={handlePrevPage}
                bookTitle={bookMeta.title}
                bookAuthor={bookMeta.author}
              />
            </div>
          );
        })()}
      </div>
    </div>
  );
};
