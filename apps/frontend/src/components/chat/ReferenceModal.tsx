import { BookOpen, ChevronLeft, ChevronRight, Clock, HardDrive, Loader2, Network, X } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { MarkdownContent } from '../common/MarkdownContent';
import { GraphView } from '../graph/GraphView';

interface ReferenceModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookId: string;
  pageNumbers: number[];
  isGraph?: boolean;
  graphQuery?: string;
}

import { formatQuranAyahUg, normalizeArabicWithAyah } from '../../utils/quranUtils';

export const ReferenceModal: React.FC<ReferenceModalProps> = ({
  isOpen,
  onClose,
  bookId,
  pageNumbers,
  isGraph = false,
  graphQuery,
}) => {
  const { t } = useI18n();
  const isGraphMode = isGraph || bookId === 'graph' || bookId === 'knowledge_graph';
  const isSummaryMode = !isGraphMode && pageNumbers.length === 0;
  const [currentPageNum, setCurrentPageNum] = useState<number>(pageNumbers[0] ?? 1);
  const [currentPageData, setCurrentPageData] = useState<any | null>(null);
  const [summaryData, setSummaryData] = useState<{ summary: string; generatedAt: string | null } | null>(null);
  const [bookData, setBookData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen || !bookId) return;
    setLoading(true);
    setCurrentPageData(null);
    if (isGraphMode) {
      if (bookId && bookId !== 'graph' && bookId !== 'knowledge_graph') {
        PersistenceService.getBookById(bookId)
          .then(book => { setBookData(book); setLoading(false); })
          .catch(() => { setLoading(false); });
      } else {
        setLoading(false);
      }
    } else if (bookId === 'quran') {
      const initialSurah = pageNumbers[0] ?? 1;
      const initialAyah = pageNumbers.slice(1)[0] ?? 1;
      setCurrentPageNum(initialAyah);
      PersistenceService.getQuranSurah(initialSurah)
        .then(verses => {
          if (verses && verses.length > 0) {
            setBookData({
              title: `${verses[0].surah_name_ug} سۈرىسى`,
              author: `قۇرئان كەرىم (${verses[0].surah_name_ar})`,
              totalPages: verses.length,
            });
            setCurrentPageData({ verses });
          } else {
            setBookData({
              title: t('chat.referenceTitle'),
              author: 'قۇرئان كەرىم',
              totalPages: 114,
            });
            setCurrentPageData(null);
          }
          setLoading(false);
        })
        .catch(err => {
          console.error("Failed to fetch Quran reference data:", err);
          setLoading(false);
        });
    } else if (isSummaryMode) {
      Promise.all([
        PersistenceService.getBookSummary(bookId),
        PersistenceService.getBookById(bookId),
      ]).then(([summary, book]) => {
        setSummaryData(summary);
        setBookData(book);
        setLoading(false);
      }).catch(err => {
        console.error("Failed to fetch summary data:", err);
        setLoading(false);
      });
    } else {
      const initialPage = pageNumbers[0] ?? 1;
      setCurrentPageNum(initialPage);
      Promise.all([
        PersistenceService.getBookById(bookId),
        PersistenceService.getPage(bookId, initialPage),
      ]).then(([book, page]) => {
        setBookData(book);
        setCurrentPageData(page);
        setLoading(false);
      }).catch(err => {
        console.error("Failed to fetch reference data:", err);
        setLoading(false);
      });
    }
  }, [isOpen, bookId, pageNumbers, isSummaryMode, isGraphMode, t]);

  // No scroll-to-ayah needed when paginating ayahs directly

  const totalPages: number = bookData?.totalPages ?? 0;
  const navigateToPage = useCallback((newPage: number) => {
    setCurrentPageNum(newPage);
    if (bookId !== 'quran') {
      setPageLoading(true);
      PersistenceService.getPage(bookId, newPage)
        .then(page => { setCurrentPageData(page); setPageLoading(false); })
        .catch(err => { console.error("Failed to fetch page:", err); setPageLoading(false); });
    }
  }, [bookId]);

  const goToPrevPage = useCallback(() => {
    if (currentPageNum > 1) navigateToPage(currentPageNum - 1);
  }, [currentPageNum, navigateToPage]);

  const goToNextPage = useCallback(() => {
    const next = currentPageNum + 1;
    if (totalPages === 0 || next <= totalPages) navigateToPage(next);
  }, [currentPageNum, totalPages, navigateToPage]);

  if (!isOpen) return null;

  const isContentLoading = loading || pageLoading;

  const modalContent = (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-4 md:p-6 pt-[max(0.5rem,env(safe-area-inset-top))] pb-[max(0.5rem,env(safe-area-inset-bottom))]" dir="rtl" lang="ug">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in transition-all duration-500"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] shadow-2xl w-full max-w-4xl max-h-[calc(100dvh-2rem)] sm:max-h-[85vh] relative z-10 overflow-hidden animate-scale-up border border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex flex-col">

        {/* Header Ribbon */}
        <div className="px-3 sm:px-6 py-2 sm:py-4 border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex items-center justify-between gap-2 sm:gap-4 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm shrink-0">
          <div className="flex items-center gap-2 sm:gap-4 min-w-0 flex-shrink">
            <div className="flex items-center justify-center min-w-[40px] min-h-[40px] w-10 h-10 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shrink-0">
              {isGraphMode ? (
                <Network size={20} />
              ) : (
                <BookOpen size={20} />
              )}
            </div>
            <div className="min-w-0 flex flex-col justify-center">
              <h2 className="font-bold text-[#1a1a1a] dark:text-slate-100 truncate text-base sm:text-lg leading-tight flex items-center flex-wrap gap-2 text-right">
                {loading ? t('common.loading') : isGraphMode ? (
                  <>
                    <span className="truncate">{t('graph.title')}</span>
                    {bookData?.title && (
                      <span className="text-xs sm:text-sm text-[#64748b] dark:text-slate-400 font-normal">
                        («{bookData.title}»)
                      </span>
                    )}
                  </>
                ) : (
                  <>
                    <span className="truncate">{bookData?.title || t('chat.referenceTitle')}</span>
                    {bookData?.volume ? ` (${t('book.volume', { volume: bookData.volume })})` : ''}
                  </>
                )}
              </h2>
              {bookData?.author && (
                <p className="text-[#64748b] dark:text-slate-400 text-xs sm:text-sm mt-0.5 truncate hidden sm:block">
                  {bookData.author}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-red-200 dark:border-red-900/30 text-red-400 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 hover:text-red-500 dark:hover:text-red-400 flex items-center justify-center shrink-0"
            title={t('common.close')}
          >
            <X size={18} className="sm:w-5 sm:h-5" />
          </button>
        </div>

        {/* Reading Canvas */}
        <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 custom-scrollbar paper-background">
          {isGraphMode ? (
            <div className="w-full h-full min-h-[500px] flex flex-col">
              <GraphView
                initialBookId={bookId !== 'graph' && bookId !== 'knowledge_graph' ? bookId : undefined}
                initialQuery={graphQuery}
                isModal={true}
              />
            </div>
          ) : isContentLoading ? (
            <div className="h-64 flex flex-col items-center justify-center gap-6 opacity-40">
              <Loader2 size={48} className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" />
              <p className="text-sm text-slate-400 dark:text-slate-500 font-normal uppercase tracking-widest">{t('common.loading')}</p>
            </div>
          ) : isSummaryMode ? (
            summaryData?.summary ? (
              <div className="w-full max-w-4xl mx-auto">
                <div className="bg-white dark:bg-slate-900/60 p-6 rounded-[24px] shadow-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 relative">
                  <div className="flex items-center justify-between mb-4 border-b border-[#0369a1]/5 dark:border-slate-800 pb-3">
                    <div />
                    <span className="text-xs font-bold text-[#94a3b8] dark:text-slate-500 uppercase flex items-center gap-1.5">
                      <span>{t('chat.bookSummary')}</span>
                    </span>
                  </div>
                  <MarkdownContent
                    content={summaryData.summary}
                    className="uyghur-text text-[#1a1a1a] dark:text-slate-100"
                    style={{ fontSize: '18px' }}
                  />
                </div>
              </div>
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-center gap-4 opacity-40">
                <HardDrive size={48} className="text-slate-300 dark:text-slate-600" />
                <p className="text-sm sm:text-base text-slate-400 dark:text-slate-500 font-normal">{t('chat.noContentFound')}</p>
              </div>
            )
          ) : bookId === 'quran' && currentPageData?.verses ? (
            <div className="quran-reference w-full max-w-4xl mx-auto space-y-4">
              {currentPageData.verses
                .filter((v: any) => v.ayah === currentPageNum)
                .map((v: any) => {
                  const isReferenced = pageNumbers.slice(1).includes(v.ayah);
                return (
                  <div
                    key={v.id}
                    id={`ayah-${v.ayah}`}
                    className={`p-6 rounded-[24px] transition-all duration-300 border ${
                      isReferenced
                        ? 'bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-md ring-2 ring-[#0369a1]/5 dark:ring-[#38bdf8]/5'
                        : 'bg-white dark:bg-slate-900/60 shadow-xl border-[#0369a1]/10 dark:border-[#38bdf8]/10'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-4 border-b border-slate-100/60 dark:border-slate-800/60 pb-3">
                      <span className={`px-3 py-1 rounded-full text-xs font-normal ${
                        isReferenced
                          ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8]'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                      }`}>
                        {v.ayah}-ئايەت
                      </span>
                      {isReferenced && (
                        <span className="text-xs text-[#0369a1] dark:text-[#38bdf8] font-normal">
                          مەنبە قىلىنغان ئايەت
                        </span>
                      )}
                    </div>
                    {/* Arabic Text */}
                    <div className="text-right mb-6" dir="rtl">
                      <p className="arabic-text text-3xl sm:text-4xl leading-[2] sm:leading-[2.2] text-slate-900 dark:text-slate-100 font-normal whitespace-pre-wrap select-all">
                        {normalizeArabicWithAyah(v.text_ar, v.ayah)}
                      </p>
                    </div>
                    {/* Uyghur & English Translations */}
                    <div className="space-y-3 border-t border-slate-50 dark:border-slate-800/60 pt-4 text-right">
                      <p className="uyghur-text text-base sm:text-lg leading-[1.8] text-[#1e293b] dark:text-slate-200 font-normal" dir="rtl">
                        <span className="text-slate-400 dark:text-slate-500 font-normal ml-1">تەرجىمىسى:</span> {formatQuranAyahUg(v.text_ug)}
                      </p>
                      <p className="text-sm text-slate-500 dark:text-slate-400 font-sans leading-relaxed text-left" dir="ltr">
                        <span className="text-slate-400 dark:text-slate-500 font-normal mr-1">English:</span> {v.text_en}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : currentPageData?.text ? (
            <div className="w-full max-w-4xl mx-auto">
              <div className="group relative p-6 rounded-[24px] bg-white dark:bg-slate-900/60 shadow-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10">
                <div className="flex items-center justify-between mb-4 border-b border-[#0369a1]/5 dark:border-slate-800 pb-3">
                  <div />
                  <span className="text-xs font-bold text-[#94a3b8] dark:text-slate-500 uppercase flex items-center gap-1.5">
                    <span>{t('chat.pageNumber', { page: currentPageNum })}</span>
                  </span>
                </div>
                <MarkdownContent
                  content={currentPageData.text}
                  className="uyghur-text text-[#1a1a1a] dark:text-slate-100"
                  style={{ fontSize: '18px' }}
                />
              </div>
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center gap-4 opacity-40">
              <HardDrive size={48} className="text-slate-300 dark:text-slate-600" />
              <p className="text-sm sm:text-base text-slate-400 dark:text-slate-500 font-normal">{t('chat.noContentFound')}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-3 sm:px-6 py-2 sm:py-4 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border-t border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3 sm:gap-6 text-xs text-slate-400 dark:text-slate-500 font-normal">
            <div className="flex items-center gap-2">
              <Clock size={14} />
              {t('common.lastUpdated')}: {isSummaryMode
                ? (summaryData?.generatedAt ? new Date(summaryData.generatedAt).toLocaleDateString() : '-')
                : (bookData?.lastUpdated ? new Date(bookData.lastUpdated).toLocaleDateString() : '-')}
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {!isSummaryMode && (
              <>
                <button
                  onClick={goToPrevPage}
                  disabled={currentPageNum <= 1}
                  title={t('common.previous')}
                  className="p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                >
                  <ChevronRight size={18} />
                </button>
                <button
                  onClick={goToNextPage}
                  disabled={totalPages > 0 && currentPageNum >= totalPages}
                  title={t('common.next')}
                  className="p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center"
                >
                  <ChevronLeft size={18} />
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 sm:px-6 sm:py-2.5 bg-slate-900 dark:bg-slate-800 hover:bg-slate-800 dark:hover:bg-slate-700 text-white dark:text-slate-100 rounded-xl text-xs sm:text-sm font-normal transition-all active:scale-95 shadow-md"
            >
              {t('common.close')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};
