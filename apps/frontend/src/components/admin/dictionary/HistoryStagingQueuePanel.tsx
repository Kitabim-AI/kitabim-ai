import React, { useState, useEffect } from 'react';
import { Check, X, Sparkles, Filter, RefreshCw, CheckCheck, BookOpen, Layers } from 'lucide-react';
import { useI18n } from '../../../i18n/I18nContext';

interface SourceCitation {
  id: number;
  book_id: string;
  book_title: string;
  volume?: number;
  pages: number[];
}

interface StagingItem {
  id: number;
  term: str;
  transliteration?: str;
  definition?: str;
  originalDefinition?: str;
  category: str;
  significanceScore: number;
  significanceReason?: str;
  isAiGenerated: boolean;
  entryType: 'new' | 'enrichment';
  existingDictionaryId?: number;
  sources: SourceCitation[];
  status: 'pending' | 'approved' | 'rejected';
  createdAt: str;
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

  const fetchQueue = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams({
        status: statusFilter,
        minSignificance: minScore.toString(),
        page: '1',
        pageSize: '50',
      });
      const res = await fetch(`/api/v1/admin/history-dictionary/staging?${query}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
        setTotal(data.total || 0);
      }
    } catch (e) {
      console.error('Failed to load staging queue', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchQueue();
  }, [statusFilter, minScore]);

  const handleApprove = async (id: number) => {
    setProcessingId(id);
    try {
      const res = await fetch(`/api/v1/admin/history-dictionary/staging/${id}/approve`, {
        method: 'POST',
      });
      if (res.ok) {
        setItems((prev) => prev.filter((item) => item.id !== id));
        setTotal((prev) => prev - 1);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id: number) => {
    setProcessingId(id);
    try {
      const res = await fetch(`/api/v1/admin/history-dictionary/staging/${id}`, {
        method: 'DELETE',
      });
      if (res.ok) {
        setItems((prev) => prev.filter((item) => item.id !== id));
        setTotal((prev) => prev - 1);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  };

  const handleBulkApprove = async () => {
    if (!selectedIds.length) return;
    try {
      const res = await fetch('/api/v1/admin/history-dictionary/staging/bulk-approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ staging_ids: selectedIds }),
      });
      if (res.ok) {
        setSelectedIds([]);
        fetchQueue();
      }
    } catch (e) {
      console.error(e);
    }
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  return (
    <div className="space-y-6" dir="rtl" lang="ug">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white dark:bg-slate-900 p-4 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
            <Sparkles className="text-amber-500" size={22} />
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

          <div className="flex items-center gap-2 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700">
            <Filter size={14} className="text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-transparent text-xs text-slate-700 dark:text-slate-300 font-medium focus:outline-none"
            >
              <option value="pending">{t('admin.statusPending') || 'تەستىقلانمىغان'}</option>
              <option value="approved">{t('admin.statusApproved') || 'تەستىقلانغان'}</option>
              <option value="rejected">{t('admin.statusRejected') || 'رەت قىلىنغان'}</option>
            </select>
          </div>

          <button
            onClick={fetchQueue}
            className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-xl transition-all"
            title={t('common.refresh') || 'قايتا يۈكلەش'}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Queue List */}
      {loading ? (
        <div className="text-center py-16 text-slate-500">
          <RefreshCw className="animate-spin mx-auto mb-3" size={24} />
          <span>{t('common.loading') || 'يۈكلىنىۋاتىدۇ...'}</span>
        </div>
      ) : items.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-12 text-center text-slate-500">
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
                  isSelected ? 'border-sky-500 ring-2 ring-sky-500/20' : 'border-slate-200 dark:border-slate-800'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(item.id)}
                      className="mt-1.5 h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500"
                    />
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{item.term}</h3>
                        {item.transliteration && (
                          <span className="text-xs text-slate-400 dir-ltr font-mono">({item.transliteration})</span>
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
                              : 'bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300'
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
                    <button
                      onClick={() => handleApprove(item.id)}
                      disabled={isProcessing}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition-all shadow-sm active:scale-95"
                    >
                      <Check size={14} />
                      <span>{t('admin.approve') || 'تەستىقلاش'}</span>
                    </button>
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

                {/* Definition view / Enrichment diff view */}
                <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/60">
                  {isEnrichment && item.originalDefinition ? (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                      <div className="bg-slate-50 dark:bg-slate-800/40 p-3 rounded-xl border border-slate-200/80 dark:border-slate-800">
                        <span className="font-bold text-slate-500 block mb-1">
                          {t('admin.originalDefinition') || 'مەۋجۇت بايان (شۇ پېتى)'}:
                        </span>
                        <p className="text-slate-700 dark:text-slate-300 leading-relaxed">{item.originalDefinition}</p>
                      </div>
                      <div className="bg-purple-50/50 dark:bg-purple-950/20 p-3 rounded-xl border border-purple-200/60 dark:border-purple-900/40">
                        <span className="font-bold text-purple-700 dark:text-purple-300 block mb-1">
                          {t('admin.enrichedDefinition') || 'يېڭى بېيىتىلغان بايان'}:
                        </span>
                        <p className="text-slate-800 dark:text-slate-200 leading-relaxed">{item.definition}</p>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed">{item.definition}</p>
                  )}
                </div>

                {/* Multi-book Fact Sources & Citations */}
                {item.sources && item.sources.length > 0 && (
                  <div className="mt-3 flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400 flex-wrap">
                    <span className="font-bold flex items-center gap-1">
                      <BookOpen size={13} className="text-sky-500" />
                      {t('admin.sources') || 'پاكىت مەنبەلىرى'}:
                    </span>
                    {item.sources.map((src) => (
                      <span key={src.id} className="bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-slate-600 dark:text-slate-300">
                        [{src.id}] «{src.book_title}» {src.volume ? `${src.volume}-جىلد` : ''} ({src.pages.join(', ')}-بەت)
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
