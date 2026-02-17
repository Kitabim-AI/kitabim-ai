import React, { useState, useEffect, useRef } from 'react';
import { Search, Book as BookIcon, User, Tag, ArrowRight, Loader2, X } from 'lucide-react';
import { Book } from '@shared/types';
import { BookCard } from './BookCard';
import { PersistenceService } from '../../services/persistenceService';
import { useI18n } from '../../i18n/I18nContext';

interface HomeViewProps {
  books: Book[];
  isInitialLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  selectedCategory: string;
  setSelectedCategory: (category: string) => void;
  onBookClick: (book: Book) => void;
  loaderRef: React.RefObject<HTMLDivElement>;
  loadMore: () => void;
}

export const HomeView: React.FC<HomeViewProps> = ({
  books,
  isInitialLoading,
  isLoadingMore,
  hasMore,
  searchQuery,
  setSearchQuery,
  selectedCategory,
  setSelectedCategory,
  onBookClick,
  loaderRef,
}) => {
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

  const handleCategoryClick = (category: string) => {
    setSelectedCategory(category);
    setSearchQuery('');
  };

  const hasSearch = searchQuery.length > 0 || selectedCategory.length > 0;

  return (
    <div className={`flex flex-col items-center transition-all duration-1000 ${hasSearch ? 'pt-6' : 'pt-20'}`} dir="rtl">
      {/* Brand & Hero Section */}
      <div className={`text-center mb-10 transition-all duration-1000 ${hasSearch ? 'scale-75 opacity-70 mb-4' : 'scale-100 opacity-100'}`}>
        <div className="flex flex-col items-center gap-2 mb-6">
          <div className="px-6 py-2 bg-[#0369a1] text-white rounded-full text-[14px] font-black uppercase tracking-[0.3em] mb-4 border border-[#0369a1]/20 shadow-[0_8px_20px_rgba(3,105,161,0.2)]">
            {t('app.tagline')}
          </div>
          <h1
            className="font-black text-[#1a1a1a] tracking-tighter leading-none flex items-center gap-4"
            style={{ fontSize: hasSearch ? '3.5rem' : '5rem' }}
          >
            <span className="text-[#0369a1]">AI.</span>Kitabim
          </h1>
        </div>

        {proverb ? (
          <div className="flex flex-col items-center gap-1">
            <p className="uyghur-text font-black text-[#1a1a1a] leading-relaxed italic max-w-3xl px-6 transition-all duration-700"
              style={{ fontSize: hasSearch ? '1.1rem' : '1.55rem', opacity: hasSearch ? 0.6 : 1 }}>
              {proverb.text}
            </p>
          </div>
        ) : (
          <p className="text-[#94a3b8] font-bold text-xl mb-8">{t('app.welcome')}</p>
        )}
      </div>

      {/* Search Section */}
      <div className="w-full max-w-3xl px-4 relative mb-12">
        <div className="relative group">
          <div className="absolute inset-y-0 right-0 pr-6 flex items-center pointer-events-none text-[#94a3b8] group-focus-within:text-[#0369a1] transition-colors z-10">
            <Search size={22} strokeWidth={3} />
          </div>
          <input
            ref={searchInputRef}
            type="text"
            className="w-full px-16 py-5 bg-white/60 backdrop-blur-2xl border-2 border-[#0369a1]/10 rounded-[32px] text-lg font-black text-[#1a1a1a] placeholder:text-slate-300 outline-none focus:border-[#0369a1] focus:ring-[12px] focus:ring-[#0369a1]/5 transition-all shadow-[0_24px_64px_rgba(0,0,0,0.06)] uyghur-text"
            placeholder={t('home.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            dir="rtl"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 left-6 flex items-center text-[#94a3b8] hover:text-[#0369a1] transition-colors z-10"
            >
              <X size={24} strokeWidth={3} />
            </button>
          )}
        </div>

        {/* Categories helper */}
        {!hasSearch && topCategories.length > 0 && (
          <div className="mt-12 flex flex-wrap justify-center gap-3 px-4">
            <span className="w-full text-center text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.3em] mb-4">{t('home.topCategories')}</span>
            {topCategories.map(cat => (
              <button
                key={cat}
                onClick={() => handleCategoryClick(cat)}
                className="px-6 py-2.5 bg-white/40 backdrop-blur-md border border-[#75C5F0]/10 rounded-2xl text-sm font-black text-[#1a1a1a] hover:bg-[#75C5F0] hover:text-white transition-all active:scale-95 shadow-sm hover:shadow-lg hover:shadow-[#75C5F0]/20"
              >
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results Section */}
      {hasSearch && (
        <div className="w-full max-w-7xl px-8 pb-32">
          <div className="flex items-center justify-between mb-16 px-4">
            <div className="flex items-center gap-4">
              <button
                onClick={() => { setSearchQuery(''); setSelectedCategory(''); }}
                className="p-3 bg-white/40 hover:bg-[#0369a1] text-[#0369a1] hover:text-white rounded-2xl transition-all shadow-sm active:scale-90"
              >
                <ArrowRight size={24} strokeWidth={3} className="rotate-180" />
              </button>
              <div>
                <h2 className="text-3xl font-black text-[#1a1a1a]">{t('home.searchResults')}</h2>
                <p className="text-[14px] font-black text-[#94a3b8] uppercase tracking-widest mt-1">«{searchQuery || selectedCategory}» {t('home.resultsFor')}</p>
              </div>
            </div>
            <div className="px-6 py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl text-sm font-black shadow-inner border border-[#0369a1]/5">
              <span className="opacity-60">{t('common.total')}</span> {books.length} <span className="opacity-60">{t('home.totalBooks')}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-x-8 gap-y-16 justify-items-center">
            {books.map(book => (
              <BookCard
                key={book.id}
                book={book}
                onClick={onBookClick}
              />
            ))}
          </div>

          {books.length === 0 && !isInitialLoading && (
            <div className="w-full py-40 text-center glass-panel flex flex-col items-center justify-center" style={{ borderRadius: '48px' }}>
              <div className="p-8 bg-[#0369a1]/10 rounded-[40px] mb-8">
                <BookIcon className="w-20 h-20 text-[#0369a1] opacity-40" />
              </div>
              <p className="text-[#1a1a1a] font-black text-3xl mb-4">{t('library.empty.title')}</p>
              <p className="text-[#94a3b8] font-bold text-lg max-w-md">{t('library.empty.message')}</p>
            </div>
          )}

          {/* Infinite Scroll Trigger */}
          <div ref={loaderRef} className="h-60 flex flex-col items-center justify-center gap-6">
            {!isInitialLoading && isLoadingMore && (
              <>
                <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                <span className="text-[14px] font-black text-[#0369a1] uppercase tracking-[0.3em] animate-pulse">{t('library.loadingMore')}</span>
              </>
            )}
            {!hasMore && books.length > 0 && (
              <div className="flex flex-col items-center gap-4 opacity-30">
                <div className="w-12 h-[1px] bg-[#94a3b8]"></div>
                <span className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.3em]">{t('pagination.of')}</span>
                <div className="w-12 h-[1px] bg-[#94a3b8]"></div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
