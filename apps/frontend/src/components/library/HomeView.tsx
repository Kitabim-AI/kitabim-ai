import { Book as BookIcon, Bot, Keyboard, RefreshCw, Search, X, Delete } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';
import { getCollectionPageSize } from '../../services/authService';
import { PersistenceService } from '../../services/persistenceService';
import { ProverbDisplay } from '../common/ProverbDisplay';
import { QuestionRotator } from '../common/QuestionRotator';
import { BookCard } from './BookCard';
import { HomeSearchTabResults } from './HomeSearchTabResults';
import { SearchTabBar } from './SearchTabBar';
import { getTabNoResultsKey, getTabPlaceholderKey } from './searchTabsConfig';

interface KeyDef {
  latin: string;
  uyghur: string;
  shift: string;
}

const KEYBOARD_ROWS: KeyDef[][] = [
  [
    { latin: 'q', uyghur: 'چ', shift: 'چ' },
    { latin: 'w', uyghur: 'ۋ', shift: 'ۋ' },
    { latin: 'e', uyghur: 'ې', shift: 'ې' },
    { latin: 'r', uyghur: 'ر', shift: 'ر' },
    { latin: 't', uyghur: 'ت', shift: 'ـ' },
    { latin: 'y', uyghur: 'ي', shift: 'ي' },
    { latin: 'u', uyghur: 'ۇ', shift: 'ۇ' },
    { latin: 'i', uyghur: 'ڭ', shift: 'ڭ' },
    { latin: 'o', uyghur: 'و', shift: 'و' },
    { latin: 'p', uyghur: 'پ', shift: 'پ' }
  ],
  [
    { latin: 'a', uyghur: 'ھ', shift: 'ھ' },
    { latin: 's', uyghur: 'س', shift: 'س' },
    { latin: 'd', uyghur: 'د', shift: 'ژ' },
    { latin: 'f', uyghur: 'ا', shift: 'ف' },
    { latin: 'g', uyghur: 'ە', shift: 'گ' },
    { latin: 'h', uyghur: 'ى', shift: 'خ' },
    { latin: 'j', uyghur: 'ق', shift: 'ج' },
    { latin: 'k', uyghur: 'ك', shift: 'ۆ' },
    { latin: 'l', uyghur: 'ل', shift: 'ل' },
    { latin: ';', uyghur: '؛', shift: '؛' }
  ],
  [
    { latin: 'z', uyghur: 'ز', shift: 'ز' },
    { latin: 'x', uyghur: 'ش', shift: 'ش' },
    { latin: 'c', uyghur: 'غ', shift: 'غ' },
    { latin: 'v', uyghur: 'ۈ', shift: 'ۈ' },
    { latin: 'b', uyghur: 'ب', shift: 'ب' },
    { latin: 'n', uyghur: 'ن', shift: 'ن' },
    { latin: 'm', uyghur: 'م', shift: 'م' },
    { latin: ',', uyghur: '،', shift: ',' },
    { latin: '/', uyghur: 'ئ', shift: '؟' }
  ]
];

