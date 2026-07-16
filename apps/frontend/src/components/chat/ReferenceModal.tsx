import { BookOpen, ChevronLeft, ChevronRight, Clock, HardDrive, Loader2, X } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { MarkdownContent } from '../common/MarkdownContent';

interface ReferenceModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookId: string;
  pageNumbers: number[];
}

const normalizeArabic = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/\u06E1/g, '\u0652') // Uthmanic Sukun -> Standard Sukun
    .replace(/\u0671/g, '\u0627') // Alif Wasla -> Standard Alif
    .replace(/[\u06D6-\u06DC\u06DF-\u06E0\u06E2-\u06ED]/g, '') // Remove Uthmanic signs that disrupt cursive connections
    ;
};

export const ReferenceModal: React.FC<ReferenceModalProps> = ({
  isOpen,
  onClose,
  bookId,
  pageNumbers,
}) => {
  const { t } = useI18n();
  const isSummaryMode = pageNumbers.length === 0;
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
    if (bookId === 'quran') {
      const initialSurah = pageNumbers[0] ?? 1;
      setCurrentPageNum(initialSurah);
      PersistenceService.getQuranSurah(initialSurah)
        .then(verses => {
          if (verses && verses.length > 0) {
            setBookData({
              title: `${verses[0].surah_name_ug} سۈرىسى`,
              author: `قۇرئان كەرىم (${verses[0].surah_name_ar})`,
              totalPages: 114,
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
  }, [isOpen, bookId, pageNumbers, isSummaryMode, t]);

  useEffect(() => {
    if (bookId === 'quran' && !loading && !pageLoading && currentPageData?.verses) {
      const targetAyah = pageNumbers.slice(1)[0];
      if (targetAyah) {
        const timer = setTimeout(() => {
          const element = document.getElementById(`ayah-${targetAyah}`);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }, 300);
        return () => clearTimeout(timer);
      }
    }
  }, [bookId, loading, pageLoading, currentPageData, pageNumbers]);

  const totalPages: number = bookData?.totalPages ?? 0;
  const navigateToPage = useCallback((newPage: number) => {
    setCurrentPageNum(newPage);
    setPageLoading(true);
    if (bookId === 'quran') {
      PersistenceService.getQuranSurah(newPage)
        .then(verses => {
          if (verses && verses.length > 0) {
            setBookData({
              title: `${verses[0].surah_name_ug} سۈرىسى`,
              author: `قۇرئان كەرىم (${verses[0].surah_name_ar})`,
              totalPages: 114,
            });
            setCurrentPageData({ verses });
          } else {
            setCurrentPageData(null);
          }
          setPageLoading(false);
        })
        .catch(err => {
          console.error("Failed to fetch Quran page:", err);
          setPageLoading(false);
        });
    } else {
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
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-4 md:p-8" dir="rtl" lang="ug">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in transition-all duration-500"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="bg-white/90 dark:bg-slate-900/90 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] md:rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.3)] w-full max-w-4xl max-h-[95vh] sm:max-h-[90vh] relative z-10 overflow-hidden animate-scale-up border border-white/40 dark:border-slate-800/40 flex flex-col">

        {/* Header */}
        <div className="p-4 pb-3 sm:p-6 sm:pb-4 md:p-8 md:pb-6 border-b border-slate-100 dark:border-slate-800 flex items-start justify-between bg-white/50 dark:bg-slate-900/50">
          <div className="flex items-center gap-3 sm:gap-4 md:gap-6">
            <div className="p-2.5 sm:p-3 md:p-4 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-2xl sm:rounded-[24px] shadow-xl shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 shrink-0">
              <BookOpen size={20} strokeWidth={2.5} className="sm:hidden" />
              <BookOpen size={28} strokeWidth={2.5} className="hidden sm:block" />
            </div>
            <div>
              <h3 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] dark:text-slate-100 mb-2 leading-tight flex items-center flex-wrap gap-2 text-right">
                {loading ? t('common.loading') : (
                  <>
                    <span>{bookData?.title || t('chat.referenceTitle')}</span>
                    {bookData?.author && (
                      <span className="text-base sm:text-lg text-slate-400 dark:text-slate-500 font-normal">
                        ({bookData.author})
                      </span>
                    )}
                  </>
                )}
              </h3>
              <div className="flex items-center gap-4 text-[#94a3b8] dark:text-slate-500 text-sm font-normal uppercase tracking-wider">
                {isSummaryMode && (
                  <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8]">
                    {t('chat.bookSummary')}
                  </span>
                )}
                {bookData?.volume && (
                  <span className="flex items-center gap-1.5 px-3 py-1 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-full text-xs">
                    {t('book.volume', { volume: bookData.volume })}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 sm:p-3 hover:bg-red-50 dark:hover:bg-red-500/10 text-slate-300 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 rounded-2xl transition-all active:scale-95 group shrink-0"
          >
            <X size={20} strokeWidth={3} className="sm:hidden" />
            <X size={28} strokeWidth={3} className="hidden sm:block" />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-grow overflow-y-auto p-4 sm:p-6 md:p-10 custom-scrollbar bg-[#f8fafc]/30 dark:bg-slate-950/40">
          {isContentLoading ? (
            <div className="h-64 flex flex-col items-center justify-center gap-6 opacity-40">
              <Loader2 size={48} className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" />
              <p className="text-sm text-slate-400 dark:text-slate-500 font-normal uppercase tracking-widest">{t('common.loading')}</p>
            </div>
          ) : isSummaryMode ? (
            summaryData?.summary ? (
              <div className="max-w-3xl mx-auto">
                <div className="bg-white/80 dark:bg-slate-900/60 p-4 sm:p-6 md:p-10 rounded-[20px] sm:rounded-[24px] md:rounded-[32px] shadow-sm border border-white dark:border-slate-800/80 relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-32 h-32 bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 rounded-bl-[100px] -mr-10 -mt-10" />
                  <MarkdownContent
                    content={summaryData.summary}
                    className="text-base sm:text-lg leading-[2] text-[#1e293b] dark:text-slate-200 relative z-10"
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
            <div className="quran-reference max-w-3xl mx-auto space-y-6">
              {currentPageData.verses.map((v: any) => {
                const isReferenced = pageNumbers.slice(1).includes(v.ayah);
                return (
                  <div
                    key={v.id}
                    id={`ayah-${v.ayah}`}
                    className={`p-6 sm:p-8 rounded-[24px] transition-all duration-300 border ${
                      isReferenced
                        ? 'bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-md ring-2 ring-[#0369a1]/5 dark:ring-[#38bdf8]/5'
                        : 'bg-white/80 dark:bg-slate-900/60 border-slate-100/80 dark:border-slate-800/80 shadow-sm'
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
                        {normalizeArabic(v.text_ar)}
                      </p>
                    </div>
                    {/* Uyghur & English Translations */}
                    <div className="space-y-3 border-t border-slate-50 dark:border-slate-800/60 pt-4 text-right">
                      <p className="uyghur-text text-base sm:text-lg leading-[1.8] text-[#1e293b] dark:text-slate-200 font-normal" dir="rtl">
                        <span className="text-slate-400 dark:text-slate-500 font-normal ml-1">تەرجىمىسى:</span> {v.text_ug}
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
            <div className="max-w-3xl mx-auto">
              <div className="bg-white/80 dark:bg-slate-900/60 p-4 pt-8 sm:p-6 sm:pt-10 md:p-10 md:pt-12 rounded-[20px] sm:rounded-[24px] md:rounded-[32px] shadow-sm border border-white dark:border-slate-800/80 relative overflow-hidden group">
                <div className="absolute top-0 right-0 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 px-4 py-1.5 rounded-bl-[24px] text-sm font-normal shadow-sm z-20 opacity-80 backdrop-blur-md">
                  {t('chat.pageNumber', { page: currentPageNum })}
                </div>
                <div className="absolute top-0 right-0 w-32 h-32 bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 rounded-bl-[100px] -mr-10 -mt-10 transition-transform group-hover:scale-110 duration-700" />
                <MarkdownContent
                  content={currentPageData.text}
                  className="text-base sm:text-lg leading-[2] text-[#1e293b] dark:text-slate-200 relative z-10"
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
        <div className="p-4 px-4 sm:p-4 sm:px-6 md:p-6 md:px-10 bg-white/50 dark:bg-slate-900/50 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
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
                  className="p-2 sm:p-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 text-slate-500 dark:text-slate-300 hover:text-[#0369a1] dark:hover:text-[#38bdf8] rounded-xl transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronRight size={18} />
                </button>
                <button
                  onClick={goToNextPage}
                  disabled={totalPages > 0 && currentPageNum >= totalPages}
                  title={t('common.next')}
                  className="p-2 sm:p-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 text-slate-500 dark:text-slate-300 hover:text-[#0369a1] dark:hover:text-[#38bdf8] rounded-xl transition-all active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <ChevronLeft size={18} />
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="px-4 py-2 sm:px-6 sm:py-2.5 md:px-8 md:py-3 bg-slate-900 dark:bg-slate-800 hover:bg-slate-800 dark:hover:bg-slate-700 text-white dark:text-slate-100 rounded-2xl text-sm font-normal transition-all active:scale-95 shadow-lg shadow-black/10 uppercase tracking-widest"
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
