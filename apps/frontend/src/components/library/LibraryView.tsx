import React, { useEffect } from 'react';
import { Zap, LibraryBig, BookOpen, RefreshCw } from 'lucide-react';
import { ProverbDisplay } from '../common/ProverbDisplay';
import { BookCard } from './BookCard';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

export const LibraryView: React.FC = () => {
  const {
    sortedBooks: books,
    totalBooks,
    isLoading: isInitialLoading,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    bookActions,
    loaderRef,
    loadMoreShelf: loadMore
  } = useAppContext();

  const { t } = useI18n();

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isInitialLoading && hasMore && !isLoadingMore && books.length > 0) {
          loadMore();
        }
      },
      { threshold: 0.1, rootMargin: '1200px' }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, loadMore, loaderRef, isInitialLoading]);

  return (
    <div className="space-y-8 sm:space-y-10 md:space-y-12 px-4 sm:px-6 md:px-0 py-4 sm:py-6 md:py-8" dir="rtl">
      {/* Header Section */}
      <div className="pb-8 sm:pb-10 md:pb-12 border-b border-[#0369a1]/10 relative">
        <header className="space-y-3 sm:space-y-4">
          <div className="flex items-center gap-3 sm:gap-4 group">
            <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 icon-shake">
              <LibraryBig size={20} className="md:w-6 md:h-6" strokeWidth={2.5} />
            </div>
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl sm:text-3xl font-black text-[#1a1a1a]">{t('library.title')}</h2>
                <div className="flex items-center gap-2 px-3 sm:px-5 py-1.5 sm:py-2 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl border border-[#0369a1]/10 shadow-inner">
                  <BookOpen size={14} className="sm:w-[18px] sm:h-[18px]" strokeWidth={2.5} />
                  <span className="text-xs sm:text-sm font-normal uppercase">
                    {isInitialLoading ? <RefreshCw size={12} className="animate-spin" /> : `${totalBooks} ${t('home.totalBooks')}`}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2 mt-1 sm:mt-2">
                <span className="w-6 sm:w-8 h-[2px] bg-[#0369a1] rounded-full" />
                <ProverbDisplay size="sm" keywords={t('proverbs.library')} className="opacity-70 mt-[-2px]" />
              </div>
            </div>
          </div>
        </header>
      </div>

      {/* Grid Section */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-3 sm:gap-x-8 gap-y-8 sm:gap-y-12 justify-items-center">
        {books.map(book => (
          <BookCard
            key={book.id}
            book={book}
            onClick={bookActions.openReader}
          />
        ))}

        {isInitialLoading && books.length === 0 && (
          <div className="col-span-full py-40 w-full flex flex-col items-center justify-center">
            <div className="relative mb-6">
              <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
              <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                <LibraryBig className="w-8 h-8 animate-pulse" />
              </div>
            </div>
            <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
          </div>
        )}

        {books.length === 0 && !isInitialLoading && !isLoadingMore && (
          <div className="col-span-full py-40 w-full flex flex-col items-center justify-center glass-panel rounded-[48px]">
            <div className="p-10 bg-[#0369a1]/10 rounded-[48px] mb-8 relative">
              <LibraryBig className="w-24 h-24 text-[#0369a1]" strokeWidth={1.5} />
            </div>
            <h4 className="text-xl sm:text-2xl md:text-3xl font-black text-[#1a1a1a] mb-4">{t('library.empty.title')}</h4>
            <p className="text-[#94a3b8] font-bold text-base sm:text-lg max-w-md text-center">{t('library.empty.message')}</p>
          </div>
        )}
      </div>

      {/* Infinite Scroll Trigger */}
      <div ref={loaderRef as any} className="h-64 flex flex-col items-center justify-center gap-6">
        {isLoadingMore && !isInitialLoading ? (
          <div className="flex flex-col items-center gap-5 animate-fade-in">
            <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
            <span className="text-xs font-black text-[#0369a1] uppercase animate-pulse">{t('common.loadingMore')}</span>
          </div>
        ) : !hasMore && books.length > 0 && (
          <div className="flex flex-col items-center gap-4 opacity-30">
            <div className="w-16 h-[1px] bg-[#94a3b8]" />
            <p className="text-xs font-black text-[#94a3b8] uppercase">{t('common.endOfList')}</p>
            <div className="w-16 h-[2px] bg-[#94a3b8]" />
          </div>
        )}
      </div>
    </div>
  );
};
