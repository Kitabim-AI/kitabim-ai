import React, { useState, useEffect } from 'react';
import { Check, X, Sparkles, Filter, RefreshCw, CheckCheck, Layers } from 'lucide-react';
import { useI18n } from '../../../i18n/I18nContext';
import { authFetch } from '../../../services/authService';

interface FactCitation {
  bookId: string;
  bookTitle: string;
  volume?: number;
  pages: number[];
}

interface HistoryFact {
  id: number;
  text: string;
  citations: FactCitation[];
  status: 'active' | 'rejected' | 'conflict';
  conflictGroup: number | null;
}

interface StagingItem {
  id: number;
  term: string;
  transliteration?: string;
  definition?: string | null;
  originalDefinition?: string;
  category: string;
  significanceScore: number;
  significanceReason?: string;
  isAiGenerated: boolean;
  entryType: 'new' | 'enrichment';
  existingDictionaryId?: number;
  facts: HistoryFact[];
  status: 'pending' | 'approved' | 'rejected';
  createdAt: string;
}

export const HistoryStagingQueuePanel: React.FC = () => {
  const { t } = useI18n();
  const [items, setItems] = useState<StagingItem[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const [minScore, setMinScore] = useState<number>(5);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [processingId, setProcessingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewingId, setPreviewingId] = useState<number | null>(null);
  const [resolvingFactKey, setResolvingFactKey] = useState<string | null>(null);
  const [showRejectedFor, setShowRejectedFor] = useState<Set<number>>(new Set());

  const fetchQueue = async (isMounted = true) => {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        status: statusFilter,
        minSignificance: minScore.toString(),
        page: '1',
        pageSize: '50',
      });
      const res = await authFetch(`/api/admin/history-dictionary/staging?${query}`);
      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      if (isMounted) {
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (e: any) {
      console.error('Failed to load staging queue', e);
      if (isMounted) {
        setError(e.message || t('admin.historyStagingLoadError') || 'تىزىملىكنى يۈكلىيەلمىدى');
      }
    } finally {
      if (isMounted) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    let isMounted = true;
    fetchQueue(isMounted);
    return () => {
      isMounted = false;
    };
  }, [statusFilter, minScore]);

  const handleApprove = async (id: number) => {
    setProcessingId(id);
    setError(null);
    try {
      const res = await authFetch(`/api/admin/history-dictionary/staging/${id}/approve`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${await res.text()}`);
      }
      setItems((prev) => prev.filter((item) => item.id !== id));
      setTotal((prev) => prev - 1);
    } catch (e: any) {
      console.error(e);
      setError(e.message || t('admin.historyStagingActionError') || 'مەشغۇلات مەغلۇپ بولدى');
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id: number) => {
    setProcessingId(id);
    setError(null);
    try {
      const res = await authFetch(`/api/admin/history-dictionary/staging/${id}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${await res.text()}`);
      }
      setItems((prev) => prev.filter((item) => item.id !== id));
      setTotal((prev) => prev - 1);
    } catch (e: any) {
      console.error(e);
      setError(e.message || t('admin.historyStagingActionError') || 'مەشغۇلات مەغلۇپ بولدى');
    } finally {
      setProcessingId(null);
    }
  };

  const handleBulkApprove = async () => {
    if (!selectedIds.length) return;
    setError(null);
    try {
      const res = await authFetch('/api/admin/history-dictionary/staging/bulk-approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ staging_ids: selectedIds }),
      });
      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      const skipped = (data.results || []).filter((r: any) => r.status !== 'approved');
      if (skipped.length > 0) {
        setError(
          `${skipped.length} item(s) skipped (unresolved conflicts or preview failure) — see term list.`
        );
      }
      setSelectedIds([]);
      fetchQueue();
    } catch (e: any) {
      console.error(e);
      setError(e.message || t('admin.historyStagingActionError') || 'مەشغۇلات مەغلۇپ بولدى');
    }
  };

  const handlePreview = async (id: number) => {
    setPreviewingId(id);
    setError(null);
    try {
      const res = await authFetch(`/api/admin/history-dictionary/staging/${id}/synthesize`, {
        method: 'POST',
      });
      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      setItems((prev) =>
        prev.map((item) => (item.id === id ? { ...item, definition: data.definition } : item))
      );
    } catch (e: any) {
      console.error(e);
      setError(e.message || t('admin.historySynthesisFailed') || 'ئالدىن كۆزىتىشنى قۇرالمىدى.');
    } finally {
      setPreviewingId(null);
    }
  };

  const handleResolveFact = async (
    stagingId: number,
    factId: number,
    factStatus: 'active' | 'rejected'
  ) => {
    const key = `${stagingId}-${factId}`;
    setResolvingFactKey(key);
    setError(null);
    try {
      const res = await authFetch(
        `/api/admin/history-dictionary/staging/${stagingId}/facts/${factId}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: factStatus }),
        }
      );
      if (!res.ok) {
        throw new Error(`Error ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      setItems((prev) =>
        prev.map((item) => (item.id === stagingId ? { ...item, facts: data.item.facts } : item))
      );
    } catch (e: any) {
      console.error(e);
      setError(e.message || t('admin.historyStagingActionError') || 'مەشغۇلات مەغلۇپ بولدى');
    } finally {
      setResolvingFactKey(null);
    }
  };

  const toggleShowRejected = (id: number) => {
    setShowRejectedFor((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  return (
    <div className="space-y-6" dir="rtl" lang="ug">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-4 rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Sparkles className="text-[#0369a1] dark:text-[#38bdf8]" size={22} />
            {t('admin.historyStagingQueue') || 'تارىخىي ئاتالغۇلارنى باھالاش ئۆچىرىتى'}
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            {t('admin.historyStagingDesc') || 'سۈنئىي ئىدراك چىقارغان ئاتالغۇلارنى تەكشۈرۈپ تەستىقلاش (مۇھىملىق دەرىجىسى يۇقىرىدىن تۆۋەنگە)'} ({total})
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
          {selectedIds.length > 0 && (
            <button
              onClick={handleBulkApprove}
              className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-xs font-semibold transition-all shadow-sm active:scale-95"
            >
              <CheckCheck size={16} />
              <span>{t('admin.bulkApprove') || 'تۆپلىمە تەستىقلاش'} ({selectedIds.length})</span>
            </button>
          )}

          {/* Min Score Filter */}
          <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-xl border border-[#0369a1]/10 dark:border-slate-700">
            <Filter size={14} className="text-[#0369a1] dark:text-[#38bdf8]" />
            <select
              value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))}
              className="bg-transparent text-xs text-slate-700 dark:text-slate-300 font-medium focus:outline-none cursor-pointer"
              title={t('admin.minSignificanceFilter') || 'مۇھىملىق دەرىجىسى شۈزگۈچ'}
            >
              <option value={1}>{t('admin.minScoreAll') || 'بارلىق دەرىجىلەر'}</option>
              <option value={3}>{t('admin.minScoreModerate') || 'ئوتتۇراھال'}</option>
              <option value={5}>{t('admin.minScoreImportant') || 'مۇھىم - كۆڭۈلدىكى'}</option>
              <option value={7}>{t('admin.minScoreHigh') || 'يۇقىرى'}</option>
              <option value={9}>{t('admin.minScoreVeryImportant') || 'ئىنتايىن مۇھىم'}</option>
            </select>
          </div>

          {/* Status Filter */}
          <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-xl border border-[#0369a1]/10 dark:border-slate-700">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-xs text-slate-700 dark:text-slate-300 font-medium focus:outline-none cursor-pointer"
            >
              <option value="pending">{t('admin.statusPending') || 'تەستىقلانمىغان'}</option>
              <option value="approved">{t('admin.statusApproved') || 'تەستىقلانغان'}</option>
              <option value="rejected">{t('admin.statusRejected') || 'رەت قىلىنغان'}</option>
            </select>
          </div>

          <button
            onClick={() => fetchQueue()}
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-xl transition-all"
            title={t('common.refresh') || 'قايتا يۈكلەش'}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="glass-panel dark:bg-red-950/20 p-4 bg-red-50 border-2 border-red-200 dark:border-red-900/30 rounded-xl">
          <p className="text-red-650 dark:text-red-400 font-normal">{error}</p>
        </div>
      )}

      {/* Queue List */}
      {loading ? (
        <div className="text-center py-16 text-slate-500">
          <RefreshCw className="animate-spin mx-auto mb-3" size={24} />
          <span>{t('common.loading') || 'يۈكلىنىۋاتىدۇ...'}</span>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 p-12 text-center text-slate-500">
          <Layers size={40} className="mx-auto mb-3 text-slate-300 dark:text-slate-700" />
          <p className="font-medium">{t('admin.noStagingItems') || 'تەكشۈرىدىغان تارىخىي ئاتالغۇ يوق.'}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((item) => {
            const isSelected = selectedIds.includes(item.id);
            const isProcessing = processingId === item.id;
            const isEnrichment = item.entryType === 'enrichment';

            return (
              <div
                key={item.id}
                className={`bg-white dark:bg-slate-900 border rounded-2xl p-5 transition-all shadow-sm ${
                  isSelected ? 'border-[#0369a1] dark:border-[#38bdf8] ring-2 ring-[#0369a1]/20 dark:ring-[#38bdf8]/20' : 'border-[#0369a1]/10 dark:border-slate-800'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(item.id)}
                      className="mt-1.5 h-4 w-4 rounded border-slate-300 text-[#0369a1] focus:ring-[#0369a1]"
                    />
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{item.term}</h3>
                        {item.transliteration && (
                          <span dir="ltr" className="text-xs text-slate-400 font-mono">({item.transliteration})</span>
                        )}

                        {/* Significance Badge */}
                        <span
                          className={`text-xs px-2.5 py-0.5 rounded-full font-bold ${
                            item.significanceScore >= 8
                              ? 'bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800'
                              : 'bg-amber-100 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-300 dark:border-amber-800'
                          }`}
                        >
                          ★ {item.significanceScore}/10
                        </span>

                        {/* Category & Entry Type Badges */}
                        <span className="text-xs px-2 py-0.5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-medium">
                          {item.category}
                        </span>
                        <span
                          className={`text-xs px-2 py-0.5 rounded-md font-semibold ${
                            isEnrichment
                              ? 'bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300'
                              : 'bg-[#0369a1]/10 text-[#0369a1] dark:bg-[#38bdf8]/10 dark:text-[#38bdf8]'
                          }`}
                        >
                          {isEnrichment ? (t('admin.typeEnrichment') || 'تولۇقلاپ بېيىتىش') : (t('admin.typeNew') || 'يېڭى ئاتالغۇ')}
                        </span>
                      </div>

                      {item.significanceReason && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 italic">
                          "{item.significanceReason}"
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    {(() => {
                      const conflictCount = item.facts.filter((f) => f.status === 'conflict').length;
                      return (
                        <button
                          onClick={() => handleApprove(item.id)}
                          disabled={isProcessing || conflictCount > 0}
                          title={
                            conflictCount > 0
                              ? (t('admin.historyApproveBlockedConflicts') || `${conflictCount} زىددىيەتنى بىر تەرەپ قىلىڭ`).replace(
                                  '{count}',
                                  String(conflictCount)
                                )
                              : undefined
                          }
                          className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition-all shadow-sm active:scale-95"
                        >
                          <Check size={14} />
                          <span>{t('admin.approve') || 'تەستىقلاش'}</span>
                        </button>
                      );
                    })()}
                    <button
                      onClick={() => handleReject(item.id)}
                      disabled={isProcessing}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-red-100 dark:bg-red-950/60 hover:bg-red-200 dark:hover:bg-red-900/60 disabled:opacity-50 text-red-600 dark:text-red-400 rounded-xl text-xs font-semibold transition-all active:scale-95"
                    >
                      <X size={14} />
                      <span>{t('admin.reject') || 'رەت قىلىش'}</span>
                    </button>
                  </div>
                </div>

                {/* Facts & conflict resolution */}
                <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/60 space-y-3">
                  {(() => {
                    const activeFacts = item.facts.filter((f) => f.status === 'active');
                    const conflictFacts = item.facts.filter((f) => f.status === 'conflict');
                    const rejectedFacts = item.facts.filter((f) => f.status === 'rejected');
                    const conflictGroups = Array.from(
                      new Set(conflictFacts.map((f) => f.conflictGroup))
                    );
                    const showRejected = showRejectedFor.has(item.id);

                    const renderCitations = (citations: FactCitation[]) => (
                      <span className="text-xs text-slate-400 ms-2">
                        {citations
                          .map(
                            (c) =>
                              `«${c.bookTitle}»${c.volume ? ` ${c.volume}-جىلد` : ''} (${c.pages.join(', ')}-بەت)`
                          )
                          .join('؛ ')}
                      </span>
                    );

                    return (
                      <>
                        {conflictGroups.map((group) => (
                          <div
                            key={`conflict-${group}`}
                            className="border border-amber-400 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/20 rounded-xl p-3 space-y-2"
                          >
                            <span className="text-xs font-bold text-amber-700 dark:text-amber-400">
                              {t('admin.historyFactConflict') || 'زىددىيەتلىك پاكىتلار'}
                            </span>
                            {conflictFacts
                              .filter((f) => f.conflictGroup === group)
                              .map((f) => (
                                <div key={f.id} className="flex items-start justify-between gap-3 text-sm">
                                  <div>
                                    <span className="text-slate-800 dark:text-slate-200">{f.text}</span>
                                    {renderCitations(f.citations)}
                                  </div>
                                  <div className="flex gap-1.5 shrink-0">
                                    <button
                                      disabled={resolvingFactKey === `${item.id}-${f.id}`}
                                      onClick={() => handleResolveFact(item.id, f.id, 'active')}
                                      className="text-xs px-2 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg disabled:opacity-50"
                                    >
                                      {t('admin.historyFactKeepThis') || 'بۇنى ساقلا'}
                                    </button>
                                    <button
                                      disabled={resolvingFactKey === `${item.id}-${f.id}`}
                                      onClick={() => handleResolveFact(item.id, f.id, 'rejected')}
                                      className="text-xs px-2 py-1 bg-red-100 dark:bg-red-950/60 text-red-600 dark:text-red-400 rounded-lg disabled:opacity-50"
                                    >
                                      {t('admin.historyFactReject') || 'رەت قىل'}
                                    </button>
                                  </div>
                                </div>
                              ))}
                          </div>
                        ))}

                        <div className="space-y-1.5">
                          <span className="text-xs font-bold text-slate-500 block">
                            {t('admin.historyFactsActive') || 'پاكىتلار'} ({activeFacts.length})
                          </span>
                          {activeFacts.map((f) => (
                            <div key={f.id} className="text-sm text-slate-700 dark:text-slate-300">
                              • {f.text}
                              {renderCitations(f.citations)}
                            </div>
                          ))}
                        </div>

                        {rejectedFacts.length > 0 && (
                          <div>
                            <button
                              onClick={() => toggleShowRejected(item.id)}
                              className="text-xs text-slate-400 underline"
                            >
                              {showRejected
                                ? t('admin.historyFactsHideRejected') || 'رەت قىلىنغانلارنى يوشۇر'
                                : `${t('admin.historyFactsShowRejected') || 'رەت قىلىنغانلارنى كۆرسەت'} (${rejectedFacts.length})`}
                            </button>
                            {showRejected && (
                              <div className="mt-1.5 space-y-1">
                                {rejectedFacts.map((f) => (
                                  <div key={f.id} className="text-sm text-slate-400 line-through">
                                    • {f.text}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}

                        <div className="flex items-start justify-between gap-3 bg-slate-50 dark:bg-slate-800/40 p-3 rounded-xl">
                          <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                            {item.definition || (t('admin.historyNoPreviewYet') || 'تېخى ئالدىن كۆزىتىش يوق.')}
                          </p>
                          <button
                            onClick={() => handlePreview(item.id)}
                            disabled={previewingId === item.id}
                            className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 bg-[#0369a1]/10 text-[#0369a1] dark:bg-[#38bdf8]/10 dark:text-[#38bdf8] rounded-xl text-xs font-semibold disabled:opacity-50"
                          >
                            <Sparkles size={13} />
                            {previewingId === item.id
                              ? t('admin.historyPreviewing') || 'قۇرۇلۋاتىدۇ...'
                              : t('admin.historyPreview') || 'ئالدىن كۆزىتىش'}
                          </button>
                        </div>
                      </>
                    );
                  })()}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
