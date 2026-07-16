import { AlertTriangle, BarChart3, Book, CheckCircle, Clock, FileText, Hash, Loader, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { authFetch } from '../../services/authService';


interface StatusCount {
  status: string;
  count: number;
}

interface PageStats {
  total: number;
  indexed: number;
  unindexed: number;
  percentage_indexed: number;
  error: number;
  pages_by_status: StatusCount[];
}

interface ChunkStats {
  total: number;
  embedded: number;
  pending: number;
  percentage_embedded: number;
}

interface SystemStats {
  total_books: number;
  books_by_status: StatusCount[];
  page_stats: PageStats;
  chunk_stats: ChunkStats;
}

interface RAGQualityStats {
  total_evaluations: number;
  graded_evaluations: number;
  avg_faithfulness: number | null;
  avg_answer_relevance: number | null;
}

// ---- Styling helpers ----
const STATUS_STYLES: Record<string, { bg: string; border: string; text: string; bar: string }> = {
  ready: { bg: 'bg-green-50 dark:bg-emerald-950/20', border: 'border-green-200 dark:border-emerald-900/30', text: 'text-green-700 dark:text-emerald-400', bar: 'bg-green-500 dark:bg-emerald-500' },
  ocr: { bg: 'bg-blue-50 dark:bg-blue-950/20', border: 'border-blue-200 dark:border-blue-900/30', text: 'text-blue-700 dark:text-blue-400', bar: 'bg-blue-500 dark:bg-blue-500' },
  chunking: { bg: 'bg-indigo-55/60 dark:bg-indigo-950/20', border: 'border-indigo-200 dark:border-indigo-900/30', text: 'text-indigo-700 dark:text-indigo-400', bar: 'bg-indigo-500 dark:bg-indigo-500' },
  embedding: { bg: 'bg-orange-50 dark:bg-orange-950/20', border: 'border-orange-100 dark:border-orange-900/30', text: 'text-orange-600 dark:text-orange-400', bar: 'bg-orange-500 dark:bg-orange-500' },
  'ocr:idle': { bg: 'bg-blue-50 dark:bg-blue-950/20', border: 'border-blue-100 dark:border-blue-900/30', text: 'text-blue-600 dark:text-blue-400', bar: 'bg-blue-400 dark:bg-blue-500' },
  'ocr:running': { bg: 'bg-blue-50 dark:bg-blue-950/20', border: 'border-blue-200 dark:border-blue-900/30', text: 'text-blue-700 dark:text-blue-400', bar: 'bg-blue-500 dark:bg-blue-500' },
  'ocr:in_progress': { bg: 'bg-blue-50 dark:bg-blue-950/20', border: 'border-blue-200 dark:border-blue-900/30', text: 'text-blue-700 dark:text-blue-400', bar: 'bg-blue-500 dark:bg-blue-500' },
  'ocr:succeeded': { bg: 'bg-blue-50 dark:bg-blue-950/20', border: 'border-blue-200 dark:border-blue-900/30', text: 'text-blue-850 dark:text-blue-400', bar: 'bg-blue-605 dark:bg-blue-600' },
  'chunking:idle': { bg: 'bg-indigo-50 dark:bg-indigo-950/20', border: 'border-indigo-100 dark:border-indigo-900/30', text: 'text-indigo-600 dark:text-indigo-400', bar: 'bg-indigo-400 dark:bg-indigo-500' },
  'chunking:running': { bg: 'bg-indigo-50 dark:bg-indigo-950/20', border: 'border-indigo-200 dark:border-indigo-900/30', text: 'text-indigo-700 dark:text-indigo-400', bar: 'bg-indigo-500 dark:bg-indigo-500' },
  'chunking:in_progress': { bg: 'bg-indigo-50 dark:bg-indigo-950/20', border: 'border-indigo-200 dark:border-indigo-900/30', text: 'text-indigo-700 dark:text-indigo-400', bar: 'bg-indigo-500 dark:bg-indigo-500' },
  'chunking:succeeded': { bg: 'bg-indigo-50 dark:bg-indigo-950/20', border: 'border-indigo-200 dark:border-indigo-900/30', text: 'text-indigo-805 dark:text-indigo-400', bar: 'bg-indigo-605 dark:bg-indigo-600' },
  'embedding:idle': { bg: 'bg-orange-50 dark:bg-orange-950/20', border: 'border-orange-100 dark:border-orange-900/30', text: 'text-orange-600 dark:text-orange-400', bar: 'bg-orange-405 dark:bg-orange-500' },
  'embedding:running': { bg: 'bg-orange-50 dark:bg-orange-950/20', border: 'border-orange-200 dark:border-orange-900/30', text: 'text-orange-700 dark:text-orange-400', bar: 'bg-orange-505 dark:bg-orange-500' },
  'embedding:in_progress': { bg: 'bg-orange-50 dark:bg-orange-950/20', border: 'border-orange-200 dark:border-orange-900/30', text: 'text-orange-700 dark:text-orange-400', bar: 'bg-orange-505 dark:bg-orange-500' },
  'embedding:succeeded': { bg: 'bg-emerald-50 dark:bg-emerald-950/20', border: 'border-emerald-200 dark:border-emerald-900/30', text: 'text-emerald-700 dark:text-emerald-400', bar: 'bg-emerald-500 dark:bg-emerald-500' },
  'spell_check:idle': { bg: 'bg-purple-50 dark:bg-purple-950/20', border: 'border-purple-100 dark:border-purple-900/30', text: 'text-purple-600 dark:text-purple-400', bar: 'bg-purple-405 dark:bg-purple-500' },
  'spell_check:running': { bg: 'bg-purple-50 dark:bg-purple-950/20', border: 'border-purple-200 dark:border-purple-900/30', text: 'text-purple-700 dark:text-purple-400', bar: 'bg-purple-505 dark:bg-purple-500' },
  'spell_check:in_progress': { bg: 'bg-purple-55 dark:bg-purple-955/20', border: 'border-purple-205 dark:border-purple-905/30', text: 'text-purple-705 dark:text-purple-405', bar: 'bg-purple-505 dark:bg-purple-500' },
  'spell_check:succeeded': { bg: 'bg-purple-50 dark:bg-purple-950/20', border: 'border-purple-200 dark:border-purple-900/30', text: 'text-purple-800 dark:text-purple-400', bar: 'bg-purple-605 dark:bg-purple-600' },
  'spell_check:done': { bg: 'bg-purple-50 dark:bg-purple-950/20', border: 'border-purple-200 dark:border-purple-900/30', text: 'text-purple-800 dark:text-purple-400', bar: 'bg-purple-600 dark:bg-purple-600' },
  spell_check: { bg: 'bg-purple-50 dark:bg-purple-950/20', border: 'border-purple-200 dark:border-purple-900/30', text: 'text-purple-700 dark:text-purple-400', bar: 'bg-purple-500 dark:bg-purple-500' },
  'ocr:failed': { bg: 'bg-red-50 dark:bg-red-950/20', border: 'border-red-200 dark:border-red-900/30', text: 'text-red-700 dark:text-red-400', bar: 'bg-red-500 dark:bg-red-500' },
  'chunking:failed': { bg: 'bg-red-50 dark:bg-red-950/20', border: 'border-red-200 dark:border-red-900/30', text: 'text-red-700 dark:text-red-400', bar: 'bg-red-500 dark:bg-red-500' },
  'embedding:failed': { bg: 'bg-red-50 dark:bg-red-950/20', border: 'border-red-200 dark:border-red-900/30', text: 'text-red-700 dark:text-red-400', bar: 'bg-red-500 dark:bg-red-500' },
  'spell_check:failed': { bg: 'bg-red-50 dark:bg-red-950/20', border: 'border-red-200 dark:border-red-900/30', text: 'text-red-700 dark:text-red-400', bar: 'bg-red-500 dark:bg-red-500' },
  failed: { bg: 'bg-red-50 dark:bg-red-950/20', border: 'border-red-200 dark:border-red-900/30', text: 'text-red-700 dark:text-red-400', bar: 'bg-red-500 dark:bg-red-500' },
  error: { bg: 'bg-red-50 dark:bg-red-950/20', border: 'border-red-200 dark:border-red-900/30', text: 'text-red-700 dark:text-red-400', bar: 'bg-red-500 dark:bg-red-500' },
  pending: { bg: 'bg-yellow-50 dark:bg-yellow-950/20', border: 'border-yellow-200 dark:border-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', bar: 'bg-yellow-500 dark:bg-yellow-500' },
};

const DEFAULT_STYLE = { bg: 'bg-slate-50 dark:bg-slate-900/40', border: 'border-slate-200 dark:border-slate-800', text: 'text-slate-700 dark:text-slate-300', bar: 'bg-slate-400 dark:bg-slate-500' };

function getStyle(status: string) {
  return STATUS_STYLES[status.toLowerCase()] ?? DEFAULT_STYLE;
}

function StatusIcon({ status }: { status: string }) {
  switch (status.toLowerCase()) {
    case 'ready':
    case 'ocr_done':
    case 'succeeded':
      return <CheckCircle size={14} />;
    case 'ocr_processing':
    case 'indexing':
    case 'running':
      return <Loader size={14} className="animate-spin" />;
    case 'retrying':
      return <RefreshCw size={14} className="animate-spin" />;
    case 'error':
    case 'failed':
      return <XCircle size={14} />;
    case 'pending':
    case 'queued':
    case 'skipped':
    case 'chunked':
      return <Clock size={14} />;
    default:
      return <AlertTriangle size={14} />;
  }
}

interface StatCardProps {
  key?: React.Key;
  label: string;
  count: number;
  total: number;
  status: string;
  showBar?: boolean;
}

function StatCard({ label, count, total, status, showBar }: StatCardProps) {
  const s = getStyle(status);
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div className={`p-4 ${s.bg} border-2 ${s.border} rounded-xl shadow-sm`}>
      <div className={`flex items-center justify-between ${showBar ? 'mb-2' : ''}`}>
        <span className={`flex items-center gap-1.5 text-sm font-medium ${s.text}`}>
          <StatusIcon status={status} />
          {label}
        </span>
        <span className={`text-2xl font-bold ${s.text}`}>{count.toLocaleString()}</span>
      </div>
      {showBar && (
        <>
          <div className="w-full bg-white/60 dark:bg-slate-955/20 rounded-full h-1.5 overflow-hidden">
            <div className={`${s.bar} h-full rounded-full transition-all duration-700`} style={{ width: `${pct}%` }} />
          </div>
          <div className={`text-xs ${s.text} mt-1 text-right opacity-75`}>{pct.toFixed(1)}%</div>
        </>
      )}
    </div>
  );
}

