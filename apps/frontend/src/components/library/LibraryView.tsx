import React from 'react';
import { Database, Zap, Library } from 'lucide-react';
import { Book } from '@shared/types';
import { BookCard } from './BookCard';
import { useI18n } from '../../i18n/I18nContext';

interface LibraryViewProps {
  books: Book[];
  isInitialLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  searchQuery: string;
  onBookClick: (book: Book) => void;
  loaderRef: React.RefObject<HTMLDivElement>;
  loadMore: () => void;
}

export const LibraryView: React.FC<LibraryViewProps> = ({
  books,
  isInitialLoading,
  isLoadingMore,
  hasMore,
  searchQuery,
  onBookClick,
  loaderRef,
  loadMore,
}) => {
  const { t } = useI18n();

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isInitialLoading && hasMore && !isLoadingMore) {
          loadMore();
        }
      },
      { threshold: 0.1, rootMargin: '200px' }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, loadMore, loaderRef, isInitialLoading]);

  return (
    <div className="space-y-12 animate-fade-in" dir="rtl">
      {/* Header Section */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 pb-12 border-b border-[#0369a1]/10 relative">
        <div className="absolute -bottom-px left-0 right-0 h-px bg-gradient-to-l from-[#0369a1]/30 via-transparent to-transparent" />

        <header className="space-y-4">
          <div className="flex items-center gap-4 group">
            <div className="p-3.5 bg-[#0369a1] text-white rounded-[24px] shadow-xl shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
              <Library size={32} strokeWidth={2.5} />
            </div>
            <div>
              <h2 className="text-3xl font-black text-[#1a1a1a] tracking-tight">{t('library.title')}</h2>
              <div className="flex items-center gap-2 mt-2">
                <span className="w-8 h-[2px] bg-[#0369a1] rounded-full" />
                <p className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.2em]">{t('library.subtitle')}</p>
              </div>
            </div>
          </div>
        </header>

        <div className="flex items-center gap-4">
          <div className="flex flex-col items-end">
            <span className="text-[14px] font-black text-[#94a3b8] uppercase tracking-widest mb-1">{t('library.systemStatus')}</span>
            <div className="flex items-center gap-3 px-6 py-2.5 bg-white/60 backdrop-blur-md rounded-2xl border border-[#0369a1]/20 shadow-sm transition-all hover:bg-white">
              <div className="relative flex items-center justify-center">
                <div className="absolute inset-0 bg-emerald-500 rounded-full animate-ping opacity-25" />
                <div className="w-2.5 h-2.5 bg-emerald-500 rounded-full border-2 border-white" />
              </div>
              <span className="text-sm font-black text-[#1a1a1a]">{t('library.active')} • <span className="text-[#0369a1]">{books.length}</span> {t('common.book')}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Grid Section */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-10 gap-y-16 justify-items-center">
        {books.map(book => (
          <BookCard
            key={book.id}
            book={book}
            onClick={onBookClick}
          />
        ))}

        {books.length === 0 && !isInitialLoading && !isLoadingMore && (
          <div className="col-span-full py-40 w-full flex flex-col items-center justify-center glass-panel" style={{ borderRadius: '48px' }}>
            <div className="p-10 bg-[#0369a1]/10 rounded-[48px] mb-8 relative">
              <div className="absolute inset-0 bg-[#0369a1]/10 rounded-[48px] animate-pulse" />
              <Library className="w-24 h-24 text-[#0369a1]" strokeWidth={1.5} />
            </div>
            <h4 className="text-3xl font-black text-[#1a1a1a] mb-4">{t('library.empty.title')}</h4>
            <p className="text-[#94a3b8] font-bold text-lg max-w-md text-center">{t('library.empty.message')}</p>
          </div>
        )}
      </div>

      {/* Infinite Scroll Trigger */}
      <div ref={loaderRef} className="h-64 flex flex-col items-center justify-center gap-6">
        {isLoadingMore ? (
          <div className="flex flex-col items-center gap-5 animate-fade-in">
            <div className="relative">
              <div className="w-14 h-14 border-[5px] border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
              <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                <Zap size={18} strokeWidth={3} className="animate-pulse" />
              </div>
            </div>
            <span className="text-[14px] font-black text-[#0369a1] uppercase tracking-[0.4em] animate-pulse">{t('common.loadingMore')}</span>
          </div>
        ) : !hasMore && books.length > 0 && (
          <div className="flex flex-col items-center gap-4 opacity-30 group transition-all duration-700 hover:opacity-100">
            <div className="w-16 h-[2px] bg-gradient-to-r from-transparent via-[#94a3b8] to-transparent" />
            <Library size={40} className="text-[#94a3b8]" strokeWidth={1} />
            <p className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.5em]">{t('common.endOfList')}</p>
            <div className="w-16 h-[2px] bg-gradient-to-r from-transparent via-[#94a3b8] to-transparent" />
          </div>
        )}
      </div>
    </div>
  );
};
