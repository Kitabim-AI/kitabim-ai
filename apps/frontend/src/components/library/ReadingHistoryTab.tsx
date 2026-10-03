import React, { useState, useEffect, useMemo } from 'react';
import { Search, X, BookOpen, Clock } from 'lucide-react';
import { ReadingProgressEntry } from '@shared/types';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { GuestAuthWall } from '../reader/GuestAuthWall';

interface ReadingHistoryTabProps {
  onOpenBook: (bookId: string, pageNumber?: number) => void;
  onCountChange?: (count: number) => void;
  onBrowseBooks?: () => void;
}

export const ReadingHistoryTab: React.FC<ReadingHistoryTabProps> = ({
  onOpenBook,
  onCountChange,
  onBrowseBooks,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();

  const [items, setItems] = useState<ReadingProgressEntry[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [query, setQuery] = useState<string>('');

  useEffect(() => {
    if (!isAuthenticated) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    const fetchProgress = async () => {
      setIsLoading(true);
      try {
        const progressList = await PersistenceService.listReadingProgress();
        if (!isMounted) return;
        setItems(progressList);
      } catch (err) {
        console.error('Failed to load reading progress', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchProgress();
    return () => {
      isMounted = false;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    onCountChange?.(items.length);
  }, [items.length, onCountChange]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => (item.bookTitle || '').toLowerCase().includes(q));
  }, [items, query]);

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  const formatRelativeDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString();
    } catch {
      return '';
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-fade-in" dir="rtl">
      {/* Search Header */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
            <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('library.readingHistory.searchPlaceholder')}
            className="w-full pr-12 md:pr-14 pl-10 md:pl-12 py-3 md:py-3.5 bg-white/80 dark:bg-slate-900/60 backdrop-blur-md border border-slate-200/80 dark:border-slate-800 rounded-2xl md:rounded-[22px] text-sm md:text-base text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-[#0369a1]/10 dark:focus:ring-[#38bdf8]/10 focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all duration-300 shadow-sm uyghur-text"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-72 bg-white/40 dark:bg-slate-900/40 rounded-2xl animate-pulse border border-slate-200/40 dark:border-slate-800/40"
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && filteredItems.length === 0 && (
        <div className="text-center py-16 px-4 bg-white/60 dark:bg-slate-900/40 backdrop-blur-md rounded-3xl border border-slate-200/80 dark:border-slate-800 max-w-lg mx-auto shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 flex items-center justify-center mx-auto mb-4 text-[#0369a1] dark:text-[#38bdf8]">
            <BookOpen size={32} strokeWidth={1.75} />
          </div>
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 uyghur-text mb-2">
            {t('library.readingHistory.empty')}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 uyghur-text mb-6">
            {t('library.readingHistory.emptyHint')}
          </p>
          {onBrowseBooks && (
            <button
              onClick={onBrowseBooks}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 font-semibold text-sm shadow-sm hover:opacity-95 transition-all"
            >
              <span className="uyghur-text">{t('library.readingHistory.browseBooks')}</span>
            </button>
          )}
        </div>
      )}

      {/* Books Grid */}
      {!isLoading && filteredItems.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6">
          {filteredItems.map((item) => (
            <div
              key={item.bookId}
              role="button"
              tabIndex={0}
              onClick={() => onOpenBook(item.bookId, item.pageNumber)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenBook(item.bookId, item.pageNumber);
                }
              }}
              className="group cursor-pointer flex flex-col bg-white dark:bg-slate-900/80 rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-md hover:border-[#0369a1]/40 dark:hover:border-[#38bdf8]/40 transition-all duration-300 transform hover:-translate-y-1"
            >
              {/* Cover Container */}
              <div className="relative aspect-[3/4] w-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                {item.bookCoverUrl ? (
                  <img
                    src={item.bookCoverUrl}
                    alt={item.bookTitle || ''}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center p-4 text-center text-slate-400">
                    <BookOpen size={36} strokeWidth={1.5} className="opacity-50" />
                  </div>
                )}

                {/* Last Page Pill Overlay */}
                {item.pageNumber && (
                  <div className="absolute top-2 right-2 bg-slate-950/80 backdrop-blur-md text-white px-2.5 py-1 rounded-lg text-xs font-semibold uyghur-text shadow-sm border border-white/10">
                    {t('library.readingHistory.lastReadPage', { page: item.pageNumber })}
                  </div>
                )}
              </div>

              {/* Title & Metadata */}
              <div className="p-3.5 flex flex-col justify-between flex-1 gap-2">
                <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 line-clamp-2 uyghur-text group-hover:text-[#0369a1] dark:group-hover:text-[#38bdf8] transition-colors leading-snug">
                  {item.bookTitle}
                </h4>
                <div className="flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                  <Clock size={12} />
                  <span>{formatRelativeDate(item.updatedAt)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
