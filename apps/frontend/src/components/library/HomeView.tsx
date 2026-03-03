import React, { useState, useEffect, useRef } from 'react';
import { Search, Book as BookIcon, ArrowRight, X, RefreshCw } from 'lucide-react';
import { BookCard } from './BookCard';
import { PersistenceService } from '../../services/persistenceService';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

export const HomeView: React.FC = () => {
  const {
    sortedBooks: books,
    isLoading: isInitialLoading,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    homeSearchQuery: searchQuery,
    setHomeSearchQuery: setSearchQuery,
    selectedCategory,
    setSelectedCategory,
    bookActions,
    loaderRef
  } = useAppContext();

  const { t } = useI18n();
  const [proverb, setProverb] = useState<{ text: string; volume: number; pageNumber: number } | null>(null);
  const [topCategories, setTopCategories] = useState<string[]>([]);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const fetchProverb = async () => {
      try {
        const data = await PersistenceService.getRandomProverb();
        setProverb(data);
      } catch (e) {
        console.error('Error fetching proverb:', e);
      }
    };
    const fetchCategories = async () => {
      try {
        const categories = await PersistenceService.getTopCategories(5);
        setTopCategories(categories);
      } catch (e) {
        console.error('Error fetching categories:', e);
      }
    };
    fetchProverb();
    fetchCategories();
  }, []);

  const { loadMoreShelf } = useAppContext();

  const hasSearch = searchQuery.length > 0 || selectedCategory.length > 0;

  useEffect(() => {
    if (!hasSearch) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isInitialLoading && hasMore && !isLoadingMore) {
          loadMoreShelf();
        }
      },
      { threshold: 0.1, rootMargin: '200px' }
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasSearch, hasMore, isLoadingMore, loadMoreShelf, loaderRef, isInitialLoading]);

  const handleCategoryClick = (category: string) => {
    setSelectedCategory(category);
    setSearchQuery('');
  };

  return (
    <div className={`flex flex-col items-center transition-all duration-1000 ${hasSearch ? 'pt-4 sm:pt-6' : 'pt-8 sm:pt-12 md:pt-20'}`} dir="rtl" lang="ug">
      {/* Brand & Hero Section */}
      <div className={`text-center mb-6 sm:mb-8 md:mb-10 transition-all duration-1000 ${hasSearch ? 'scale-75 opacity-70 mb-4' : 'scale-100 opacity-100'}`}>
        <div className="flex flex-col items-center gap-2 mb-4 sm:mb-6">
          <div className="px-4 sm:px-6 py-2 bg-[#0369a1] text-white rounded-full text-xs sm:text-sm font-normal uppercase mb-3 sm:mb-4 border border-[#0369a1]/20 shadow-[0_8px_20px_rgba(3,105,161,0.2)]">
            {t('app.tagline')}
          </div>
          <h1
            className={`font-black text-[#1a1a1a] leading-none transition-all duration-1000 ${hasSearch
              ? 'text-2xl sm:text-3xl md:text-4xl'
              : 'text-4xl sm:text-5xl md:text-6xl lg:text-7xl'
              }`}
          >
            Kitabim<span className="text-[#0369a1]">.AI</span>
          </h1>
        </div>

        {proverb ? (
          <div className="flex flex-col items-center gap-1">
            <p className={`uyghur-text font-normal text-[#1a1a1a] leading-relaxed italic max-w-3xl px-4 sm:px-6 transition-all duration-700 ${hasSearch
              ? 'text-base sm:text-lg md:text-xl opacity-60'
              : 'text-lg sm:text-xl md:text-2xl opacity-100'
              }`}>
              {proverb.text}
            </p>
          </div>
        ) : (
          <p className="text-[#94a3b8] font-bold text-lg sm:text-xl mb-6 sm:mb-8">{t('app.welcome')}</p>
        )}
      </div>

      {/* Search Section */}
      <div className="w-full max-w-3xl px-4 relative mb-8 sm:mb-10 md:mb-12">
        <div className="relative group">
          <div className="absolute inset-y-0 right-0 pr-4 sm:pr-6 flex items-center pointer-events-none text-[#94a3b8] group-focus-within:text-[#0369a1] transition-colors z-10">
            {isInitialLoading && searchQuery ? (
              <RefreshCw size={20} className="sm:w-[22px] sm:h-[22px] animate-spin" strokeWidth={3} />
            ) : (
              <Search size={20} className="sm:w-[22px] sm:h-[22px]" strokeWidth={3} />
            )}
          </div>
          <input
            ref={searchInputRef}
            type="text"
            className="w-full px-12 sm:px-16 py-4 sm:py-5 bg-white/60 backdrop-blur-2xl border-2 border-[#0369a1]/10 rounded-[32px] text-base sm:text-lg font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none focus:border-[#0369a1] focus:ring-[12px] focus:ring-[#0369a1]/5 transition-all shadow-xl uyghur-text"
            placeholder={t('home.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            dir="rtl"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 left-0 pl-4 sm:pl-6 flex items-center text-[#94a3b8] hover:text-[#0369a1] transition-colors z-10 min-w-[44px] min-h-[44px]"
            >
              <X size={22} className="sm:w-[24px] sm:h-[24px]" strokeWidth={3} />
            </button>
          )}
        </div>

        {/* Categories helper */}
        {!hasSearch && topCategories.length > 0 && (
          <div className="mt-8 sm:mt-10 md:mt-12 flex flex-wrap justify-center gap-2 sm:gap-3 px-4">
            <span className="w-full text-center text-xs sm:text-sm font-normal text-[#94a3b8] uppercase mb-2 sm:mb-4">{t('home.topCategories')}</span>
            {topCategories.map(cat => (
              <button
                key={cat}
                onClick={() => handleCategoryClick(cat)}
                className="px-4 sm:px-6 py-2.5 min-h-[48px] sm:min-h-0 bg-white/40 backdrop-blur-md border border-[#75C5F0]/10 rounded-2xl text-sm font-normal text-[#1a1a1a] hover:bg-[#75C5F0] hover:text-white transition-all active:scale-95 shadow-sm hover:shadow-lg hover:shadow-[#75C5F0]/20"
              >
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results Section */}
      {hasSearch && (
        <div className="w-full max-w-none px-4 md:px-8 pb-24 sm:pb-32">
          <div className="flex flex-col md:flex-row md:items-center justify-between mb-10 sm:mb-12 md:mb-16 gap-4">
            <div className="flex items-center gap-3 sm:gap-4">
              <button
                onClick={() => { setSearchQuery(''); setSelectedCategory(''); }}
                className="p-3 min-w-[44px] min-h-[44px] bg-white/40 hover:bg-[#0369a1] text-[#0369a1] hover:text-white rounded-2xl transition-all shadow-sm active:scale-90"
              >
                <ArrowRight size={22} className="sm:w-[24px] sm:h-[24px] rotate-180" strokeWidth={3} />
              </button>
              <div>
                <h2 className="text-xl sm:text-2xl md:text-3xl font-normal text-[#1a1a1a]">{t('home.searchResults')}</h2>
                <p className="text-[11px] sm:text-[12px] md:text-[14px] font-normal text-[#94a3b8] uppercase mt-1">«{searchQuery || selectedCategory}» {t('home.resultsFor')}</p>
              </div>
            </div>
            <div className="px-4 sm:px-6 py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl text-xs sm:text-sm font-normal shadow-inner border border-[#0369a1]/5 w-fit">
              <span className="opacity-60">{t('common.total')}</span> {books.length} <span className="opacity-60">{t('home.totalBooks')}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-3 sm:gap-x-8 gap-y-8 sm:gap-y-12 justify-items-center">
            {books.map(book => (
              <BookCard
                key={book.id}
                book={book}
                onClick={bookActions.openReader}
              />
            ))}
          </div>

          {books.length === 0 && !isInitialLoading && (
            <div className="w-full py-20 text-center glass-panel flex flex-col items-center justify-center rounded-[32px]">
              <div className="p-6 bg-[#0369a1]/10 rounded-[32px] mb-6">
                <BookIcon className="w-16 h-16 text-[#0369a1] opacity-40" />
              </div>
              <p className="text-[#1a1a1a] font-normal text-2xl mb-2">{t(hasSearch ? 'library.noResults.title' : 'library.empty.title')}</p>
              <p className="text-[#94a3b8] font-bold text-md max-w-sm">{t(hasSearch ? 'library.noResults.message' : 'library.empty.message')}</p>
            </div>
          )}

          {/* Infinite Scroll Trigger */}
          <div ref={loaderRef as any} className="h-60 flex flex-col items-center justify-center gap-6">
            {!isInitialLoading && isLoadingMore && (
              <div className="flex flex-col items-center gap-4">
                <div className="w-10 h-10 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                <span className="text-xs font-black text-[#0369a1] uppercase animate-pulse">{t('library.loadingMore')}</span>
              </div>
            )}
            {!hasMore && books.length > 0 && (
              <div className="flex flex-col items-center gap-2 opacity-30">
                <div className="w-8 h-[1px] bg-[#94a3b8]"></div>
                <span className="text-[12px] font-black text-[#94a3b8] uppercase">{t('pagination.of')}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
