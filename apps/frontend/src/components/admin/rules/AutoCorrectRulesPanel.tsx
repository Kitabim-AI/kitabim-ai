/**
 * Auto-Correction Rules Panel - CRUD interface for global spell rules
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Sparkles, Plus, Save, X, Edit2, Trash2, Search, Check, AlertTriangle, 
  Loader2, RefreshCw, BarChart2, Clock, Inbox
} from 'lucide-react';
import { authFetch } from '../../../services/authService';
import { useI18n } from '../../../i18n/I18nContext';
import { ProverbDisplay } from '../../common/ProverbDisplay';

interface AutoCorrectRule {
  id: number;
  misspelled_word: string;
  corrected_word: string;
  is_active: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

interface RuleStats {
  total_rules: number;
  active_rules: number;
  total_auto_corrected: number;
  pending_corrections: number;
}

export function AutoCorrectRulesPanel() {
  const { t } = useI18n();
  const [rules, setRules] = useState<AutoCorrectRule[]>([]);
  const [stats, setStats] = useState<RuleStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Pagination / Infinite Scroll state
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const loaderRef = useRef<HTMLDivElement>(null);

  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState<AutoCorrectRule | null>(null);
  const [editingRule, setEditingRule] = useState<AutoCorrectRule | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form states
  const [misspelled, setMisspelled] = useState('');
  const [corrected, setCorrected] = useState('');
  const [isActive, setIsActive] = useState(false);
  const [description, setDescription] = useState('');

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const loadStats = useCallback(async () => {
    try {
      const statsRes = await authFetch('/api/auto-correct-rules/stats');
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }, []);

  const loadRules = useCallback(async (isInitial = false) => {
    if (!isInitial && (isLoading || isLoadingMore || !hasMore)) return;

    try {
      if (isInitial) {
        setIsLoading(true);
        setPage(1);
      } else {
        setIsLoadingMore(true);
      }
      
      setError(null);
      const nextPage = isInitial ? 1 : page + 1;
      const skip = (nextPage - 1) * pageSize;
      const searchParam = debouncedSearch ? `&search=${encodeURIComponent(debouncedSearch)}` : '';
      const response = await authFetch(`/api/auto-correct-rules?skip=${skip}&limit=${pageSize}${searchParam}`);

      if (!response.ok) {
        throw new Error(t('admin.autoCorrectRules.error') || 'Failed to load rules');
      }

      const data = await response.json();
      
      if (isInitial) {
        setRules(data.items);
      } else {
        setRules(prev => {
          const existingIds = prev.map(r => r.id);
          const newItems = data.items.filter((r: AutoCorrectRule) => !existingIds.includes(r.id));
          return [...prev, ...newItems];
        });
        setPage(nextPage);
      }

      setTotalCount(data.total);
      setHasMore(data.items.length === pageSize && (isInitial ? data.items.length : rules.length + data.items.length) < data.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load auto-correction rules');
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [page, pageSize, debouncedSearch, isLoading, isLoadingMore, hasMore, rules.length, t]);

  // Initial load or search change
  useEffect(() => {
    loadRules(true);
  }, [debouncedSearch]);

  // Infinite Scroll Observer
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isLoading && !isLoadingMore && hasMore) {
          loadRules(false);
        }
      },
      { threshold: 0.1, rootMargin: '1200px' }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [loadRules, isLoading, isLoadingMore, hasMore]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  const handleRefresh = async () => {
    await Promise.all([loadRules(true), loadStats()]);
  };

  const openAddModal = () => {
    setEditingRule(null);
    setMisspelled('');
    setCorrected('');
    setIsActive(true);
    setDescription('');
    setIsModalOpen(true);
  };

  const openEditModal = (rule: AutoCorrectRule) => {
    setEditingRule(rule);
    setMisspelled(rule.misspelled_word);
    setCorrected(rule.corrected_word);
    setIsActive(rule.is_active);
    setDescription(rule.description || '');
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!misspelled.trim() || !corrected.trim()) return;

    setIsSubmitting(true);
    try {
      const isEdit = !!editingRule;
      const url = isEdit 
        ? `/api/auto-correct-rules/${editingRule!.misspelled_word}` 
        : '/api/auto-correct-rules';
      
      const method = isEdit ? 'PATCH' : 'POST';
      const body = isEdit 
        ? { corrected_word: corrected.trim(), is_active: isActive, description: description.trim() || null }
        : { misspelled_word: misspelled.trim(), corrected_word: corrected.trim(), is_active: isActive, description: description.trim() || null };

      const response = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(typeof errorData.detail === 'string' ? errorData.detail : 'Failed to save rule');
      }

      setIsModalOpen(false);
      await Promise.all([loadRules(true), loadStats()]);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!isDeleting) return;

    setIsSubmitting(true);
    try {
      const response = await authFetch(`/api/auto-correct-rules/${isDeleting.misspelled_word}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error('Failed to delete rule');
      }

      setIsDeleting(null);
      await Promise.all([loadRules(true), loadStats()]);
    } catch (err: any) {
      alert(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleRuleActive = async (rule: AutoCorrectRule) => {
    try {
      const response = await authFetch(`/api/auto-correct-rules/${rule.misspelled_word}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !rule.is_active }),
      });

      if (!response.ok) throw new Error('Failed to update status');
      
      setRules(prev => prev.map(r => r.id === rule.id ? { ...r, is_active: !rule.is_active } : r));
      await loadStats();
    } catch (err: any) {
      alert(err.message);
    }
  };

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-3 md:gap-4 group">
          <div className="self-start mt-1 p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 icon-shake">
            <Sparkles size={20} className="md:w-6 md:h-6" />
          </div>
          <div>
            <h2 className="text-xl md:text-2xl lg:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.autoCorrectRules.title')}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-6 md:w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <ProverbDisplay
                keywords={t('proverbs.admin')}
                size="sm"
                className="opacity-70 mt-[-2px]"
                defaultText={t('admin.autoCorrectRules.subtitle')}
              />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 md:gap-3">
          <button
            onClick={handleRefresh}
            className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-white text-[#0369a1] rounded-xl border border-[#0369a1]/20 hover:border-[#0369a1] transition-all shadow-sm"
          >
            <RefreshCw size={14} className={(isLoading || isLoadingMore) ? 'animate-spin' : ''} />
            <span className="text-xs md:text-sm font-normal">{t('common.refresh')}</span>
          </button>
          <button
            onClick={openAddModal}
            className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/20"
          >
            <Plus size={14} className="md:w-4 md:h-4" />
            <span className="text-xs md:text-sm font-normal">{t('admin.autoCorrectRules.add')}</span>
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-4">
          <div className="glass-panel p-4 md:p-5 rounded-3xl border border-[#0369a1]/5 hover:border-[#0369a1]/20 transition-all group">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-blue-50 text-blue-600 rounded-xl group-hover:scale-110 transition-transform">
                <BarChart2 size={16} className="md:w-[18px] md:h-[18px]" />
              </div>
              <span className="text-[10px] md:text-xs font-bold text-slate-400 uppercase tracking-wider">{t('admin.autoCorrectRules.stats.total')}</span>
            </div>
            <div className="text-lg md:text-2xl font-bold text-slate-700">{stats.total_rules}</div>
          </div>
          <div className="glass-panel p-4 md:p-5 rounded-3xl border border-[#0369a1]/5 hover:border-[#0369a1]/20 transition-all group">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-emerald-50 text-emerald-600 rounded-xl group-hover:scale-110 transition-transform">
                <Check size={16} className="md:w-[18px] md:h-[18px]" />
              </div>
              <span className="text-[10px] md:text-xs font-bold text-slate-400 uppercase tracking-wider">{t('admin.autoCorrectRules.stats.active')}</span>
            </div>
            <div className="text-lg md:text-2xl font-bold text-slate-700">{stats.active_rules}</div>
          </div>
          <div className="glass-panel p-4 md:p-5 rounded-3xl border border-[#0369a1]/5 hover:border-[#0369a1]/20 transition-all group">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-purple-50 text-purple-600 rounded-xl group-hover:scale-110 transition-transform">
                <Sparkles size={16} className="md:w-[18px] md:h-[18px]" />
              </div>
              <span className="text-[10px] md:text-xs font-bold text-slate-400 uppercase tracking-wider">{t('admin.autoCorrectRules.stats.applied')}</span>
            </div>
            <div className="text-lg md:text-2xl font-bold text-slate-700">{stats.total_auto_corrected}</div>
          </div>
          <div className="glass-panel p-4 md:p-5 rounded-3xl border border-[#0369a1]/5 hover:border-[#0369a1]/20 transition-all group">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-amber-50 text-amber-600 rounded-xl group-hover:scale-110 transition-transform">
                <Clock size={16} className="md:w-[18px] md:h-[18px]" />
              </div>
              <span className="text-[10px] md:text-xs font-bold text-slate-400 uppercase tracking-wider">{t('admin.autoCorrectRules.stats.pending')}</span>
            </div>
            <div className="text-lg md:text-2xl font-bold text-slate-700">{stats.pending_corrections}</div>
          </div>
        </div>
      )}

      {/* Search Bar */}
      <div className="relative group">
        <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1]">
          <Search size={18} strokeWidth={3} />
        </div>
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('common.search')}
          className="w-full pr-12 pl-6 py-3 md:py-3.5 bg-white border-2 border-[#0369a1]/10 rounded-[16px] md:rounded-[24px] outline-none focus:border-[#0369a1] transition-all uyghur-text shadow-sm text-sm md:text-base"
        />
        {searchQuery && (
          <button
            onClick={() => setSearchQuery('')}
            className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-[#0369a1] transition-colors"
          >
            <X size={18} />
          </button>
        )}
      </div>

      {/* Rules Table */}
      <div className="glass-panel overflow-hidden rounded-[20px] md:rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10 relative">
        {isLoading && rules.length === 0 && (
          <div className="absolute inset-0 bg-white/60 backdrop-blur-[2px] z-10 flex items-center justify-center min-h-[400px]">
             <Loader2 size={32} className="md:w-10 md:h-10 text-[#0369a1] animate-spin" />
          </div>
        )}
        
        <div className="overflow-x-auto custom-scrollbar">
          <table className="w-full text-right" dir="rtl">
            <thead>
              <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-[10px] sm:text-[13px] md:text-[14px] lg:text-[15px] font-bold text-[#0369a1] uppercase leading-tight">
                <th className="px-2 sm:px-4 md:px-6 py-4 md:py-5 font-bold text-right whitespace-nowrap">{t('admin.autoCorrectRules.misspelled')}</th>
                <th className="px-2 sm:px-4 md:px-6 py-4 md:py-5 font-bold text-right whitespace-nowrap">{t('admin.autoCorrectRules.corrected')}</th>
                <th className="hidden lg:table-cell px-6 py-5 font-bold text-right">{t('admin.autoCorrectRules.description')}</th>
                <th className="hidden sm:table-cell px-4 md:px-6 py-4 md:py-5 font-bold text-center w-24 whitespace-nowrap">{t('admin.autoCorrectRules.isActive')}</th>
                <th className="px-2 sm:px-4 md:px-6 py-4 md:py-5 font-bold text-left whitespace-nowrap">{t('admin.autoCorrectRules.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#0369a1]/5">
              {rules.length === 0 && !isLoading ? (
                <tr>
                  <td colSpan={6} className="py-20 text-center">
                    <div className="p-6 bg-slate-50 rounded-[32px] mb-6 text-slate-200 inline-block">
                      <Inbox size={48} />
                    </div>
                    <h3 className="text-xl font-normal text-[#1a1a1a] mb-2">{t('admin.autoCorrectRules.empty')}</h3>
                  </td>
                </tr>
              ) : (
                rules.map(rule => (
                  <tr key={rule.id} className="hover:bg-[#0369a1]/5 transition-colors group/row">
                    <td className="px-4 md:px-6 py-4 md:py-5">
                      <span className="font-bold text-red-500 bg-red-50 px-2 md:px-2.5 py-1 md:py-1.5 rounded-lg border border-red-100 uyghur-text text-sm md:text-lg">
                        {rule.misspelled_word}
                      </span>
                    </td>
                    <td className="px-4 md:px-6 py-4 md:py-5">
                      <span className="font-bold text-[#0369a1] bg-[#0369a1]/5 px-2 md:px-2.5 py-1 md:py-1.5 rounded-lg border border-[#0369a1]/10 uyghur-text text-sm md:text-lg">
                        {rule.corrected_word}
                      </span>
                    </td>
                    <td className="hidden lg:table-cell px-6 py-5">
                      <span className="text-sm text-slate-500 uyghur-text leading-relaxed block max-w-xs truncate" title={rule.description || ''}>
                        {rule.description || <em className="opacity-40 italic">--</em>}
                      </span>
                    </td>
                    <td className="hidden sm:table-cell px-4 md:px-6 py-4 md:py-5 text-center">
                      <button
                        onClick={() => toggleRuleActive(rule)}
                        className={`inline-flex items-center px-2 md:px-3 py-1 md:py-1.5 rounded-full text-[9px] md:text-[10px] font-bold uppercase transition-all ${
                          rule.is_active 
                            ? 'bg-emerald-100 text-emerald-700' 
                            : 'bg-slate-100 text-slate-400 opacity-60'
                        }`}
                      >
                        {rule.is_active ? t('common.active') : t('common.suspended')}
                      </button>
                    </td>
                    <td className="px-4 md:px-6 py-4 md:py-5 text-left">
                      <div className="flex items-center justify-end gap-1.5 md:gap-2">
                        <button
                          onClick={() => openEditModal(rule)}
                          className="p-1.5 md:p-2 bg-[#0369a1]/10 text-[#0369a1] rounded-lg md:rounded-xl hover:bg-[#0369a1] hover:text-white transition-all shadow-sm"
                          title={t('common.edit')}
                        >
                          <Edit2 size={14} className="md:w-4 md:h-4" />
                        </button>
                        <button
                          onClick={() => setIsDeleting(rule)}
                          className="p-1.5 md:p-2 bg-red-50 text-red-500 rounded-lg md:rounded-xl hover:bg-red-500 hover:text-white transition-all shadow-sm"
                          title={t('common.delete')}
                        >
                          <Trash2 size={14} className="md:w-4 md:h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Infinite Scroll Trigger */}
        <div ref={loaderRef} className="px-8 py-8 border-t border-[#0369a1]/10 flex flex-col items-center justify-center bg-[#0369a1]/5 gap-4">
          {isLoadingMore && (
            <div className="flex flex-col items-center gap-3 animate-fade-in">
              <div className="w-8 h-8 border-2 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
              <span className="text-[10px] font-black text-[#0369a1] uppercase animate-pulse">{t('common.loadingMore')}</span>
            </div>
          )}
          {!hasMore && rules.length > 0 && (
            <div className="flex flex-col items-center gap-3 opacity-30">
              <div className="w-12 h-[1px] bg-[#94a3b8]" />
              <p className="text-[10px] font-black text-[#94a3b8] uppercase">{t('common.endOfList')}</p>
              <div className="w-12 h-[2px] bg-[#94a3b8]" />
            </div>
          )}
        </div>
      </div>

      {/* Add / Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4" dir="rtl" lang="ug">
          <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-md animate-fade-in" onClick={() => setIsModalOpen(false)} />
          <div className="relative w-full max-w-lg bg-white rounded-[32px] overflow-hidden shadow-2xl animate-scale-up border border-[#0369a1]/10 flex flex-col">
            <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-[#0369a1]/5">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
                  {editingRule ? <Edit2 size={20} /> : <Plus size={20} />}
                </div>
                <h3 className="text-xl font-bold text-[#1a1a1a]">
                  {editingRule ? t('admin.autoCorrectRules.editRule') : t('admin.autoCorrectRules.createNew')}
                </h3>
              </div>
              <button 
                onClick={() => setIsModalOpen(false)} 
                className="p-2 hover:bg-slate-200 text-slate-400 hover:text-[#1a1a1a] rounded-xl transition-all"
              >
                <X size={20} strokeWidth={2.5} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="p-8 space-y-6 overflow-y-auto max-h-[70vh]">
              <div className="space-y-2">
                <label className="block text-sm font-bold text-slate-400 uppercase tracking-widest px-1">
                  {t('admin.autoCorrectRules.misspelled')} <span className="text-red-500">*</span>
                </label>
                <input
                  autoFocus
                  required
                  disabled={!!editingRule}
                  type="text"
                  value={misspelled}
                  onChange={(e) => setMisspelled(e.target.value)}
                  className={`w-full px-5 py-3.5 border-2 rounded-2xl outline-none focus:border-[#0369a1] transition-all uyghur-text text-xl ${
                    editingRule ? 'bg-slate-50 border-slate-100 text-slate-400 cursor-not-allowed' : 'bg-white border-slate-100'
                  }`}
                  placeholder={t('admin.autoCorrectRules.misspelled')}
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-bold text-slate-400 uppercase tracking-widest px-1">
                  {t('admin.autoCorrectRules.corrected')} <span className="text-red-500">*</span>
                </label>
                <input
                  required
                  type="text"
                  value={corrected}
                  onChange={(e) => setCorrected(e.target.value)}
                  className="w-full px-5 py-3.5 border-2 border-slate-100 rounded-2xl bg-white outline-none focus:border-[#0369a1] transition-all uyghur-text text-xl"
                  placeholder={t('admin.autoCorrectRules.corrected')}
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-bold text-slate-400 uppercase tracking-widest px-1">
                  {t('admin.autoCorrectRules.description')}
                </label>
                <textarea
                  rows={3}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-5 py-3.5 border-2 border-slate-100 rounded-2xl bg-white outline-none focus:border-[#0369a1] transition-all uyghur-text text-base resize-none"
                  placeholder={t('admin.autoCorrectRules.description')}
                />
              </div>

              <div className="flex items-center gap-3 px-1">
                <button
                  type="button"
                  onClick={() => setIsActive(!isActive)}
                  className={`w-12 h-6 rounded-full transition-all relative ${isActive ? 'bg-emerald-500' : 'bg-slate-200'}`}
                >
                  <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${isActive ? 'left-1' : 'left-7'}`} />
                </button>
                <span className="text-sm font-bold text-slate-600 uppercase tracking-wide">
                  {t('admin.autoCorrectRules.isActive')}
                </span>
              </div>
            </form>

            <div className="px-8 py-6 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="px-6 py-2.5 bg-white border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-all font-bold uppercase tracking-widest text-xs"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleSubmit}
                disabled={isSubmitting || !misspelled.trim() || !corrected.trim()}
                className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-8 py-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 hover:bg-[#0284c7] transition-all active:scale-95 disabled:opacity-50 font-bold uppercase tracking-widest text-xs"
              >
                {isSubmitting ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {isDeleting && (
        <div className="fixed inset-0 z-[210] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm animate-fade-in" onClick={() => setIsDeleting(null)} />
          <div className="relative w-full max-w-sm bg-white rounded-[40px] p-8 shadow-2xl animate-scale-up border border-[#0369a1]/10 flex flex-col items-center text-center">
            <div className="w-20 h-20 bg-red-50 text-red-500 rounded-full flex items-center justify-center mb-6 shadow-inner ring-8 ring-red-50/50">
              <Trash2 size={40} />
            </div>
            <h3 className="text-2xl font-bold text-[#1a1a1a] mb-3 uyghur-text">
              {t('common.delete')}
            </h3>
            <p className="text-slate-500 mb-8 uyghur-text leading-relaxed">
              {t('admin.autoCorrectRules.confirmDelete')}
              <span className="block mt-2 font-bold text-red-500 text-lg">
                "{isDeleting.misspelled_word}" → "{isDeleting.corrected_word}"
              </span>
            </p>
            <div className="flex gap-3 w-full">
              <button
                onClick={() => setIsDeleting(null)}
                className="flex-1 py-3 bg-slate-100 text-slate-600 rounded-2xl font-bold uppercase tracking-widest text-xs hover:bg-slate-200 transition-all active:scale-95"
              >
                {t('common.cancel')}
              </button>
              <button
                onClick={handleDelete}
                disabled={isSubmitting}
                className="flex-1 py-3 bg-red-500 text-white rounded-2xl font-bold uppercase tracking-widest text-xs shadow-lg shadow-red-500/20 hover:bg-red-600 transition-all active:scale-95 disabled:opacity-50"
              >
                {isSubmitting ? <Loader2 size={16} className="animate-spin mx-auto" /> : t('common.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AutoCorrectRulesPanel;