export const HomeView: React.FC = () => {
  const {
    sortedBooks: books,
    totalBooks,
    isLoading: isInitialLoading,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    homeSearchQuery: searchQuery,
    setHomeSearchQuery: setSearchQuery,
    homeActiveTab: activeTab,
    setHomeActiveTab: setActiveTab,
    homeSearchText,
    setHomeSearchText,
    selectedCategory,
    setSelectedCategory,
    bookActions,
    loaderRef,
    setView,
    chat,
    loadMoreShelf,
    fontSize,
  } = useAppContext();

  const { t } = useI18n();
  const isBookTab = activeTab === 'ask' || activeTab === 'books';
  const isEnUg = activeTab === 'en-ug';
  // The typed query is persisted in `homeSearchText` (AppContext) for every tab, so it
  // survives HomeView unmounting (opening/closing the reader) and carries over when the
  // user switches tabs. Book tabs additionally commit into `searchQuery` to trigger the fetch.
  const [localSearch, setLocalSearch] = useState(homeSearchText);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const localSearchRef = useRef(localSearch);
  const keyboardRef = useRef<HTMLDivElement>(null);

  const [showKeyboardMap, setShowKeyboardMap] = useState(false);
  const [isShiftPressed, setIsShiftPressed] = useState(false);

  useEffect(() => {
    localSearchRef.current = localSearch;
  }, [localSearch]);

  // Listen to physical Shift and Escape keys
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Shift') {
        setIsShiftPressed(true);
      }
      if (e.key === 'Escape') {
        setShowKeyboardMap(false);
      }
    };
    
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === 'Shift') {
        setIsShiftPressed(false);
      }
    };
    
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, []);

  // Close keyboard on click outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        showKeyboardMap &&
        keyboardRef.current &&
        !keyboardRef.current.contains(e.target as Node) &&
        !(e.target as HTMLElement).closest('.keyboard-toggle-btn')
      ) {
        setShowKeyboardMap(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showKeyboardMap]);

  const handleKeyClick = (char: string) => {
    const input = searchInputRef.current;
    if (!input) return;
    
    if (document.activeElement !== input) {
      input.focus();
    }
    
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const value = input.value;
    const newValue = value.substring(0, start) + char + value.substring(end);
    
    setLocalSearch(newValue);
    
    // Position cursor after inserted character and scroll to caret
    setTimeout(() => {
      input.focus();
      input.setSelectionRange(start + char.length, start + char.length);
      if (input.dir === 'rtl') {
        input.scrollLeft = -input.scrollWidth;
        if (input.scrollLeft === 0) {
          input.scrollLeft = input.scrollWidth;
        }
      } else {
        input.scrollLeft = input.scrollWidth;
      }
    }, 0);
  };

  const handleBackspaceClick = () => {
    const input = searchInputRef.current;
    if (!input) return;
    
    if (document.activeElement !== input) {
      input.focus();
    }
    
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const value = input.value;
    
    let newValue = value;
    let newCursorPos = start;
    
    if (start !== end) {
      // Delete selection
      newValue = value.substring(0, start) + value.substring(end);
      newCursorPos = start;
    } else if (start > 0) {
      // Delete single char before cursor
      newValue = value.substring(0, start - 1) + value.substring(start);
      newCursorPos = start - 1;
    }
    
    setLocalSearch(newValue);
    
    setTimeout(() => {
      input.focus();
      input.setSelectionRange(newCursorPos, newCursorPos);
      if (input.dir === 'rtl') {
        input.scrollLeft = -input.scrollWidth;
        if (input.scrollLeft === 0) {
          input.scrollLeft = input.scrollWidth;
        }
      } else {
        input.scrollLeft = input.scrollWidth;
      }
    }, 0);
  };

  // Focus the search input on mount and when activeTab changes
  useEffect(() => {
    searchInputRef.current?.focus();
    if (isEnUg) {
      setShowKeyboardMap(false);
    }
  }, [activeTab, isEnUg]);

  // Keep the input scrolled to the caret (end of text) when the query is long
  useEffect(() => {
    const input = searchInputRef.current;
    if (!input || document.activeElement !== input) return;
    
    const timer = setTimeout(() => {
      if (input.dir === 'rtl') {
        input.scrollLeft = -input.scrollWidth;
        if (input.scrollLeft === 0) {
          input.scrollLeft = input.scrollWidth;
        }
      } else {
        input.scrollLeft = input.scrollWidth;
      }
    }, 0);
    return () => clearTimeout(timer);
  }, [localSearch]);

  // Search is active if we have a category OR at least 3 characters (book tabs), or any
  // typed text for the other tabs (they debounce their own fetches independently).
  const hasBookSearch = (searchQuery.length >= 3) || selectedCategory.length > 0;
  const hasSearch = isBookTab ? hasBookSearch : localSearch.trim().length > 0;

  // No books found for a text query (not a category browse) — prompt to chat.
  // Only the "Ask" tab falls back to chat; "Books" is an explicit title/author/category search.
  const chatHint = activeTab === 'ask' && searchQuery.length >= 3 && !selectedCategory && !isInitialLoading && books.length === 0;
  const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  const isMac = !isTouchDevice && navigator.platform.toUpperCase().startsWith('MAC');

  // Debounce: after 300ms of no typing, persist the query (so it carries over across tabs
  // and survives HomeView unmounting/remounting) and, for book tabs, commit it to `searchQuery`
  // to trigger the API call. Once chatHint is active, suppress the `searchQuery` commit as long
  // as the query stays long enough to be a question — only let through a clear (< 3 chars) so
  // the user can exit chat mode by deleting the input.
  useEffect(() => {
    const timer = setTimeout(() => {
      const trimmed = localSearch.trim();
      if (trimmed !== homeSearchText) {
        setHomeSearchText(trimmed);
      }
      if (isBookTab) {
        if (trimmed === searchQuery) return;
        if (chatHint && trimmed.length >= 3 && trimmed.length >= searchQuery.length) return;
        setSearchQuery(trimmed);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch, searchQuery, homeSearchText, setSearchQuery, setHomeSearchText, chatHint, isBookTab]);

  // Sync local search when the persisted query is cleared or changed externally
  // (e.g. the clear button, a chat handoff, or navigating away and back to home).
  useEffect(() => {
    if (localSearchRef.current.trim() !== homeSearchText) {
      setLocalSearch(homeSearchText);
    }
  }, [homeSearchText]);



  useEffect(() => {
    if (!isBookTab || !hasSearch) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isInitialLoading && hasMore && !isLoadingMore && books.length > 0) {
          loadMoreShelf();
        }
      },
      { threshold: 0.1, rootMargin: '1200px' }
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [isBookTab, hasSearch, hasMore, isLoadingMore, loadMoreShelf, loaderRef, isInitialLoading]);

  const handleSearchSubmit = () => {
    const trimmed = localSearch.trim();
    if (trimmed.length >= 3 && !selectedCategory && !isInitialLoading && books.length === 0) {
      chat.setChatInput(trimmed);
      setLocalSearch('');
      setSearchQuery('');
      setHomeSearchText('');
      setView('global-chat');
    }
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
            className={`font-black text-[#1a1a1a] dark:text-slate-100 leading-none transition-all duration-1000 mt-5 ${hasSearch
              ? 'text-2xl sm:text-3xl md:text-4xl'
              : 'text-4xl sm:text-5xl md:text-6xl lg:text-7xl'
              }`}
          >
            Kitabim<span className="text-[#0369a1] dark:text-[#38bdf8]">.AI</span>
          </h1>
        </div>

        <ProverbDisplay
          className={`items-center text-center transition-all duration-700 ${hasSearch ? 'opacity-60' : 'opacity-100'}`}
          size={hasSearch ? 'sm' : 'lg'}
          keywords={t('proverbs.home')}
          defaultText={t('app.welcome')}
        />
      </div>

      {/* Search Section */}
      <div className="w-full max-w-[840px] px-4 relative mb-8 sm:mb-10 md:mb-12">
        <div className="mb-4">
          <SearchTabBar activeTab={activeTab} onChange={setActiveTab} />
        </div>
        <div className="relative group">
          <button
            onClick={handleSearchSubmit}
            className={`absolute inset-y-0 ${isEnUg ? 'left-0 pl-4 sm:pl-6' : 'right-0 pr-4 sm:pr-6'} flex items-center text-[#94a3b8] group-focus-within:text-[#0369a1] dark:group-focus-within:text-[#38bdf8] transition-colors z-10`}
          >
            {isInitialLoading && localSearch ? (
              <RefreshCw size={20} className="sm:w-[22px] sm:h-[22px] animate-spin" strokeWidth={3} />
            ) : chatHint ? (
              <Bot size={20} className="sm:w-[22px] sm:h-[22px] text-[#0369a1] dark:text-[#38bdf8]" strokeWidth={2.5} />
            ) : (
              <Search size={20} className="sm:w-[22px] sm:h-[22px]" strokeWidth={3} />
            )}
          </button>
          <input
            ref={searchInputRef}
            type="text"
            className={`w-full py-4 sm:py-5 bg-white/60 dark:bg-slate-900/60 backdrop-blur-2xl border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-[32px] text-base sm:text-lg font-normal text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-300 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] focus:ring-[12px] focus:ring-[#0369a1]/5 dark:focus:ring-[#38bdf8]/5 transition-all shadow-xl ${
              isEnUg ? '' : 'uyghur-text'
            } ${
              isEnUg
                ? `pl-12 md:pl-16 ${localSearch ? 'pr-14' : 'pr-6'}`
                : `pr-12 md:pr-16 md:pl-28 ${localSearch ? 'pl-14' : 'pl-6'}`
            }`}
            placeholder={t(getTabPlaceholderKey(activeTab))}
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearchSubmit(); }}
            dir={isEnUg ? 'ltr' : 'rtl'}
            lang={isEnUg ? 'en' : 'ug'}
            data-latin={isEnUg ? 'true' : undefined}
          />
          <div className={`absolute inset-y-0 ${isEnUg ? 'right-0 pr-4 sm:pr-6' : 'left-0 pl-4 sm:pl-6'} flex items-center gap-0.5 z-10`} dir="ltr">
            {localSearch && (
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => { setLocalSearch(''); setSearchQuery(''); setHomeSearchText(''); }}
                className="w-9 h-9 rounded-full flex items-center justify-center text-[#94a3b8] hover:text-[#0369a1] hover:bg-slate-100/50 transition-colors"
                title="Clear"
              >
                <X size={20} className="sm:w-[22px] sm:h-[22px]" strokeWidth={3} />
              </button>
            )}

            {/* Keyboard layout toggle icon, hidden on mobile and en-ug tab */}
            {!isEnUg && (
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setShowKeyboardMap(!showKeyboardMap)}
                className={`hidden md:flex items-center justify-center text-[#94a3b8] hover:text-[#0369a1] transition-colors w-9 h-9 rounded-full hover:bg-slate-100/50 keyboard-toggle-btn ${
                  showKeyboardMap ? 'text-[#0369a1] bg-[#0369a1]/10 hover:bg-[#0369a1]/15' : ''
                }`}
                title={t('home.keyboardMapTooltip')}
              >
                <Keyboard size={20} className="sm:w-[22px] sm:h-[22px]" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>

        {/* Keyboard Map Panel */}
        {!isEnUg && showKeyboardMap && (
          <div
            ref={keyboardRef}
            className="absolute left-4 right-4 mt-3 bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl border border-slate-200/60 dark:border-slate-800 rounded-3xl p-5 shadow-2xl z-20 hidden md:block animate-in fade-in slide-in-from-top-4 duration-200"
            dir="ltr"
          >
            {/* Keyboard Header */}
            <div className="flex justify-between items-center mb-4 pb-3 border-b border-slate-100 dark:border-slate-800" dir="rtl">
              <div className="flex flex-col gap-0.5">
                <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200 uyghur-text">
                  {t('home.keyboardMapTitle')}
                </h4>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 uyghur-text">
                  {t('home.keyboardMapSubtitle')}
                </p>
              </div>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setShowKeyboardMap(false)}
                className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
                <X size={16} />
              </button>
            </div>
            
            {/* Keys Layout */}
            <div className="flex flex-col gap-2 items-center w-full">
              {/* Row 1 */}
              <div className="flex gap-1.5 w-full justify-center">
                {KEYBOARD_ROWS[0].map(key => (
                  <button
                    key={key.latin}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handleKeyClick(isShiftPressed ? key.shift : key.uyghur)}
                    className="h-12 flex-1 max-w-[54px] min-w-[36px] bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/80 border border-slate-200 dark:border-slate-700 rounded-lg flex flex-col justify-between p-1.5 shadow-sm text-slate-800 dark:text-slate-200 transition-all active:scale-95 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600 select-none"
                  >
                    <span className="text-[9px] text-slate-400 dark:text-slate-500 font-medium uppercase self-start">{key.latin}</span>
                    <span className="text-base sm:text-lg font-bold self-center leading-none mt-0.5">{isShiftPressed ? key.shift : key.uyghur}</span>
                  </button>
                ))}
              </div>
              
              {/* Row 2 */}
              <div className="flex gap-1.5 w-full justify-center pl-4">
                {KEYBOARD_ROWS[1].map(key => (
                  <button
                    key={key.latin}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handleKeyClick(isShiftPressed ? key.shift : key.uyghur)}
                    className="h-12 flex-1 max-w-[54px] min-w-[36px] bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/80 border border-slate-200 dark:border-slate-700 rounded-lg flex flex-col justify-between p-1.5 shadow-sm text-slate-800 dark:text-slate-200 transition-all active:scale-95 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600 select-none"
                  >
                    <span className="text-[9px] text-slate-400 dark:text-slate-500 font-medium uppercase self-start">{key.latin}</span>
                    <span className="text-base sm:text-lg font-bold self-center leading-none mt-0.5">{isShiftPressed ? key.shift : key.uyghur}</span>
                  </button>
                ))}
              </div>
              
              {/* Row 3 */}
              <div className="flex gap-1.5 w-full justify-center pl-8">
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setIsShiftPressed(!isShiftPressed)}
                  className={`h-12 px-3 border rounded-lg flex items-center justify-center font-semibold text-xs transition-all active:scale-95 cursor-pointer select-none ${
                    isShiftPressed
                      ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white border-[#0369a1] dark:border-[#38bdf8]'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700 hover:border-slate-300 dark:hover:border-slate-600'
                  }`}
                >
                  Shift
                </button>
                
                {KEYBOARD_ROWS[2].map(key => (
                  <button
                    key={key.latin}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handleKeyClick(isShiftPressed ? key.shift : key.uyghur)}
                    className="h-12 flex-1 max-w-[54px] min-w-[36px] bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/80 border border-slate-200 dark:border-slate-700 rounded-lg flex flex-col justify-between p-1.5 shadow-sm text-slate-800 dark:text-slate-200 transition-all active:scale-95 cursor-pointer hover:border-slate-300 dark:hover:border-slate-600 select-none"
                  >
                    <span className="text-[9px] text-slate-400 dark:text-slate-500 font-medium uppercase self-start">{key.latin}</span>
                    <span className="text-base sm:text-lg font-bold self-center leading-none mt-0.5">{isShiftPressed ? key.shift : key.uyghur}</span>
                  </button>
                ))}
                
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={handleBackspaceClick}
                  className="h-12 px-3 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700 hover:border-slate-300 dark:hover:border-slate-600 rounded-lg flex items-center justify-center text-slate-700 dark:text-slate-300 transition-all active:scale-95 cursor-pointer select-none"
                  title="Backspace"
                >
                  <Delete size={16} />
                </button>
              </div>
              
              {/* Row 4 */}
              <div className="flex gap-1.5 w-full justify-center mt-0.5">
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => handleKeyClick(' ')}
                  className="h-12 w-48 sm:w-64 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/80 border border-slate-200 dark:border-slate-700 rounded-lg flex items-center justify-center shadow-sm text-slate-800 dark:text-slate-200 text-xs font-semibold transition-all active:scale-95 cursor-pointer select-none hover:border-slate-300 dark:hover:border-slate-600"
                >
                  {t('home.spaceKey')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Chat hint when no books match the query */}
        {chatHint && (
          <p className="mt-4 text-center text-sm text-[#94a3b8] uyghur-text" dir="rtl">
            {t(isTouchDevice ? 'home.tapToChat' : isMac ? 'home.pressReturnToChat' : 'home.pressEnterToChat')}
          </p>
        )}



        {/* Recent questions rotator */}
        {!hasSearch && (
          <QuestionRotator
            className="mt-8 sm:mt-10"
            onQuestionClick={(q) => {
              chat.setChatInput(q);
              setView('global-chat');
            }}
          />
        )}
      </div>

      {/* Results Section */}
      {isBookTab ? (
        hasSearch && !chatHint && (
          <div className="w-full max-w-none px-4 md:px-8 pb-24 sm:pb-32">
            <div className="flex flex-col mb-10 sm:mb-12 md:mb-16 gap-2">
              <div className="flex items-center justify-between">
                <h2 className="text-xl sm:text-2xl md:text-3xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('home.searchResults')}</h2>
                <div className="px-3 sm:px-4 py-1 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl text-xs sm:text-sm font-normal shadow-inner border border-[#0369a1]/5 dark:border-[#38bdf8]/5">
                  {isInitialLoading ? <RefreshCw size={12} className="inline-block animate-spin mx-1" /> : totalBooks} <span className="opacity-60">{t('home.totalBooks')}</span>
                </div>
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

              {isInitialLoading && books.length === 0 && (
                <div className="col-span-full py-20 w-full flex flex-col items-center justify-center">
                  <div className="relative mb-6">
                    <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                    <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                      <RefreshCw className="w-8 h-8 animate-pulse" />
                    </div>
                  </div>
                  <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('common.loading')}</h3>
                </div>
              )}
            </div>

            {books.length === 0 && !isInitialLoading && (
              <div className="w-full py-20 text-center glass-panel flex flex-col items-center justify-center rounded-[32px]">
                <div className="p-6 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 rounded-[32px] mb-6">
                  <BookIcon className="w-16 h-16 text-[#0369a1] dark:text-[#38bdf8] opacity-60 dark:opacity-80" />
                </div>
                <p className="text-[#1a1a1a] dark:text-slate-100 font-bold text-xl sm:text-2xl mb-2 uyghur-text">{t(hasSearch ? getTabNoResultsKey(activeTab) : 'library.empty.title')}</p>
                <p className="text-[#94a3b8] dark:text-slate-400 font-medium text-sm sm:text-base max-w-sm uyghur-text">{t(hasSearch ? 'library.noResults.message' : 'library.empty.message')}</p>
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
                  <div className="w-8 h-[1px] bg-[#94a3b8] dark:bg-slate-700"></div>
                  <span className="text-xs font-black text-[#94a3b8] dark:text-slate-500 uppercase">{t('common.endOfList')}</span>
                </div>
              )}
            </div>
          </div>
        )
      ) : (
        hasSearch && (
          <div className="w-full max-w-none px-4 md:px-8 pb-24 sm:pb-32">
            <div className="flex flex-col mb-10 sm:mb-12 md:mb-16 gap-2">
              <h2 className="text-xl sm:text-2xl md:text-3xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('home.searchResults')}</h2>
            </div>
            <HomeSearchTabResults
              activeTab={activeTab}
              query={localSearch}
              pageSize={getCollectionPageSize()}
              onOpenBook={bookActions.openReader}
            />
          </div>
        )
      )}
    </div>
  );
};
