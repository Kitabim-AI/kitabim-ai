/**
 * History Dictionary Panel — read-only viewer for Uyghur historical vocabulary.
 */

import {
  AlertCircle,
  Check,
  ChevronDown,
  Edit2,
  Hash,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useAppContext } from '../../../context/AppContext';
import { useNotification } from '../../../context/NotificationContext';
import { useIsAdmin } from '../../../hooks/useAuth';
import { useI18n } from '../../../i18n/I18nContext';
import { authFetch } from '../../../services/authService';
import { UYGHUR_ALPHABET, sortByUyghurAlphabet, parseDefinition } from '../../../utils/uyghurAlphabet';

interface HistoryEntry {
  id: number;
  term: string;
  transliteration?: string;
  definition?: string;
  letter_group: string;
  is_ai_generated?: boolean;
  aliases?: string[];
}

const PAGE_SIZE = 20;

const UYGHUR_TO_LATIN_GROUP: Record<string, string> = {
  'ئا': 'A', 'ئە': 'E', 'ب': 'B', 'پ': 'P', 'ت': 'T', 'ج': 'J', 'چ': 'CH',
  'خ': 'X', 'د': 'D', 'ر': 'R', 'ز': 'Z', 'ژ': 'ZH', 'س': 'S', 'ش': 'SH',
  'غ': 'GH', 'ف': 'F', 'ق': 'Q', 'ك': 'K', 'گ': 'G', 'ڭ': 'NG', 'ل': 'L',
  'م': 'M', 'ن': 'N', 'ھ': 'H', 'ئو': 'O', 'ئۇ': 'U', 'ئۆ': 'OE', 'ئۈ': 'UE',
  'ۋ': 'W', 'ي': 'Y', 'ئې': 'EE', 'ئى': 'I'
};

