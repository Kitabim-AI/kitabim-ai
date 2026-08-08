/**
 * History Dictionary Panel — read-only viewer for Uyghur historical vocabulary.
 */

import {
  AlertCircle,
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
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [duplicateError, setDuplicateError] = useState<string | null>(null);

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
    setDuplicateError(null);
    setIsAddModalOpen(true);
  };

  const openEditModal = (entry: HistoryEntry) => {
    setEditingEntry(entry);
    setFormTerm(entry.term);
    setFormTransliteration(entry.transliteration || '');
    setFormDefinition(entry.definition || '');
    setDuplicateError(null);
    setIsAddModalOpen(true);
  };

  const closeModal = () => {
    setIsAddModalOpen(false);
    setEditingEntry(null);
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
        ? { transliteration: formTransliteration.trim() || null, definition: formDefinition.trim() || null }
        : {
            term: formTerm.trim(),
            transliteration: formTransliteration.trim() || null,
            definition: formDefinition.trim() || null,
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
    <>
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

        {stats && (
          <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] dark:text-[#38bdf8] bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap self-end md:self-auto md:mr-auto">
            <Hash size={12} className="md:w-[14px] md:h-[14px]" />
            {t('admin.historyDictionary.totalEntries', {
              count: stats.total_entries.toLocaleString(),
            })}
          </div>
        )}

        {isAdmin && (
          <button
            onClick={openAddModal}
            title={t('admin.historyDictionary.addEntry')}
            className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 shrink-0"
          >
            <Plus size={14} className="md:w-4 md:h-4" />
            <span className="text-xs md:text-sm font-normal">{t('admin.historyDictionary.addEntry')}</span>
          </button>
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
                {t('admin.historyDictionary.entryNotFound')}
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
                    className="flex items-start justify-between gap-3 px-4 md:px-6 py-4 md:py-5 rounded-2xl transition-all group hover:bg-slate-50/50 dark:hover:bg-slate-800/30"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-baseline gap-2 md:gap-3">
                        <span className="uyghur-text text-sm sm:text-lg font-bold text-slate-800 dark:text-slate-100">
                          {entry.term}
                        </span>
                        {entry.transliteration && (
                          <span className="text-sm sm:text-lg text-slate-400 dark:text-slate-500 font-mono tracking-wide" dir="ltr">
                            {entry.transliteration}
                          </span>
                        )}
                      </div>
                      {entry.definition && (
                        <p className="uyghur-text text-sm sm:text-lg text-slate-500 dark:text-slate-400 font-normal leading-relaxed mt-1.5 whitespace-pre-wrap">
                          {parseDefinition(entry.definition).map((chunk, idx) => {
                            if (chunk.type === 'br') {
                              return <br key={idx} />;
                            }
                            if (chunk.type === 'metadata') {
                              return (
                                <strong key={idx} className="font-bold text-slate-800 dark:text-slate-200">
                                  {chunk.content}
                                </strong>
                              );
                            }
                            return <span key={idx}>{chunk.content}</span>;
                          })}
                        </p>
                      )}
                    </div>
                    {isAdmin && (
                      <div className="flex items-center gap-1.5 md:gap-2 shrink-0">
                        <button
                          onClick={() => openEditModal(entry)}
                          className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 transition-all"
                          title={t('common.edit')}
                        >
                          <Edit2 size={16} />
                        </button>
                        <button
                          onClick={() => handleDeleteEntry(entry)}
                          className="p-2 bg-red-50 dark:bg-red-500/10 text-red-500 dark:text-red-400 rounded-xl hover:bg-red-500 dark:hover:bg-red-600 hover:text-white transition-all"
                          title={t('common.delete')}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    )}
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

    {isAddModalOpen && createPortal(
      <div className="fixed inset-0 z-[200] flex items-center justify-center p-4" dir="rtl" lang="ug">
        <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-md animate-fade-in" onClick={closeModal} />
        <div className="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-[32px] overflow-hidden shadow-2xl animate-scale-up border border-[#0369a1]/10 dark:border-slate-800 flex flex-col">
          <div className="px-8 py-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-[#0369a1]/5 dark:bg-[#38bdf8]/5">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
                {editingEntry ? <Edit2 size={20} /> : <Plus size={20} />}
              </div>
              <h3 className="text-xl font-bold text-[#1a1a1a] dark:text-slate-100">
                {editingEntry ? t('admin.historyDictionary.editEntry') : t('admin.historyDictionary.addEntry')}
              </h3>
            </div>
            <button
              onClick={closeModal}
              className="p-2 hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-400 dark:text-slate-500 hover:text-[#1a1a1a] dark:hover:text-slate-100 rounded-xl transition-all"
            >
              <X size={20} strokeWidth={2.5} />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="p-8 space-y-6 overflow-y-auto max-h-[70vh]">
            <div className="space-y-2">
              <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1">
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
              <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1">
                {t('admin.historyDictionary.transliteration')}
              </label>
              <input
                type="text"
                dir="ltr"
                value={formTransliteration}
                onChange={(e) => setFormTransliteration(e.target.value)}
                className="w-full px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all font-mono text-lg"
                placeholder={t('admin.historyDictionary.transliteration')}
              />
            </div>

            <div className="space-y-2">
              <label className="block text-sm font-bold text-slate-400 dark:text-slate-500 uppercase tracking-widest px-1">
                {t('admin.historyDictionary.definition')}
              </label>
              <textarea
                rows={4}
                dir="rtl"
                value={formDefinition}
                onChange={(e) => setFormDefinition(e.target.value)}
                className="w-full px-5 py-3.5 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text text-base resize-none"
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
              disabled={isSubmitting || !formTerm.trim()}
              className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-8 py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all active:scale-95 disabled:opacity-50 font-bold uppercase tracking-widest text-xs"
            >
              {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : t('common.save')}
            </button>
          </div>
        </div>
      </div>,
      document.body
    )}
    </>
  );
};
