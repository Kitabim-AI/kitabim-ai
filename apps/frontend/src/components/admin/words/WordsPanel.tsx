/**
 * Words Panel - Editor/Admin tool to view spell check words list (Read-Only)
 */

import {
  AlertCircle,
  Check,
  Hash,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X
} from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useAppContext } from '../../../context/AppContext';
import { useNotification } from '../../../context/NotificationContext';
import { useIsAdmin } from '../../../hooks/useAuth';
import { useI18n } from '../../../i18n/I18nContext';
import { authFetch } from '../../../services/authService';
import { UYGHUR_ALPHABET, sortByUyghurAlphabet } from '../../../utils/uyghurAlphabet';

interface WordsWord {
  id: number;
  word: string;
}

export const WordsPanel: React.FC = () => {
  const { t } = useI18n();
  const isAdmin = useIsAdmin();
  const { setModal } = useAppContext();
  const { addNotification } = useNotification();
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<WordsWord[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [stats, setStats] = useState<{ total_words: number } | null>(null);
  const [letterGroups] = useState<string[]>(UYGHUR_ALPHABET);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  // Infinite Scroll State
  const [allWords, setAllWords] = useState<WordsWord[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const loaderRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const PAGE_SIZE = 20;

  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, []);

  const fetchStats = async (group: string | null = activeGroup) => {
    try {
      const params = new URLSearchParams();
      if (group) params.set('letter_group', group);
      const resp = await authFetch(`/api/spell-check/words/stats?${params}`);
      if (resp.ok) setStats(await resp.json());
    } catch (e) {
      console.error('Failed to fetch words stats', e);
    }
  };


  const fetchAllWords = useCallback(async (pageNum: number, clear: boolean = false, group: string | null = activeGroup) => {
    if (isLoadingMore) return;
    setIsLoadingMore(true);
    try {
      const params = new URLSearchParams({ skip: String(pageNum * PAGE_SIZE), limit: String(PAGE_SIZE) });
      if (group) params.set('letter_group', group);
      const resp = await authFetch(`/api/spell-check/words?${params}`);
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
  }, [isLoadingMore, activeGroup]);

  const searchWords = async (q: string) => {
    if (!q.trim()) {
      setSuggestions([]);
      return;
    }

    setIsSearching(true);
    try {
      const resp = await authFetch(`/api/spell-check/words/search?q=${encodeURIComponent(q)}&limit=10`);
      if (resp.ok) {
        const data = await resp.json();
        setSuggestions(data);
      }
    } catch (e) {
      console.error('Failed to search words list', e);
    } finally {
      setIsSearching(false);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchAllWords(0, true, null);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      searchWords(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleGroupSelect = (group: string | null) => {
    setActiveGroup(group);
    setPage(0);
    setAllWords([]);
    setHasMore(true);
    fetchStats(group);
    fetchAllWords(0, true, group);
  };

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

  const activeWords = searchQuery.trim() ? suggestions : allWords;

  const handleDeleteWord = (entry: WordsWord) => {
    setModal({
      isOpen: true,
      title: t('common.delete'),
      message: t('admin.words.confirmDelete', { word: entry.word }),
      type: 'confirm',
      confirmText: t('common.delete'),
      destructive: true,
      onConfirm: async () => {
        setModal((prev: any) => ({ ...prev, isLoading: true }));
        try {
          const resp = await authFetch(`/api/spell-check/words/${entry.id}`, { method: 'DELETE' });
          if (!resp.ok) throw new Error('Failed to delete word');
          setAllWords(prev => prev.filter(w => w.id !== entry.id));
          setSuggestions(prev => prev.filter(w => w.id !== entry.id));
          fetchStats();
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('admin.words.deleteSuccess'), 'success');
        } catch (e) {
          console.error('Failed to delete word', e);
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('admin.words.deleteError'), 'error');
        }
      },
    });
  };

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in pb-20" dir="rtl" lang="ug">
      {/* Main Search & Tool Section */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
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
            ref={inputRef}
            className={`w-full pr-11 md:pr-14 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl uyghur-text outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] text-slate-800 dark:text-slate-100 transition-all shadow-sm placeholder:text-slate-300 dark:placeholder:text-slate-500 text-base md:pl-14 ${
              searchQuery ? 'pl-11' : 'pl-4'
            }`}
            placeholder={t('admin.words.searchPlaceholder')}
            dir="rtl"
          />
          <div className="absolute inset-y-0 left-3 md:left-4 flex items-center gap-1 md:gap-2 z-10">
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery('')}
                className="p-1.5 md:p-2 text-slate-300 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                title={t('common.clear')}
              >
                <X strokeWidth={2.5} className="w-4 h-4 md:w-5 md:h-5" />
              </button>
            )}
          </div>
        </div>

        {stats && (
          <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] dark:text-[#38bdf8] bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap self-end md:self-auto md:mr-auto">
            <Hash size={12} className="md:w-[14px] md:h-[14px]" />
            {t('admin.words.totalWords', { count: stats.total_words.toLocaleString() })}
          </div>
        )}
      </div>

      {/* Letter group filter pills */}
      {!searchQuery.trim() && letterGroups.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handleGroupSelect(null)}
            className={`px-3 py-1 rounded-full text-[12px] md:text-[13px] uyghur-text transition-all border ${
              activeGroup === null
                ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 border-[#0369a1] dark:border-[#38bdf8]'
                : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-200 border-slate-200 dark:border-slate-800 hover:border-[#0369a1]/40 dark:hover:border-[#38bdf8]/40 hover:text-[#0369a1] dark:hover:text-[#38bdf8]'
            }`}
          >
            {t('common.all')}
          </button>
          {letterGroups.map((group) => (
            <button
              key={group}
              onClick={() => handleGroupSelect(group)}
              className={`px-3 py-1 rounded-full text-[13px] md:text-[14px] uyghur-text transition-all border ${
                activeGroup === group
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 border-[#0369a1] dark:border-[#38bdf8]'
                  : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-200 border-slate-200 dark:border-slate-800 hover:border-[#0369a1]/40 dark:hover:border-[#38bdf8]/40 hover:text-[#0369a1] dark:hover:text-[#38bdf8]'
              }`}
            >
              {group}
            </button>
          ))}
        </div>
      )}

      {/* Search Results / Full List */}
      <div className="space-y-3">
        {isSearching && activeWords.length === 0 && (
           <div className="flex justify-center py-20">
              <Loader2 size={40} className="animate-spin text-[#0369a1]/20" />
           </div>
        )}

        {searchQuery.trim() && !isSearching && suggestions.length === 0 && (
          <div className="glass-panel rounded-[24px] md:rounded-[32px] py-8 md:py-12 px-4 md:px-8 flex flex-col items-center justify-center gap-3 md:gap-4 text-center animate-fade-in shadow-lg border border-[#0369a1]/10">
             <div className="p-3 md:p-4 bg-amber-50 dark:bg-amber-500/10 text-amber-500 dark:text-amber-400 rounded-full shadow-inner ring-4 ring-amber-50/50 dark:ring-amber-500/10">
                <AlertCircle className="w-6 h-6 md:w-8 md:h-8" />
             </div>
             <div className="space-y-1">
                <h3 className="text-lg md:text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('admin.words.wordNotFound')}</h3>
                <p className="text-slate-400 font-bold text-[9px] md:text-xs uppercase tracking-widest opacity-60 line-clamp-1">{searchQuery}</p>
             </div>
          </div>
        )}

        {activeWords.length > 0 && (
          <div className="space-y-3">
            <div className="glass-panel rounded-[32px] p-2 overflow-hidden shadow-xl animate-fade-in border border-[#0369a1]/5 dark:border-[#38bdf8]/10">
              <div className="grid grid-cols-1 gap-1">
                  {activeWords.map((entry) => (
                    <div
                      key={entry.id}
                      className={`
                        flex items-center justify-between gap-3 px-4 md:px-6 py-3 md:py-4 rounded-2xl transition-all group
                        ${entry.word === searchQuery.trim() ? 'bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 ring-1 ring-[#0369a1]/10 dark:ring-[#38bdf8]/20' : 'hover:bg-slate-50/50 dark:hover:bg-slate-800/30'}
                      `}
                    >
                      <div className="flex items-center gap-3 md:gap-4 min-w-0">
                        <div className={`p-1.5 md:p-2 rounded-lg ${entry.word === searchQuery.trim() ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950' : 'bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500'}`}>
                           <Check size={14} strokeWidth={3} className="w-3 h-3 md:w-3.5 md:h-3.5" />
                        </div>
                        <span className={`uyghur-text text-sm sm:text-lg ${entry.word === searchQuery.trim() ? 'font-bold text-[#0369a1] dark:text-[#38bdf8]' : 'text-slate-700 dark:text-slate-200 font-normal'}`}>
                           {entry.word}
                        </span>
                        {entry.word === searchQuery.trim() && (
                          <span className="text-[8px] md:text-[10px] font-bold text-[#0369a1]/60 dark:text-[#38bdf8]/60 uppercase tracking-widest bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-2 md:px-2.5 py-0.5 md:py-1 rounded-full border border-[#0369a1]/10 dark:border-[#38bdf8]/10">
                             {t('admin.words.wordExists')}
                          </span>
                        )}
                      </div>
                      {isAdmin && (
                        <button
                          onClick={() => handleDeleteWord(entry)}
                          className="p-2 shrink-0 bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 rounded-xl hover:bg-red-500 dark:hover:bg-red-600 hover:text-white transition-all"
                          title={t('common.delete')}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
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
    </div>
  );
};
