/**
 * Dictionary Management Panel - Editor/Admin tool to manage spell check dictionary
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Search, Plus, Trash2, Check, X, Loader2, BookA, Hash, 
  AlertCircle, RefreshCw
} from 'lucide-react';
import { authFetch } from '../../../services/authService';
import { useI18n } from '../../../i18n/I18nContext';

import { useAppContext } from '../../../context/AppContext';

interface DictionaryWord {
  id: number;
  word: string;
}
export const DictionaryManagementPanel: React.FC = () => {
  const { t } = useI18n();
  const { setModal } = useAppContext();
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<DictionaryWord[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [exactMatch, setExactMatch] = useState<DictionaryWord | null>(null); 
  const [isAdding, setIsAdding] = useState(false);
  const [isDeleting, setIsDeleting] = useState<string | null>(null);
  const [lastAction, setLastAction] = useState<{ type: 'add' | 'delete', word: string } | null>(null);
  const [stats, setStats] = useState<{ total_words: number } | null>(null);

  // Infinite Scroll State
  const [allWords, setAllWords] = useState<DictionaryWord[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const loaderRef = useRef<HTMLDivElement>(null);
  const PAGE_SIZE = 20;

  const fetchStats = async () => {
    try {
      const resp = await authFetch('/api/spell-check/dictionary/stats');
      if (resp.ok) {
        const data = await resp.json();
        setStats(data);
      }
    } catch (e) {
      console.error('Failed to fetch dictionary stats', e);
    }
  };

  const fetchAllWords = useCallback(async (pageNum: number, clear: boolean = false) => {
    if (isLoadingMore) return;
    setIsLoadingMore(true);
    try {
      const resp = await authFetch(`/api/spell-check/dictionary?skip=${pageNum * PAGE_SIZE}&limit=${PAGE_SIZE}`);
      if (resp.ok) {
        const data = await resp.json();
        if (clear) {
          setAllWords(data);
        } else {
          setAllWords(prev => [...prev, ...data]);
        }
        setHasMore(data.length === PAGE_SIZE);
      }
    } catch (e) {
      console.error('Failed to fetch words', e);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore]);

  const searchWords = async (q: string) => {
    if (!q.trim()) {
      setSuggestions([]);
      setExactMatch(null); 
      return;
    }

    setIsSearching(true);
    try {
      const resp = await authFetch(`/api/spell-check/dictionary/search?q=${encodeURIComponent(q)}&limit=10`);
      if (resp.ok) {
        const data = await resp.json();
        setSuggestions(data);
        
        const exact = data.find((d: DictionaryWord) => d.word === q.trim());
        setExactMatch(exact || null);
      }
    } catch (e) {
      console.error('Failed to search dictionary', e);
    } finally {
      setIsSearching(false);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchAllWords(0, true);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      searchWords(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Infinite Scroll Observer
  useEffect(() => {
    if (!hasMore || isLoadingMore || searchQuery.trim()) return;

    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        const next = page + 1;
        setPage(next);
        fetchAllWords(next);
      }
    }, { threshold: 0.1 });

    if (loaderRef.current) {
      observer.observe(loaderRef.current);
    }
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, page, fetchAllWords, searchQuery]);

  const handleAddWord = async (word: string) => {
    const val = word.trim();
    if (!val) return;

    setIsAdding(true);
    try {
      const resp = await authFetch('/api/spell-check/dictionary', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: val }),
      });

      if (resp.ok) {
        setLastAction({ type: 'add', word: val });
        setSearchQuery('');
        // Refresh full list and stats
        setPage(0);
        fetchAllWords(0, true);
        fetchStats();
      }
    } catch (e) {
      console.error('Failed to add word', e);
    } finally {
      setIsAdding(false);
    }
  };

  const handleDeleteWord = (word: string) => {
    setModal({
      isOpen: true,
      title: t('admin.dictionary.confirmDeleteTitle'),
      message: t('admin.dictionary.confirmDelete', { word }),
      type: 'confirm',
      confirmText: t('common.delete'),
      destructive: true,
      onConfirm: async () => {
        setIsDeleting(word);
        setModal((prev: any) => ({ ...prev, isOpen: false })); 
        try {
          const resp = await authFetch(`/api/spell-check/dictionary/${encodeURIComponent(word)}`, {
            method: 'DELETE',
          });

          if (resp.ok) {
            setLastAction({ type: 'delete', word });
            if (searchQuery) {
              searchWords(searchQuery);
            } else {
              setAllWords(prev => prev.filter(w => w.word !== word));
            }
            fetchStats();
          }
        } catch (e) {
          console.error('Failed to delete word', e);
        } finally {
          setIsDeleting(null);
        }
      }
    });
  };

  const activeWords = searchQuery.trim() ? suggestions : allWords;

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in pb-20" dir="rtl" lang="ug">
      {/* Header */}

      {/* Main Search & Tool Section */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4 py-4 md:py-8">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] transition-colors z-10 font-bold">
            {isSearching ? (
              <RefreshCw className="animate-spin" size={16} />
            ) : (
              <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
            )}
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pr-11 md:pr-14 pl-20 md:pl-28 py-2.5 md:py-3 bg-white border-2 border-[#0369a1]/10 rounded-2xl uyghur-text outline-none focus:border-[#0369a1] transition-all shadow-sm placeholder:text-slate-300 text-base"
            placeholder={t('admin.dictionary.searchPlaceholder')}
            dir="rtl"
          />
          <div className="absolute inset-y-0 left-3 md:left-4 flex items-center gap-1 md:gap-2 z-10">
            {searchQuery.trim() && !exactMatch && !isSearching && (
              <button
                onClick={() => handleAddWord(searchQuery)}
                disabled={isAdding}
                className="h-8 md:h-9 px-3 md:px-5 bg-[#0369a1] text-white rounded-lg md:rounded-xl font-normal text-[11px] md:text-sm flex items-center gap-1.5 md:gap-2 hover:bg-[#0284c7] transition-all active:scale-95 shadow-md shadow-[#0369a1]/20 disabled:opacity-50"
              >
                {isAdding ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} strokeWidth={3} className="md:w-3.5 md:h-3.5" />}
                <span className="hidden sm:inline">{t('admin.dictionary.addWord')}</span>
              </button>
            )}
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery('')}
                className="p-1.5 md:p-2 text-slate-300 hover:text-red-500 transition-colors"
                title={t('common.clear')}
              >
                <X strokeWidth={2.5} className="w-4 h-4 md:w-5 md:h-5" />
              </button>
            )}
          </div>
        </div>

        {stats && (
          <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] bg-[#0369a1]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 shadow-sm whitespace-nowrap self-end md:self-auto md:mr-auto">
            <Hash size={12} className="md:w-[14px] md:h-[14px]" />
            {t('admin.dictionary.totalWords', { count: stats.total_words.toLocaleString() })}
          </div>
        )}
      </div>

        {/* Search Results / Full List */}
        <div className="space-y-3">
          {isSearching && activeWords.length === 0 && (
             <div className="flex justify-center py-20">
                <Loader2 size={40} className="animate-spin text-[#0369a1]/20" />
             </div>
          )}

          {searchQuery.trim() && !isSearching && suggestions.length === 0 && (
            <div className="glass-panel rounded-[24px] md:rounded-[32px] py-8 md:py-12 px-4 md:px-8 flex flex-col items-center justify-center gap-3 md:gap-4 text-center animate-fade-in shadow-lg border border-[#0369a1]/10">
               <div className="p-3 md:p-4 bg-amber-50 text-amber-500 rounded-full shadow-inner ring-4 ring-amber-50/50">
                  <AlertCircle className="w-6 h-6 md:w-8 md:h-8" />
               </div>
               <div className="space-y-1">
                  <h3 className="text-lg md:text-xl font-normal text-[#1a1a1a]">{t('admin.dictionary.wordNotFound')}</h3>
                  <p className="text-slate-400 font-bold text-[9px] md:text-xs uppercase tracking-widest opacity-60 line-clamp-1">{searchQuery}</p>
               </div>
            </div>
          )}

          {activeWords.length > 0 && (
            <div className="space-y-3">
              <div className="glass-panel rounded-[32px] p-2 overflow-hidden shadow-xl animate-fade-in border border-[#0369a1]/5">
                <div className="grid grid-cols-1 gap-1">
                    {activeWords.map((entry) => (
                      <div 
                        key={entry.id} 
                        className={`
                          flex items-center justify-between px-4 md:px-6 py-3 md:py-4 rounded-2xl transition-all group
                          ${entry.word === searchQuery.trim() ? 'bg-[#0369a1]/5 ring-1 ring-[#0369a1]/10' : 'hover:bg-slate-50/50'}
                        `}
                      >
                        <div className="flex items-center gap-3 md:gap-4">
                          <div className={`p-1.5 md:p-2 rounded-lg ${entry.word === searchQuery.trim() ? 'bg-[#0369a1] text-white' : 'bg-slate-100 text-slate-400'}`}>
                             <Check size={14} strokeWidth={3} className="w-3 h-3 md:w-3.5 md:h-3.5" />
                          </div>
                          <span className={`uyghur-text text-[15px] md:text-xl ${entry.word === searchQuery.trim() ? 'font-bold text-[#0369a1]' : 'text-slate-700 font-normal'}`}>
                             {entry.word}
                          </span>
                          {entry.word === searchQuery.trim() && (
                            <span className="text-[8px] md:text-[10px] font-bold text-[#0369a1]/60 uppercase tracking-widest bg-[#0369a1]/10 px-2 md:px-2.5 py-0.5 md:py-1 rounded-full border border-[#0369a1]/10">
                               {t('admin.dictionary.wordExists')}
                            </span>
                          )}
                        </div>
                        
                        <button
                          onClick={() => handleDeleteWord(entry.word)}
                          disabled={isDeleting === entry.word}
                          className="p-2.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all opacity-0 group-hover:opacity-100 active:scale-90"
                          title={t('admin.dictionary.removeWord')}
                        >
                          {isDeleting === entry.word ? <Loader2 size={18} className="animate-spin" /> : <Trash2 size={18} />}
                        </button>
                      </div>
                    ))}
                </div>
              </div>

              {/* Loader Trigger for Infinite Scroll */}
              {!searchQuery.trim() && hasMore && (
                <div ref={loaderRef} className="flex justify-center py-8">
                  <Loader2 size={24} className="animate-spin text-[#0369a1]/40" />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Feedback / Recent Action */}
        {lastAction && (
          <div className={`
             mx-auto max-w-md p-4 rounded-2xl border flex items-center justify-between gap-4 animate-scale-up shadow-lg
             ${lastAction.type === 'add' ? 'bg-emerald-50 border-emerald-100 text-emerald-700' : 'bg-red-50 border-red-100 text-red-700'}
          `}>
             <div className="flex items-center gap-3">
                <div className={`p-1.5 rounded-lg ${lastAction.type === 'add' ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                   {lastAction.type === 'add' ? <Check size={14} strokeWidth={3} /> : <Trash2 size={14} />}
                </div>
                <span className="font-bold uyghur-text text-sm md:text-base">
                   «{lastAction.word}» {lastAction.type === 'add' ? 'لۇغەتكە قوشۇلدى.' : 'لۇغەتتىن ئۆچۈرۈلدى.'}
                </span>
             </div>
             <button onClick={() => setLastAction(null)} className="p-1 hover:bg-black/5 rounded-md transition-colors">
                <X size={16} />
             </button>
          </div>
        )}
    </div>
  );
};

const RefreshingIcon: React.FC<{ loading: boolean }> = ({ loading }) => (
  <div className={`relative ${loading ? 'opacity-20' : 'opacity-100'} transition-opacity`}>
     {loading && <Loader2 className="animate-spin text-[#0369a1]" size={14} />}
  </div>
);
