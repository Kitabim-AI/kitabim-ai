import React, { useState, useEffect, useRef } from 'react';
import { Search, Book as BookIcon, User, Tag, ArrowRight, Loader2 } from 'lucide-react';
import { Book } from '@shared/types';
import { BookCard } from './BookCard';
import { PersistenceService } from '../../services/persistenceService';

interface HomeViewProps {
  books: Book[];
  isInitialLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  onBookClick: (book: Book) => void;
  loaderRef: React.RefObject<HTMLDivElement>;
  loadMore: () => void;
}

interface Suggestion {
  text: string;
  type: 'title' | 'author' | 'category';
}

export const HomeView: React.FC<HomeViewProps> = ({
  books,
  isInitialLoading,
  isLoadingMore,
  hasMore,
  searchQuery,
  setSearchQuery,
  onBookClick,
  loaderRef,
  loadMore,
}) => {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const suggestionsRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (suggestionsRef.current && !suggestionsRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const fetchSuggestions = async () => {
      if (searchQuery.length < 2) {
        setSuggestions([]);
        return;
      }

      setIsSuggesting(true);
      try {
        const data = await PersistenceService.getSuggestions(searchQuery);
        setSuggestions(data);
      } catch (error) {
        console.error('Error fetching suggestions:', error);
      } finally {
        setIsSuggesting(false);
      }
    };

    const debounce = setTimeout(fetchSuggestions, 300);
    return () => clearTimeout(debounce);
  }, [searchQuery]);

  const handleSuggestionClick = (suggestion: Suggestion) => {
    setSearchQuery(suggestion.text);
    setShowSuggestions(false);
  };

  const hasSearch = searchQuery.length > 0;

  return (
    <div className={`flex flex-col items-center transition-all duration-700 ${hasSearch ? 'pt-10' : 'pt-32'}`}>
      {/* Brand Section */}
      <div className={`text-center mb-8 transition-all duration-700 ${hasSearch ? 'scale-75 opacity-70 mb-4' : 'scale-100 opacity-100'}`}>
        <h1 className="text-6xl md:text-7xl font-serif font-black text-slate-900 tracking-tight mb-2">
          Kitabim<span className="text-indigo-600">.AI</span>
        </h1>
        <p className="text-slate-500 font-medium text-lg">Your Portal to Uyghur Literature & Knowledge</p>
      </div>

      {/* Search Section */}
      <div className="w-full max-w-3xl px-4 relative mb-12">
        <div className="relative group">
          <div className="absolute inset-y-0 left-0 pl-6 flex items-center pointer-events-none">
            {isSuggesting ? (
              <Loader2 className="h-5 w-5 text-indigo-500 animate-spin" />
            ) : (
              <Search className="h-5 w-5 text-slate-400 group-focus-within:text-indigo-500 transition-colors" />
            )}
          </div>
          <input
            ref={searchInputRef}
            type="text"
            className="block w-full pl-14 pr-16 py-4 md:py-5 bg-white border-2 border-slate-100 rounded-3xl text-lg shadow-xl shadow-slate-200/50 focus:ring-4 focus:ring-indigo-100 focus:border-indigo-400 outline-none transition-all placeholder:text-slate-400"
            placeholder="Search books by title, author, or category..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setShowSuggestions(true);
            }}
            onFocus={() => setShowSuggestions(true)}
          />
          <div className="absolute inset-y-2 right-2 flex items-center">
            <button
              onClick={() => searchInputRef.current?.focus()}
              className="px-4 py-2 bg-indigo-600 text-white rounded-2xl font-bold flex items-center gap-2 hover:bg-indigo-700 active:scale-95 transition-all shadow-lg shadow-indigo-100"
            >
              Search
              <ArrowRight size={18} />
            </button>
          </div>
        </div>

        {/* Suggestions Dropdown */}
        {showSuggestions && suggestions.length > 0 && (
          <div
            ref={suggestionsRef}
            className="absolute z-50 left-4 right-4 mt-2 bg-white rounded-3xl shadow-2xl border border-slate-100 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200"
          >
            {suggestions.map((suggestion, index) => (
              <button
                key={`${suggestion.text}-${index}`}
                onClick={() => handleSuggestionClick(suggestion)}
                className="w-full text-left px-6 py-3 hover:bg-slate-50 flex items-center gap-4 transition-colors group"
              >
                <div className="p-2 bg-slate-100 rounded-lg text-slate-400 group-hover:bg-indigo-100 group-hover:text-indigo-600 transition-colors">
                  {suggestion.type === 'title' && <BookIcon size={18} />}
                  {suggestion.type === 'author' && <User size={18} />}
                  {suggestion.type === 'category' && <Tag size={18} />}
                </div>
                <div>
                  <p className="font-bold text-slate-800 group-hover:text-indigo-700 transition-colors">{suggestion.text}</p>
                  <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">{suggestion.type}</p>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Categories helper - only shown when no results/search */}
        {!hasSearch && (
          <div className="mt-8 flex flex-wrap justify-center gap-2">
            {['History', 'Literature', 'Religion', 'Biography', 'Science'].map(cat => (
              <button
                key={cat}
                onClick={() => setSearchQuery(cat)}
                className="px-4 py-1.5 bg-white border border-slate-100 text-slate-600 text-sm font-bold rounded-full hover:border-indigo-300 hover:text-indigo-600 shadow-sm transition-all active:scale-95"
              >
                {cat}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Results Section */}
      {hasSearch && (
        <div className="w-full max-w-7xl px-6 pb-20 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex items-center justify-between mb-8 border-b border-slate-100 pb-4">
            <h2 className="text-xl font-black text-slate-800 uppercase tracking-tighter">
              Search Results
            </h2>
            <div className="text-xs font-black text-slate-400 uppercase tracking-widest">
              {books.length} Books Found
            </div>
          </div>

          <div className="book-shelf-row">
            {books.map(book => (
              <BookCard
                key={book.id}
                book={book}
                onClick={onBookClick}
              />
            ))}
            {books.length === 0 && !isInitialLoading && (
              <div className="col-span-full py-20 text-center bg-white border-2 border-dashed border-slate-100 rounded-3xl">
                <BookIcon className="w-12 h-12 text-slate-200 mx-auto mb-4" />
                <p className="text-slate-400 font-bold">No books match "{searchQuery}"</p>
              </div>
            )}
          </div>

          {/* Infinite Scroll Trigger */}
          <div ref={loaderRef} className="h-32 flex items-center justify-center">
            {!isInitialLoading && isLoadingMore && (
              <div className="flex flex-col items-center gap-3">
                <div className="w-10 h-10 border-4 border-indigo-100 border-t-indigo-600 rounded-full animate-spin"></div>
                <span className="text-[10px] font-black text-indigo-600 uppercase tracking-widest">Loading more...</span>
              </div>
            )}
            {!hasMore && books.length > 0 && (
              <div className="flex flex-col items-center gap-2 opacity-30 mt-12">
                <BookIcon size={24} className="text-slate-400" />
                <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">End of the collection</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