export const HistoryDictionaryPanel: React.FC = () => {
  const { t } = useI18n();
  const isAdmin = useIsAdmin();
  const { setModal } = useAppContext();
  const { addNotification } = useNotification();

  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<HistoryEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [stats, setStats] = useState<{ total_entries: number } | null>(null);
  const [letterGroups] = useState<string[]>(UYGHUR_ALPHABET);
  const [activeGroup, setActiveGroup] = useState<string | null>(null);

  const [allEntries, setAllEntries] = useState<HistoryEntry[]>([]);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const loaderRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [editingEntry, setEditingEntry] = useState<HistoryEntry | null>(null);
  const [formTerm, setFormTerm] = useState('');
  const [formTransliteration, setFormTransliteration] = useState('');
  const [formDefinition, setFormDefinition] = useState('');
  const [formAliases, setFormAliases] = useState<string[]>([]);
  const [aliasInput, setAliasInput] = useState('');
  const [formSource, setFormSource] = useState<'ai' | 'web'>('ai');
  const [isSourceDropdownOpen, setIsSourceDropdownOpen] = useState(false);
  const sourceDropdownRef = useRef<HTMLDivElement>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (sourceDropdownRef.current && !sourceDropdownRef.current.contains(event.target as Node)) {
        setIsSourceDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, []);

  const fetchStats = async (group: string | null = activeGroup) => {
    try {
      const params = new URLSearchParams();
      const mappedGroup = group ? (UYGHUR_TO_LATIN_GROUP[group] || group) : null;
      if (mappedGroup) params.set('letter_group', mappedGroup);
      const resp = await authFetch(`/api/history-dictionary/stats?${params}`);
      if (resp.ok) setStats(await resp.json());
    } catch (e) {
      console.error('Failed to fetch history dictionary stats', e);
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
        const mappedGroup = group ? (UYGHUR_TO_LATIN_GROUP[group] || group) : null;
        if (mappedGroup) params.set('letter_group', mappedGroup);
        const resp = await authFetch(`/api/history-dictionary?${params}`);
        if (resp.ok) {
          const data: HistoryEntry[] = await resp.json();
          setAllEntries(prev => (clear ? data : [...prev, ...data]));
          setHasMore(data.length === PAGE_SIZE);
        }
      } catch (e) {
        console.error('Failed to fetch history dictionary entries', e);
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
        `/api/history-dictionary/search?q=${encodeURIComponent(q)}&limit=30`,
      );
      if (resp.ok) setSuggestions(await resp.json());
    } catch (e) {
      console.error('Failed to search history dictionary', e);
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

  const handleDeleteEntry = (entry: HistoryEntry) => {
    setModal({
      isOpen: true,
      title: t('common.delete'),
      message: t('admin.historyDictionary.confirmDelete', { word: entry.term }),
      type: 'confirm',
      confirmText: t('common.delete'),
      destructive: true,
      onConfirm: async () => {
        setModal((prev: any) => ({ ...prev, isLoading: true }));
        try {
          const resp = await authFetch(`/api/history-dictionary/${entry.id}`, { method: 'DELETE' });
          if (!resp.ok) throw new Error('Failed to delete entry');
          setAllEntries(prev => prev.filter(e => e.id !== entry.id));
          setSuggestions(prev => prev.filter(e => e.id !== entry.id));
          fetchStats();
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('admin.historyDictionary.deleteSuccess'), 'success');
        } catch (e) {
          console.error('Failed to delete history dictionary entry', e);
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('admin.historyDictionary.deleteError'), 'error');
        }
      },
    });
  };

  const openAddModal = () => {
    setEditingEntry(null);
    setFormTerm('');
    setFormTransliteration('');
    setFormDefinition('');
    setFormAliases([]);
    setAliasInput('');
    setFormSource('ai');
    setDuplicateError(null);
    setIsAddModalOpen(true);
  };

  const openEditModal = (entry: HistoryEntry) => {
    setEditingEntry(entry);
    setFormTerm(entry.term);
    setFormTransliteration(entry.transliteration || '');
    setFormDefinition(entry.definition || '');
    setFormAliases(entry.aliases || []);
    setAliasInput('');
    setFormSource(entry.is_ai_generated ? 'ai' : 'web');
    setDuplicateError(null);
    setIsAddModalOpen(true);
  };

  const closeModal = () => {
    setIsAddModalOpen(false);
    setEditingEntry(null);
    setFormAliases([]);
    setAliasInput('');
    setDuplicateError(null);
  };

  const refreshCurrentView = async () => {
    if (searchQuery.trim()) {
      await searchEntries(searchQuery);
    } else {
      setAllEntries([]);
      setPage(0);
      setHasMore(true);
      await fetchEntries(0, true, activeGroup);
    }
    await fetchStats();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formTerm.trim()) return;
    setIsSubmitting(true);
    setDuplicateError(null);
    try {
      const isEdit = !!editingEntry;
      const url = isEdit ? `/api/history-dictionary/${editingEntry!.id}` : '/api/history-dictionary';
      const method = isEdit ? 'PATCH' : 'POST';
      const body = isEdit
        ? {
            transliteration: formTransliteration.trim() || null,
            definition: formDefinition.trim() || null,
            is_ai_generated: formSource === 'ai',
            aliases: formAliases,
          }
        : {
            term: formTerm.trim(),
            transliteration: formTransliteration.trim() || null,
            definition: formDefinition.trim() || null,
            is_ai_generated: formSource === 'ai',
            aliases: formAliases,
          };

      const resp = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        if (resp.status === 409) {
          const errorData = await resp.json();
          setDuplicateError(errorData?.detail?.message || t('admin.historyDictionary.createError'));
          return;
        }
        throw new Error(isEdit ? 'Failed to update entry' : 'Failed to create entry');
      }

      closeModal();
      await refreshCurrentView();
      addNotification(
        t(isEdit ? 'admin.historyDictionary.updateSuccess' : 'admin.historyDictionary.createSuccess'),
        'success',
      );
    } catch (e) {
      console.error('Failed to save history dictionary entry', e);
      addNotification(
        t(editingEntry ? 'admin.historyDictionary.updateError' : 'admin.historyDictionary.createError'),
        'error',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in pb-20" dir="rtl" lang="ug">
      {/* Search + Stats row */}
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
            placeholder={t('admin.historyDictionary.searchPlaceholder')}
            dir="rtl"
          />
          {searchQuery && (
            <div className="absolute inset-y-0 left-3 md:left-4 flex items-center gap-1 md:gap-2 z-10">
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

        {(isAdmin || stats) && (
          <div className="flex items-center gap-2 md:gap-3 shrink-0 self-end md:self-auto md:mr-auto">
            {isAdmin && (
              <button
                onClick={openAddModal}
                title={t('admin.historyDictionary.newEntry')}
                className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 shrink-0"
              >
                <Plus size={14} className="md:w-4 md:h-4" />
                <span className="text-xs md:text-sm font-normal">{t('admin.historyDictionary.newEntry')}</span>
              </button>
            )}

            {stats && (
              <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] dark:text-[#38bdf8] bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap">
                <Hash size={12} className="md:w-[14px] md:h-[14px]" />
                {t('admin.historyDictionary.totalEntries', {
                  count: stats.total_entries.toLocaleString(),
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Alphabet Selector */}
      <div className="glass-panel p-4 sm:p-6 rounded-3xl border border-slate-200/60 dark:border-slate-800">
        {/* Letter chips */}
        <div className="flex flex-wrap gap-1.5 justify-center sm:justify-start" dir="rtl">
          <button
            onClick={() => handleGroupSelect(null)}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all uyghur-text ${
              activeGroup === null
                ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            {t('common.all')}
          </button>
          {letterGroups.map((g) => (
            <button
              key={g}
              onClick={() => handleGroupSelect(g)}
              className={`w-9 h-9 rounded-xl text-sm font-bold transition-all uyghur-text flex items-center justify-center ${
                activeGroup === g
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700'
              }`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {/* Results / Entries View */}
      {searchQuery.trim().length > 0 ? (
        /* Search results view */
        <div className="glass-panel p-4 sm:p-6 rounded-3xl border border-slate-200/60 dark:border-slate-800">
          {isSearching ? (
            <div className="py-12 flex justify-center text-slate-400">
              <Loader2 size={24} className="animate-spin" />
            </div>
          ) : suggestions.length === 0 ? (
            <div className="py-12 text-center text-slate-400 uyghur-text text-sm">
              {t('admin.historyDictionary.entryNotFound')}
            </div>
          ) : (
            <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
              {suggestions.map((entry) => (
                <div key={entry.id} className="py-4 flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 md:gap-3">
                      <span className="uyghur-text text-sm sm:text-lg font-bold text-slate-800 dark:text-slate-100">
                        {entry.term}
                      </span>
                      {entry.transliteration && (
                        <span className="text-sm sm:text-lg text-slate-400 dark:text-slate-500 font-mono tracking-wide" dir="ltr">
                          {entry.transliteration}
                        </span>
                      )}
                      <span
                        className={`px-2 py-0.5 rounded-md text-[11px] font-bold font-sans tracking-wide uppercase border ${
                          entry.is_ai_generated
                            ? 'bg-sky-500/10 text-[#0369a1] dark:text-[#38bdf8] border-[#0369a1]/20 dark:border-[#38bdf8]/20'
                            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                        }`}
                      >
                        {entry.is_ai_generated ? t('admin.historyDictionary.sourceAi') : t('admin.historyDictionary.sourceWeb')}
                      </span>
                    </div>
                    {entry.aliases && entry.aliases.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                        {entry.aliases.map((alias, idx) => (
                          <span
                            key={idx}
                            className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700/80 uyghur-text"
                          >
                            {alias}
                          </span>
                        ))}
                      </div>
                    )}
                    {entry.definition && (
                      <p className="uyghur-text text-sm sm:text-lg text-slate-500 dark:text-slate-400 font-normal leading-relaxed mt-1.5 whitespace-pre-wrap">
                        {parseDefinition(entry.definition).map((chunk, idx) => {
                          if (chunk.type === 'br') {
                            return <br key={idx} />;
                          }
                          if (chunk.type === 'metadata') {
                            return (
                              <span key={idx} className="text-xs sm:text-sm text-[#0369a1] dark:text-[#38bdf8] font-bold block mt-1">
                                [{chunk.content}]
                              </span>
                            );
                          }
                          return chunk.content;
                        })}
                      </p>
                    )}
                  </div>
                    {isAdmin && (
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => openEditModal(entry)}
                          title={t('common.edit')}
                          className="p-2 rounded-xl text-slate-400 hover:text-[#0369a1] hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          onClick={() => handleDeleteEntry(entry)}
                          title={t('common.delete')}
                          className="p-2 rounded-xl text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    )}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* Infinite list view */
        <div className="glass-panel p-4 sm:p-6 rounded-3xl border border-slate-200/60 dark:border-slate-800 space-y-4">
          <div className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {allEntries.map((entry) => (
              <div key={entry.id} className="py-4 flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2 md:gap-3">
                    <span className="uyghur-text text-sm sm:text-lg font-bold text-slate-800 dark:text-slate-100">
                      {entry.term}
                    </span>
                    {entry.transliteration && (
                      <span className="text-sm sm:text-lg text-slate-400 dark:text-slate-500 font-mono tracking-wide" dir="ltr">
                        {entry.transliteration}
                      </span>
                    )}
                    <span
                      className={`px-2 py-0.5 rounded-md text-[11px] font-bold font-sans tracking-wide uppercase border ${
                        entry.is_ai_generated
                          ? 'bg-sky-500/10 text-[#0369a1] dark:text-[#38bdf8] border-[#0369a1]/20 dark:border-[#38bdf8]/20'
                          : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                      }`}
                    >
                      {entry.is_ai_generated ? t('admin.historyDictionary.sourceAi') : t('admin.historyDictionary.sourceWeb')}
                    </span>
                  </div>
                  {entry.aliases && entry.aliases.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                      {entry.aliases.map((alias, idx) => (
                        <span
                          key={idx}
                          className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-slate-700/80 uyghur-text"
                        >
                          {alias}
                        </span>
                      ))}
                    </div>
                  )}
                  {entry.definition && (
                    <p className="uyghur-text text-sm sm:text-lg text-slate-500 dark:text-slate-400 font-normal leading-relaxed mt-1.5 whitespace-pre-wrap">
                      {parseDefinition(entry.definition).map((chunk, idx) => {
                        if (chunk.type === 'br') {
                          return <br key={idx} />;
                        }
                        if (chunk.type === 'metadata') {
                          return (
                            <span key={idx} className="text-xs sm:text-sm text-[#0369a1] dark:text-[#38bdf8] font-bold block mt-1">
                              [{chunk.content}]
                            </span>
                          );
                        }
                        return chunk.content;
                      })}
                    </p>
                  )}
                </div>
                {isAdmin && (
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <button
                      onClick={() => openEditModal(entry)}
                      title={t('common.edit')}
                      className="p-2 rounded-xl text-slate-400 hover:text-[#0369a1] hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                    >
                      <Edit2 size={16} />
                    </button>
                    <button
                      onClick={() => handleDeleteEntry(entry)}
                      title={t('common.delete')}
                      className="p-2 rounded-xl text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10 transition-all"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div ref={loaderRef} className="py-6 flex justify-center items-center">
            {isLoadingMore && <Loader2 size={24} className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" />}
            {!hasMore && allEntries.length > 0 && (
              <span className="text-xs text-slate-400 font-medium uyghur-text">
                {t('common.endOfList')}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Add / Edit Modal */}
      {(isAddModalOpen || editingEntry) &&
        createPortal(
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
            <div
              className="w-full max-w-2xl bg-white dark:bg-slate-900 rounded-3xl shadow-2xl border border-slate-200/60 dark:border-slate-800 overflow-hidden"
              dir="rtl"
            >
              <div className="px-8 py-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 uyghur-text">
                  {t(editingEntry ? 'admin.historyDictionary.editEntry' : 'admin.historyDictionary.addEntry')}
                </h3>
                <button
                  onClick={closeModal}
                  className="p-2 rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                >
                  <X size={18} />
                </button>
              </div>

              <form onSubmit={handleSubmit} className="p-8 space-y-6 overflow-y-auto max-h-[70vh]">
                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1 uyghur-text">
                    {t('admin.historyDictionary.term')} <span className="text-red-500">*</span>
                  </label>
                  <input
                    autoFocus
                    required
                    disabled={!!editingEntry}
                    type="text"
                    dir="rtl"
                    value={formTerm}
                    onChange={(e) => setFormTerm(e.target.value)}
                    className={`w-full px-5 py-3.5 border-2 rounded-2xl outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text text-xl ${
                      editingEntry
                        ? 'bg-slate-50 dark:bg-slate-800/50 border-slate-100 dark:border-slate-800 text-slate-400 dark:text-slate-500 cursor-not-allowed'
                        : 'bg-white dark:bg-slate-950 border-slate-100 dark:border-slate-800 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500'
                    }`}
                    placeholder={t('admin.historyDictionary.term')}
                  />
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1 uyghur-text">
                    {t('admin.historyDictionary.transliteration')}
                  </label>
                  <input
                    type="text"
                    dir="ltr"
                    lang="en"
                    data-latin="true"
                    value={formTransliteration}
                    onChange={(e) => setFormTransliteration(e.target.value)}
                    className="w-full px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all font-sans text-base"
                    placeholder={t('admin.historyDictionary.transliteration')}
                  />
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1 uyghur-text">
                    {t('admin.historyDictionary.aliases')}
                  </label>
                  <div className="space-y-3">
                    <div className="flex gap-2">
                      <input
                        type="text"
                        dir="rtl"
                        value={aliasInput}
                        onChange={(e) => setAliasInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            const val = aliasInput.trim();
                            if (val && !formAliases.includes(val)) {
                              setFormAliases([...formAliases, val]);
                              setAliasInput('');
                            }
                          }
                        }}
                        className="flex-1 px-5 py-3 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text text-base"
                        placeholder={t('admin.historyDictionary.aliasesPlaceholder')}
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const val = aliasInput.trim();
                          if (val && !formAliases.includes(val)) {
                            setFormAliases([...formAliases, val]);
                            setAliasInput('');
                          }
                        }}
                        className="px-4 py-3 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 rounded-2xl transition-all flex items-center justify-center"
                      >
                        <Plus size={18} />
                      </button>
                    </div>
                    {formAliases.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {formAliases.map((alias, idx) => (
                          <span
                            key={idx}
                            className="inline-flex items-center gap-1.5 px-3 py-1 bg-sky-500/10 text-[#0369a1] dark:text-[#38bdf8] border border-[#0369a1]/20 dark:border-[#38bdf8]/20 rounded-full text-sm font-semibold uyghur-text"
                          >
                            {alias}
                            <button
                              type="button"
                              onClick={() => setFormAliases(formAliases.filter((_, i) => i !== idx))}
                              className="hover:text-red-500 transition-colors p-0.5"
                            >
                              <X size={14} />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1 uyghur-text">
                    {t('admin.historyDictionary.source')}
                  </label>
                  <div className="relative" ref={sourceDropdownRef}>
                    <button
                      type="button"
                      onClick={() => setIsSourceDropdownOpen(!isSourceDropdownOpen)}
                      className="w-full flex items-center justify-between px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all font-sans text-base shadow-sm"
                    >
                      <span className="font-bold">{formSource === 'ai' ? t('admin.historyDictionary.sourceAi') : t('admin.historyDictionary.sourceWeb')}</span>
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="currentColor" className={`text-slate-400 transition-transform duration-200 ${isSourceDropdownOpen ? 'rotate-180' : ''}`}>
                        <path d="M6 8L2 4h8L6 8z" />
                      </svg>
                    </button>

                    {isSourceDropdownOpen && (
                      <div
                        className="absolute top-full left-0 right-0 mt-2 bg-white/95 dark:bg-slate-900/95 backdrop-blur-xl glass-panel shadow-2xl z-[100] overflow-hidden py-1.5 border border-[#0369a1]/10 dark:border-[#38bdf8]/15 rounded-2xl"
                        dir="rtl"
                      >
                        {[
                          { id: 'ai', label: t('admin.historyDictionary.sourceAi') },
                          { id: 'web', label: t('admin.historyDictionary.sourceWeb') },
                        ].map((option) => (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() => {
                              setFormSource(option.id as 'ai' | 'web');
                              setIsSourceDropdownOpen(false);
                            }}
                            className={`w-full flex items-center px-5 py-3 text-sm font-bold uppercase transition-all ${
                              option.id === formSource
                                ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8]'
                                : 'text-[#1a1a1a] dark:text-slate-200 hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/10'
                            }`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1 uyghur-text">
                    {t('admin.historyDictionary.definition')} <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    required
                    rows={7}
                    dir="rtl"
                    value={formDefinition}
                    onChange={(e) => setFormDefinition(e.target.value)}
                    className="w-full px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text text-base resize-y min-h-[160px]"
                    placeholder={t('admin.historyDictionary.definition')}
                  />
                </div>

                {duplicateError && (
                  <div className="px-4 py-3 rounded-xl bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400 text-sm">
                    {duplicateError}
                  </div>
                )}
              </form>

              <div className="px-8 py-6 bg-slate-50 dark:bg-slate-950/40 border-t border-slate-100 dark:border-slate-800 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-6 py-2.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all font-bold uppercase tracking-widest text-xs"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting || !formTerm.trim() || !formDefinition.trim()}
                  className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-8 py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all active:scale-95 disabled:opacity-50 font-bold uppercase tracking-widest text-xs"
                >
                  {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : t('common.save')}
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
};
