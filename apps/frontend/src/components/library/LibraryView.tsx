import { BookMarked, BookOpen, LibraryBig, RefreshCw } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { BookCard } from './BookCard';
import { ReadingBookmarksTab } from './ReadingBookmarksTab';

export const LibraryView: React.FC = () => {
  const {
    sortedBooks: books,
    totalBooks,
    isLoading: isInitialLoading,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    bookActions,
    loaderRef,
    loadMoreShelf: loadMore,
    activeTab,
    setActiveTab,
  } = useAppContext();

  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const [readingBookmarksCount, setReadingBookmarksCount] = useState<number | null>(null);

  const isReadingBookmarksActive =
    isAuthenticated && activeTab === 'reading-bookmarks';

  useEffect(() => {
    if (!isAuthenticated && activeTab === 'reading-bookmarks') {
      setActiveTab('all-books');
    }
  }, [isAuthenticated, activeTab, setActiveTab]);

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

  const libraryTabs = [
    { key: 'all-books' as const, label: t('library.tabs.allBooks'), icon: LibraryBig },
    ...(isAuthenticated
      ? [
          {
            key: 'reading-bookmarks' as const,
            label: t('library.tabs.readingAndBookmarks') || 'ئوقۇۋاتقانلىرىم ۋە خەتكۈشلەر',
            icon: BookMarked,
          },
        ]
      : []),
  ];

  return (
    <div className="space-y-6 sm:space-y-8 px-4 sm:px-6 md:px-0 py-4 sm:py-6" dir="rtl">
      {/* Tab Bar with Count Badge */}
      <div className="flex items-end justify-between gap-3 border-b border-slate-200 dark:border-slate-800 pb-0">
        <div className="flex items-end gap-1.5 overflow-x-auto [scrollbar-width:none]">
          {libraryTabs.map(({ key, label, icon: Icon }) => {
            const isSelected =
              key === 'reading-bookmarks'
                ? isReadingBookmarksActive
                : !isReadingBookmarksActive;
            return (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`flex items-center gap-2 px-4 sm:px-5 py-2.5 sm:py-3 text-xs sm:text-sm font-semibold rounded-t-xl transition-all duration-200 active:scale-95 whitespace-nowrap cursor-pointer ${
                  isSelected
                    ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                    : 'bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-b-0 border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-[#0369a1] dark:hover:text-[#38bdf8]'
                }`}
              >
                <Icon size={16} strokeWidth={2.2} className="shrink-0" />
                <span className="uyghur-text mt-[2px]">{label}</span>
              </button>
            );
          })}
        </div>

        {/* Count Badge */}
        {(!isReadingBookmarksActive || isAuthenticated) && (
          <div className="mb-2 shrink-0 flex items-center gap-2 px-3 sm:px-4 py-1.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-sm">
            {isReadingBookmarksActive ? (
              <>
                <BookMarked size={14} className="sm:w-4 sm:h-4" strokeWidth={2.5} />
                <span className="text-xs sm:text-sm font-normal uppercase">
                  {readingBookmarksCount === null ? (
                    <RefreshCw size={12} className="animate-spin" />
                  ) : (
                    `${readingBookmarksCount} ${t('home.totalBooks')}`
                  )}
                </span>
              </>
            ) : (
              <>
                <BookOpen size={14} className="sm:w-4 sm:h-4" strokeWidth={2.5} />
                <span className="text-xs sm:text-sm font-normal uppercase">
                  {isInitialLoading ? (
                    <RefreshCw size={12} className="animate-spin" />
                  ) : (
                    `${totalBooks} ${t('home.totalBooks')}`
                  )}
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {!isReadingBookmarksActive && (
        <>
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
                  <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] dark:border-t-[#38bdf8] rounded-full animate-spin"></div>
                  <div className="absolute inset-0 flex items-center justify-center text-[#0369a1] dark:text-[#38bdf8]">
                    <LibraryBig className="w-8 h-8 animate-pulse" />
                  </div>
                </div>
                <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('common.loading')}</h3>
              </div>
            )}

            {books.length === 0 && !isInitialLoading && !isLoadingMore && (
              <div className="col-span-full py-40 w-full flex flex-col items-center justify-center glass-panel rounded-[48px]">
                <div className="p-10 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 rounded-[48px] mb-8 relative">
                  <LibraryBig className="w-24 h-24 text-[#0369a1] dark:text-[#38bdf8]" strokeWidth={1.5} />
                </div>
                <h4 className="text-xl sm:text-2xl md:text-3xl font-black text-[#1a1a1a] dark:text-slate-100 mb-4">{t('library.empty.title')}</h4>
                <p className="text-[#94a3b8] dark:text-slate-400 font-bold text-base sm:text-lg max-w-md text-center">{t('library.empty.message')}</p>
              </div>
            )}
          </div>

          {/* Infinite Scroll Trigger & State */}
          <div ref={loaderRef as any} className="h-64 flex flex-col items-center justify-center gap-6">
            {isLoadingMore && !isInitialLoading ? (
              <div className="flex flex-col items-center gap-5 animate-fade-in">
                <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] dark:border-t-[#38bdf8] rounded-full animate-spin"></div>
                <span className="text-xs font-black text-[#0369a1] dark:text-[#38bdf8] uppercase animate-pulse">{t('common.loadingMore')}</span>
              </div>
            ) : !hasMore && books.length > 0 && (
              <div className="flex flex-col items-center gap-4 opacity-30">
                <div className="w-16 h-[1px] bg-[#94a3b8] dark:bg-slate-700" />
                <p className="text-xs font-black text-[#94a3b8] dark:text-slate-500 uppercase">{t('common.endOfList')}</p>
                <div className="w-16 h-[2px] bg-[#94a3b8] dark:bg-slate-700" />
              </div>
            )}
          </div>
        </>
      )}

      {isReadingBookmarksActive && (
        <ReadingBookmarksTab
          onOpenBook={(bookId, pageNumber) => bookActions.openReader({ id: bookId }, pageNumber)}
          onOpenBookmark={(bookId, pageNumber, quoteText) =>
            bookActions.openReader({ id: bookId }, pageNumber, quoteText)
          }
          onCountChange={setReadingBookmarksCount}
        />
      )}
    </div>
  );
};
