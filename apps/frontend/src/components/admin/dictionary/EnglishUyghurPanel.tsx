/**
 * English-Uyghur Dictionary Panel — read-only bilingual dictionary viewer.
 */

import {
  AlertCircle,
  Hash,
  Loader2,
  RefreshCw,
  Search,
  X,
} from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../../i18n/I18nContext';
import { authFetch } from '../../../services/authService';

interface EnglishUyghurEntry {
  id: number;
  english: string;
  uyghur: string;
  letter_group: string;
}

const PAGE_SIZE = 20;

const ENGLISH_ALPHABET = [
  'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z'
];

export const EnglishUyghurPanel: React.FC = () => {
  const { t } = useI18n();

  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<EnglishUyghurEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [stats, setStats] = useState<{ total_entries: number } | null>(null);
  const [letterGroups] = useState<string[]>(ENGLISH_ALPHABET);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  const [allEntries, setAllEntries] = useState<EnglishUyghurEntry[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const loaderRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
      const resp = await authFetch(`/api/english-uyghur-dictionary/stats?${params}`);
      if (resp.ok) setStats(await resp.json());
    } catch (e) {
      console.error('Failed to fetch English-Uyghur dictionary stats', e);
    }
  };


  const fetchEntries = useCallback(
    async (pageNum: number, clear = false, group: string | null = activeGroup) => {
      if (isLoadingMore) return;
      setIsLoadingMore(true);
      try {
        const params = new URLSearchParams({
          skip: String(pageNum * PAGE_SIZE),
          limit: String(PAGE_SIZE),
        });
        if (group) params.set('letter_group', group);
        const resp = await authFetch(`/api/english-uyghur-dictionary?${params}`);
        if (resp.ok) {
          const data: EnglishUyghurEntry[] = await resp.json();
          setAllEntries(prev => (clear ? data : [...prev, ...data]));
          setHasMore(data.length === PAGE_SIZE);
        }
      } catch (e) {
        console.error('Failed to fetch English-Uyghur dictionary entries', e);
      } finally {
        setIsLoadingMore(false);
      }
    },
    [isLoadingMore, activeGroup],
  );

  const searchEntries = async (q: string) => {
    if (!q.trim()) {
      setSuggestions([]);
      return;
    }
    setIsSearching(true);
    try {
      const resp = await authFetch(
        `/api/english-uyghur-dictionary/search?q=${encodeURIComponent(q)}&limit=10`,
      );
      if (resp.ok) setSuggestions(await resp.json());
    } catch (e) {
      console.error('Failed to search English-Uyghur dictionary', e);
    } finally {
      setIsSearching(false);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchEntries(0, true, null);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => searchEntries(searchQuery), 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleGroupSelect = (group: string | null) => {
    setActiveGroup(group);
    setPage(0);
    setAllEntries([]);
    setHasMore(true);
    fetchStats(group);
    fetchEntries(0, true, group);
  };

  useEffect(() => {
    if (!hasMore || isLoadingMore || searchQuery.trim()) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          const next = page + 1;
          setPage(next);
          fetchEntries(next);
        }
      },
      { threshold: 0.1 },
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, page, fetchEntries, searchQuery]);

  const activeEntries = searchQuery.trim() ? suggestions : allEntries;

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in pb-20" dir="rtl">
      {/* Search + Stats row */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 left-4 md:left-5 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
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
            className="w-full pl-11 md:pl-14 pr-10 md:pr-11 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] text-slate-800 dark:text-slate-100 placeholder:text-slate-300 dark:placeholder:text-slate-500 text-base"
            placeholder={t('admin.englishUyghurDictionary.searchPlaceholder')}
            dir="ltr"
            lang="en"
            data-latin="true"
          />
          {searchQuery && (
            <div className="absolute inset-y-0 right-3 md:right-4 flex items-center z-10">
              <button
                onClick={() => setSearchQuery('')}
                className="p-1.5 md:p-2 text-slate-300 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                title={t('common.clear')}
              >
                <X strokeWidth={2.5} className="w-4 h-4 md:w-5 md:h-5" />
              </button>
            </div>
          )}
        </div>

        {stats && (
          <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] dark:text-[#38bdf8] bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap self-end md:self-auto">
            <Hash size={12} className="md:w-[14px] md:h-[14px]" />
            {t('admin.englishUyghurDictionary.totalEntries', {
              count: stats.total_entries.toLocaleString(),
            })}
          </div>
        )}
      </div>

      {/* Letter group filter pills */}
      {!searchQuery.trim() && letterGroups.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handleGroupSelect(null)}
            className={`px-3 py-1 rounded-full text-[12px] md:text-[13px] transition-all border ${
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
              className={`px-3 py-1 rounded-full text-[13px] md:text-[14px] font-mono transition-all border ${
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

      {/* Entry list */}
      <div className="space-y-3">
        {isSearching && activeEntries.length === 0 && (
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
              <h3 className="text-lg md:text-xl font-normal text-[#1a1a1a] dark:text-slate-100">
                {t('admin.englishUyghurDictionary.entryNotFound')}
              </h3>
              <p className="text-slate-400 font-bold text-[9px] md:text-xs uppercase tracking-widest opacity-60 line-clamp-1">
                {searchQuery}
              </p>
            </div>
          </div>
        )}

        {activeEntries.length > 0 && (
          <div className="space-y-3">
            <div className="glass-panel rounded-[32px] p-2 overflow-hidden shadow-xl animate-fade-in border border-[#0369a1]/5 dark:border-[#38bdf8]/10">
              <div className="grid grid-cols-1 gap-1">
                {activeEntries.map((entry) => (
                  <div
                    key={entry.id}
                    className="flex items-start justify-between px-4 md:px-6 py-4 md:py-5 rounded-2xl transition-all group hover:bg-slate-50/50 dark:hover:bg-slate-800/30"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-baseline gap-2 md:gap-3">
                        <span className="text-[16px] md:text-xl font-bold text-slate-800 dark:text-slate-100">
                          {entry.english}
                        </span>
                      </div>
                      <p className="uyghur-text text-[13px] md:text-[14px] text-slate-500 dark:text-slate-400 font-normal leading-relaxed mt-1.5 whitespace-pre-wrap" dir="rtl" lang="ug">
                        {entry.uyghur}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

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
