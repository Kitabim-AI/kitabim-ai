import React from 'react';
import { X, Search, Library, RefreshCw } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';
import { useBooks } from '../../hooks/useBooks';
import { BookCard } from './BookCard';
import { ProverbDisplay } from '../common/ProverbDisplay';

export const SearchOverlay: React.FC = () => {
  const {
    view,
    globalSearchQuery,
    setGlobalSearchQuery,
    isGlobalSearchOpen,
    setIsGlobalSearchOpen,
    bookActions,
    pageSize
  } = useAppContext();

  const { t } = useI18n();
  const inputRef = React.useRef<HTMLInputElement>(null);

  // The overlay has its own dedicated search fetcher
  const {
    sortedBooks: books,
    totalBooks,
    isLoading,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    loadMoreShelf: loadMore
  } = useBooks('search-overlay', globalSearchQuery, pageSize, 1);

  const loaderRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isLoading && hasMore && !isLoadingMore && books.length > 0) {
          loadMore();
        }
      },
      { threshold: 0.1, rootMargin: '400px' }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, loadMore, isLoading, books.length]);

  // Focus input when overlay appears and freeze background
  React.useEffect(() => {
    if (isGlobalSearchOpen) {
      const originalBodyStyle = document.body.style.overflow;
      const originalHtmlStyle = document.documentElement.style.overflow;
      
      document.body.style.overflow = 'hidden';
      document.documentElement.style.overflow = 'hidden';
      document.body.style.height = '100vh';
      
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          setIsGlobalSearchOpen(false);
          setGlobalSearchQuery('');
        }
      };

      window.addEventListener('keydown', handleKeyDown);

      // Small timeout to ensure DOM is ready after animation start
      const timer = setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
      
      return () => {
         document.body.style.overflow = originalBodyStyle;
         document.documentElement.style.overflow = originalHtmlStyle;
         document.body.style.height = '';
         window.removeEventListener('keydown', handleKeyDown);
         clearTimeout(timer);
      };
    }
  }, [isGlobalSearchOpen, setIsGlobalSearchOpen, setGlobalSearchQuery]);

  if (!isGlobalSearchOpen) return null;

  return (
    <div 
      className="fixed inset-0 z-[110] flex items-center justify-center p-4 sm:p-6 md:p-10 lg:p-12 animate-fade-in bg-slate-900/40 backdrop-blur-3xl" 
      style={{ backdropFilter: 'blur(40px)', WebkitBackdropFilter: 'blur(40px)' }}
      dir="rtl"
    >
      {/* Backdrop for click handling */}
      <div 
        className="absolute inset-0" 
        onClick={() => {
           setIsGlobalSearchOpen(false);
           setGlobalSearchQuery('');
        }}
      />

      {/* Content Container - Giant Modal Style */}
      <div className="relative z-10 w-full max-w-[1400px] h-full h-max-[90dvh] bg-white/95 backdrop-blur-2xl rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.2)] overflow-hidden flex flex-col animate-fade-in border border-white/40">
        {/* Header */}
        <div className="w-full bg-white/50 border-b border-[#0369a1]/10 px-4 py-4 md:px-10 md:py-8 flex items-center gap-3 md:gap-6 shadow-sm">
          {/* Search Icon & Input Group */}
          <div className="flex items-center gap-3 md:gap-4 flex-grow min-w-0">
            <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl md:rounded-2xl shadow-lg shadow-[#0369a1]/20 flex-shrink-0">
              <Search size={22} className="md:w-6 md:h-6" strokeWidth={2.5} />
            </div>
            
            <div className="flex-grow relative group min-w-0">
              <input
                ref={inputRef}
                type="text"
                value={globalSearchQuery}
                onChange={(e) => setGlobalSearchQuery(e.target.value)}
                placeholder={t('home.searchPlaceholder')}
                className="w-full bg-transparent text-lg md:text-2xl font-normal text-[#1a1a1a] outline-none placeholder:text-slate-300 uyghur-text truncate"
              />
              <div className="absolute -bottom-1 left-0 right-0 h-0.5 bg-[#0369a1]/10 group-focus-within:bg-[#0369a1] transition-all rounded-full" />
            </div>
          </div>
          
          {/* Close Button */}
          <button
            onClick={() => {
              setIsGlobalSearchOpen(false);
              setGlobalSearchQuery('');
            }}
            className="p-2 md:p-3 bg-slate-50 text-slate-400 rounded-xl md:rounded-2xl hover:bg-slate-100 hover:text-slate-600 transition-all active:scale-95 flex-shrink-0"
            title={t('common.cancel')}
          >
            <X size={22} className="md:w-6 md:h-6" strokeWidth={2.5} />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-grow overflow-y-auto custom-scrollbar p-6 md:p-10 w-full overflow-x-hidden">
          {books.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-6 gap-y-12 justify-items-center pb-20">
              {books.map(book => (
                <BookCard
                  key={book.id}
                  book={book}
                  onClick={(b) => {
                     setIsGlobalSearchOpen(false);
                     setGlobalSearchQuery('');
                     bookActions.openReader(b);
                  }}
                />
              ))}
            </div>
          ) : !isLoading ? (
            <div className="h-[50vh] flex flex-col items-center justify-center text-center">
              <div className="p-12 bg-[#0369a1]/5 rounded-[48px] mb-8 animate-fade-in">
                {globalSearchQuery.trim().length >= 3 ? (
                  <Library className="w-24 h-24 text-[#0369a1]" strokeWidth={1.5} />
                ) : (
                  <Search className="w-24 h-24 text-[#0369a1]" strokeWidth={1.5} />
                )}
              </div>
              
              <div className="max-w-md mx-auto space-y-4 animate-fade-in">
                {globalSearchQuery.trim().length >= 3 ? (
                  <div className="space-y-4">
                    <h4 className="text-2xl font-black text-[#1a1a1a]">
                      {t('library.noResults.title')}
                    </h4>
                    <p className="text-slate-500 font-bold">
                      {t('library.noResults.message')}
                    </p>
                  </div>
                ) : (
                  <ProverbDisplay 
                    keywords="كىتاب" 
                    size="base" 
                    className="opacity-50" 
                  />
                )}
              </div>
            </div>
          ) : (
            <div className="h-[50vh] flex flex-col items-center justify-center">
              <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin mb-4"></div>
              <span className="text-sm font-black text-[#0369a1] uppercase animate-pulse">{t('common.loading')}...</span>
            </div>
          )}

          {/* Infinite Scroll Trigger */}
          {globalSearchQuery.trim().length >= 3 && (
            <div ref={loaderRef as any} className="py-20 flex flex-col items-center justify-center gap-6">
              {isLoadingMore ? (
                <div className="flex flex-col items-center gap-4 animate-fade-in">
                  <div className="w-10 h-10 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                  <span className="text-[10px] font-black text-[#0369a1] uppercase animate-pulse">{t('common.loadingMore')}</span>
                </div>
              ) : !hasMore && books.length > 0 && (
                <div className="flex flex-col items-center gap-4 opacity-30">
                  <div className="w-16 h-[1px] bg-[#94a3b8]" />
                  <p className="text-[10px] font-black text-[#94a3b8] uppercase">{t('common.endOfList')}</p>
                  <div className="w-16 h-[2px] bg-[#94a3b8]" />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