// ---- Component ----
export const StatsPanel: React.FC = () => {
  const { t } = useI18n();
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [ragQuality, setRagQuality] = useState<RAGQualityStats | null>(null);
  const [ragQualityError, setRagQualityError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [llmState, setLlmState] = useState<string | null>(null);

  const loadStats = async () => {
    try {
      setIsLoading(true);
      setError(null);
      setRagQualityError(null);
      const [statsRes, ragRes] = await Promise.all([
        authFetch('/api/stats/'),
        authFetch('/api/stats/rag'),
      ]);
      if (!statsRes.ok) throw new Error(`Error ${statsRes.status}: ${await statsRes.text()}`);
      setStats(await statsRes.json());
      if (ragRes.ok) {
        setRagQuality(await ragRes.json());
      } else {
        setRagQualityError(t('admin.stats.ragStatsUnavailable', { status: ragRes.status }));
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load statistics');
    } finally {
      setIsLoading(false);
    }
  };

  const loadLlmStatus = async () => {
    try {
      const res = await authFetch('/api/system-configs/circuit-breaker/status');
      if (!res.ok) return;
      const data = await res.json();
      setLlmState(data.overall_state || (data.overall_available ? 'closed' : 'open'));
    } catch {
      // silently ignore — editors may not have access
    }
  };

  useEffect(() => {
    loadStats();
    loadLlmStatus();
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
        <div className="glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-20 flex flex-col items-center justify-center text-center animate-pulse shadow-xl rounded-[24px]">
          <BarChart3 className="w-16 h-16 text-[#0369a1] dark:text-[#38bdf8] mb-6 animate-bounce" />
          <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('common.loading')}</h3>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
        <div className="glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-20 flex flex-col items-center justify-center text-center shadow-xl rounded-[24px]">
          <div className="p-4 bg-red-50 dark:bg-red-955/20 text-red-555 rounded-3xl mb-6"><XCircle size={48} className="text-red-500" /></div>
          <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100 mb-2">{t('admin.stats.loadError') || 'Failed to load statistics'}</h3>
          <p className="text-[#94a3b8] dark:text-slate-400 font-normal mb-6">{error}</p>
          <button onClick={loadStats} className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0369a1]/90 dark:hover:bg-[#38bdf8]/90 transition-all shadow-lg">
            <RefreshCw size={18} />
            <span className="text-sm font-normal uppercase">{t('common.refresh') || 'Retry'}</span>
          </button>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  // Label maps
  const bookStatusLabel: Record<string, string> = {
    ready: t('common.done'),
    ocr: t('admin.pipeline.ocr'),
    chunking: t('bookCard.pipeline.chunking'),
    embedding: t('admin.pipeline.embedding'),
    error: t('common.error'),
    pending: t('common.pending'),
  };

  const pageStatusLabel: Record<string, string> = {
    'ocr:idle': `OCR: ${t('bookCard.pipeline.idle')}`,
    'ocr:running': `OCR: ${t('bookCard.pipeline.running')}`,
    'ocr:in_progress': `OCR: ${t('bookCard.pipeline.in_progress')}`,
    'ocr:succeeded': `OCR: ${t('bookCard.pipeline.succeeded')}`,
    'chunking:idle': `${t('bookCard.pipeline.chunking')}: ${t('bookCard.pipeline.idle')}`,
    'chunking:running': `${t('bookCard.pipeline.chunking')}: ${t('bookCard.pipeline.running')}`,
    'chunking:in_progress': `${t('bookCard.pipeline.chunking')}: ${t('bookCard.pipeline.in_progress')}`,
    'chunking:succeeded': `${t('bookCard.pipeline.chunking')}: ${t('bookCard.pipeline.succeeded')}`,
    'embedding:idle': `${t('bookCard.pipeline.embedding')}: ${t('bookCard.pipeline.idle')}`,
    'embedding:running': `${t('bookCard.pipeline.embedding')}: ${t('bookCard.pipeline.running')}`,
    'embedding:in_progress': `${t('bookCard.pipeline.embedding')}: ${t('bookCard.pipeline.in_progress')}`,
    'embedding:succeeded': `${t('bookCard.pipeline.embedding')}: ${t('bookCard.pipeline.succeeded')}`,
    'spell_check:idle': `${t('bookCard.pipeline.spell_check')}: ${t('bookCard.pipeline.idle')}`,
    'spell_check:running': `${t('bookCard.pipeline.spell_check')}: ${t('bookCard.pipeline.running')}`,
    'spell_check:in_progress': `${t('bookCard.pipeline.spell_check')}: ${t('bookCard.pipeline.in_progress')}`,
    'spell_check:succeeded': `${t('bookCard.pipeline.spell_check')}: ${t('bookCard.pipeline.succeeded')}`,
    'spell_check:done': `${t('bookCard.pipeline.spell_check')}: ${t('common.done')}`,
    'ocr:failed': `OCR: ${t('bookCard.pipeline.failed')}`,
    'chunking:failed': `${t('bookCard.pipeline.chunking')}: ${t('bookCard.pipeline.failed')}`,
    'embedding:failed': `${t('bookCard.pipeline.embedding')}: ${t('bookCard.pipeline.failed')}`,
    'spell_check:failed': `${t('bookCard.pipeline.spell_check')}: ${t('bookCard.pipeline.failed')}`,
    failed: t('bookCard.pipeline.failed'),
    error: t('common.error'),
  };

  return (
    <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Header */}


      {/* Stat Blocks */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">

        {/* ── Books ── */}
        <div className="glass-panel dark:bg-slate-900/60 overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <Book size={16} className="text-[#0369a1] dark:text-[#38bdf8]" />
              <h4 className="text-base font-semibold text-[#0369a1] dark:text-[#38bdf8] uppercase tracking-wide">
                {t('admin.stats.booksByStatus') || 'Books by Status'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border-2 border-slate-200 dark:border-slate-800 rounded-xl shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600 dark:text-slate-400">{t('admin.stats.totalBooks') || 'Total Books'}</span>
                <span className="text-2xl font-bold text-slate-800 dark:text-slate-250">{stats.total_books.toLocaleString()}</span>
              </div>
            </div>

            {/* Dynamic breakdown */}
            {(stats.books_by_status || []).map(({ status, count }) => (
              <StatCard
                key={status}
                label={bookStatusLabel[status.toLowerCase()] || status}
                count={count}
                total={stats.total_books}
                status={status}
                showBar
              />
            ))}
          </div>
        </div>

        {/* ── Pages ── */}
        <div className="glass-panel dark:bg-slate-900/60 overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <FileText size={16} className="text-[#0369a1] dark:text-[#38bdf8]" />
              <h4 className="text-base font-semibold text-[#0369a1] dark:text-[#38bdf8] uppercase tracking-wide">
                {t('admin.stats.pageStats') || 'Page Statistics'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border-2 border-slate-200 dark:border-slate-800 rounded-xl shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600 dark:text-slate-400">{t('admin.stats.totalPages') || 'Total Pages'}</span>
                <span className="text-2xl font-bold text-slate-800 dark:text-slate-250">{stats.page_stats.total.toLocaleString()}</span>
              </div>
            </div>

            {/* Indexed */}
            <div className="p-4 bg-green-50 dark:bg-emerald-950/20 border-2 border-green-200 dark:border-emerald-900/30 rounded-xl shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="flex items-center gap-1.5 text-sm font-medium text-green-700 dark:text-emerald-450">
                  <CheckCircle size={14} />
                  {t('admin.stats.indexedPages') || 'Indexed Pages'}
                </span>
                <span className="text-2xl font-bold text-green-700 dark:text-emerald-400">{stats.page_stats.indexed.toLocaleString()}</span>
              </div>
              <div className="w-full bg-white/60 dark:bg-slate-955/20 rounded-full h-1.5 overflow-hidden">
                <div className="bg-green-500 dark:bg-emerald-500 h-full rounded-full transition-all duration-700" style={{ width: `${stats.page_stats.percentage_indexed}%` }} />
              </div>
              <div className="text-xs text-green-700 dark:text-emerald-405 mt-1 text-right opacity-75">{stats.page_stats.percentage_indexed.toFixed(1)}%</div>
            </div>

            {/* Dynamic page status breakdown (excluding ocr_done/indexed which is above) */}
            {(stats.page_stats.pages_by_status || [])
              .filter(({ status }) => status.toLowerCase() !== 'indexed')
              .map(({ status, count }) => (
                <StatCard
                  key={status}
                  label={pageStatusLabel[status.toLowerCase()] || status}
                  count={count}
                  total={stats.page_stats.total}
                  status={status}
                  showBar
                />
              ))}
          </div>
        </div>

        {/* ── Chunks ── */}
        <div className="glass-panel dark:bg-slate-900/60 overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <Hash size={16} className="text-[#0369a1] dark:text-[#38bdf8]" />
              <h4 className="text-base font-semibold text-[#0369a1] dark:text-[#38bdf8] uppercase tracking-wide">
                {t('admin.stats.chunkStats') || 'Chunk Statistics'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border-2 border-slate-200 dark:border-slate-800 rounded-xl shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600 dark:text-slate-400">{t('admin.stats.totalChunks') || 'Total Chunks'}</span>
                <span className="text-2xl font-bold text-slate-800 dark:text-slate-250">{stats.chunk_stats.total.toLocaleString()}</span>
              </div>
            </div>

            {/* Embedded */}
            <StatCard
              label={t('admin.stats.embeddedChunks') || 'Embedded Chunks'}
              count={stats.chunk_stats.embedded}
              total={stats.chunk_stats.total}
              status="ready"
              showBar
            />

            {/* Pending */}
            <StatCard
              label={t('admin.stats.pendingChunks') || 'Pending Chunks'}
              count={stats.chunk_stats.pending}
              total={stats.chunk_stats.total}
              status="pending"
            />
          </div>
        </div>

        {/* ── RAG Quality & Feedback ── */}
        <div className="glass-panel dark:bg-slate-900/60 overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <ShieldCheck size={16} className="text-[#0369a1] dark:text-[#38bdf8]" />
              <h4 className="text-base font-semibold text-[#0369a1] dark:text-[#38bdf8] uppercase tracking-wide">
                {t('admin.stats.ragQualityTitle') || 'RAG Quality & Feedback'}
              </h4>
            </div>

            {ragQualityError && (
              <div className="p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/30 rounded-xl">
                <p className="text-xs text-amber-700 dark:text-amber-400 font-medium">{ragQualityError}</p>
              </div>
            )}

            {/* Total evaluated */}
            <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border-2 border-slate-200 dark:border-slate-800 rounded-xl shadow-sm">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600 dark:text-slate-400">{t('admin.stats.totalQueries') || 'Total Queries'}</span>
                <span className="text-2xl font-bold text-slate-800 dark:text-slate-250">{(ragQuality?.total_evaluations ?? 0).toLocaleString()}</span>
              </div>
            </div>

            {/* Graded */}
            <div className="p-4 bg-indigo-50 dark:bg-indigo-950/20 border-2 border-indigo-200 dark:border-indigo-900/30 rounded-xl shadow-sm">
              <div className="flex items-center justify-between mb-2">
                <span className="flex items-center gap-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-400">
                  <CheckCircle size={14} />
                  {t('admin.stats.gradedEvaluations') || 'Feedback Submissions'}
                </span>
                <span className="text-2xl font-bold text-indigo-700 dark:text-indigo-400">{(ragQuality?.graded_evaluations ?? 0).toLocaleString()}</span>
              </div>
              <div className="w-full bg-white/60 dark:bg-slate-950/60 rounded-full h-1.5 overflow-hidden">
                <div
                  className="bg-indigo-500 dark:bg-indigo-500 h-full rounded-full transition-all duration-700"
                  style={{ width: `${ragQuality && ragQuality.total_evaluations > 0 ? (ragQuality.graded_evaluations / ragQuality.total_evaluations) * 100 : 0}%` }}
                />
              </div>
            </div>

            {/* Faithfulness */}
            {ragQuality?.avg_faithfulness != null ? (
              <div className="p-4 bg-emerald-50 dark:bg-emerald-950/20 border-2 border-emerald-200 dark:border-emerald-900/30 rounded-xl shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="flex items-center gap-1.5 text-sm font-medium text-emerald-700 dark:text-emerald-400">
                    <CheckCircle size={14} />
                    {t('admin.stats.avgFaithfulness') || 'Avg Faithfulness'}
                  </span>
                  <span className="text-2xl font-bold text-emerald-700 dark:text-emerald-450">{(ragQuality.avg_faithfulness * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full bg-white/60 dark:bg-slate-950/60 rounded-full h-1.5 overflow-hidden">
                  <div className="bg-emerald-500 dark:bg-emerald-500 h-full rounded-full transition-all duration-700" style={{ width: `${ragQuality.avg_faithfulness * 100}%` }} />
                </div>
              </div>
            ) : (
              <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl shadow-sm">
                <span className="text-sm text-slate-500 dark:text-slate-400">{t('admin.stats.avgFaithfulnessNoData') || 'Avg Faithfulness — no data yet'}</span>
              </div>
            )}

            {/* Answer Relevance */}
            {ragQuality?.avg_answer_relevance != null ? (
              <div className="p-4 bg-blue-50 dark:bg-blue-950/20 border-2 border-blue-200 dark:border-blue-900/30 rounded-xl shadow-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="flex items-center gap-1.5 text-sm font-medium text-blue-700 dark:text-blue-400">
                    <CheckCircle size={14} />
                    {t('admin.stats.avgAnswerRelevance') || 'Avg Answer Relevance'}
                  </span>
                  <span className="text-2xl font-bold text-blue-700 dark:text-emerald-450">{(ragQuality.avg_answer_relevance * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full bg-white/60 dark:bg-slate-950/60 rounded-full h-1.5 overflow-hidden">
                  <div className="bg-blue-500 dark:bg-blue-500 h-full rounded-full transition-all duration-700" style={{ width: `${ragQuality.avg_answer_relevance * 100}%` }} />
                </div>
              </div>
            ) : (
              <div className="p-4 bg-slate-50 dark:bg-slate-900/40 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl shadow-sm">
                <span className="text-sm text-slate-500 dark:text-slate-400">{t('admin.stats.avgAnswerRelevanceNoData') || 'Avg Answer Relevance — no data yet'}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StatsPanel;
