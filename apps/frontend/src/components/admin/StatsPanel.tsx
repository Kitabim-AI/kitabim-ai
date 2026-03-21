import React, { useState, useEffect } from 'react';
import { Book, FileText, CheckCircle, XCircle, RefreshCw, BarChart3, Clock, AlertTriangle, Loader, Zap, Hash } from 'lucide-react';
import { authFetch } from '../../services/authService';
import { useI18n } from '../../i18n/I18nContext';
import { ProverbDisplay } from '../common/ProverbDisplay';

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

// ---- Styling helpers ----
const STATUS_STYLES: Record<string, { bg: string; border: string; text: string; bar: string }> = {
  ready: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', bar: 'bg-green-500' },
  ocr: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  chunking: { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', bar: 'bg-indigo-500' },
  embedding: { bg: 'bg-orange-50', border: 'border-orange-100', text: 'text-orange-600', bar: 'bg-orange-500' },
  'ocr:idle': { bg: 'bg-blue-50', border: 'border-blue-100', text: 'text-blue-600', bar: 'bg-blue-400' },
  'ocr:running': { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  'ocr:in_progress': { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  'ocr:succeeded': { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-800', bar: 'bg-blue-600' },
  'chunking:idle': { bg: 'bg-indigo-50', border: 'border-indigo-100', text: 'text-indigo-600', bar: 'bg-indigo-400' },
  'chunking:running': { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', bar: 'bg-indigo-500' },
  'chunking:in_progress': { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-700', bar: 'bg-indigo-500' },
  'chunking:succeeded': { bg: 'bg-indigo-50', border: 'border-indigo-200', text: 'text-indigo-800', bar: 'bg-indigo-600' },
  'embedding:idle': { bg: 'bg-orange-50', border: 'border-orange-100', text: 'text-orange-600', bar: 'bg-orange-400' },
  'embedding:running': { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', bar: 'bg-orange-500' },
  'embedding:in_progress': { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', bar: 'bg-orange-500' },
  'embedding:succeeded': { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', bar: 'bg-emerald-500' },
  failed: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', bar: 'bg-red-500' },
  error: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', bar: 'bg-red-500' },
  pending: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700', bar: 'bg-yellow-500' },
};

const DEFAULT_STYLE = { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-700', bar: 'bg-slate-400' };

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
    <div className={`p-4 ${s.bg} border-2 ${s.border} rounded-xl`}>
      <div className={`flex items-center justify-between ${showBar ? 'mb-2' : ''}`}>
        <span className={`flex items-center gap-1.5 text-sm font-medium ${s.text}`}>
          <StatusIcon status={status} />
          {label}
        </span>
        <span className={`text-2xl font-bold ${s.text}`}>{count.toLocaleString()}</span>
      </div>
      {showBar && (
        <>
          <div className="w-full bg-white/60 rounded-full h-1.5 overflow-hidden">
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
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [llmState, setLlmState] = useState<string | null>(null);

  const loadStats = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await authFetch('/api/stats/');
      if (!response.ok) throw new Error(`Error ${response.status}: ${await response.text()}`);
      setStats(await response.json());
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
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center animate-pulse">
          <BarChart3 className="w-16 h-16 text-[#0369a1] mb-6 animate-bounce" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
          <div className="p-4 bg-red-50 text-red-500 rounded-3xl mb-6"><XCircle size={48} /></div>
          <h3 className="text-xl font-normal text-[#1a1a1a] mb-2">{t('admin.stats.loadError') || 'Failed to load statistics'}</h3>
          <p className="text-[#94a3b8] font-normal mb-6">{error}</p>
          <button onClick={loadStats} className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg">
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
    failed: t('bookCard.pipeline.failed'),
    error: t('common.error'),
  };

  return (
    <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-4 group">
          <div className="self-start mt-1 p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 icon-shake">
            <BarChart3 size={20} className="md:w-6 md:h-6" />
          </div>
          <div>
            <h2 className="text-xl md:text-2xl lg:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.stats.title') || 'System Statistics'}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <ProverbDisplay
                keywords={t('proverbs.admin')}
                size="sm"
                className="opacity-70 mt-[-2px]"
                defaultText={t('admin.stats.subtitle') || 'View system analytics and metrics'}
              />
            </div>
          </div>
        </div>
        {/* Right side: LLM chip + Refresh button */}
        <div className="flex items-center gap-3 self-end md:self-auto">
          {/* LLM Status Chip — leftmost */}
          {llmState && (
            <div
              className={`flex items-center gap-2 px-4 py-2 rounded-xl border-2 text-sm font-medium transition-all shadow-sm ${llmState === 'closed'
                ? 'bg-green-50 border-green-200 text-green-700'
                : llmState === 'open' ? 'bg-red-50 border-red-200 text-red-700' : 'bg-yellow-50 border-yellow-200 text-yellow-700'
                }`}
            >
              <Zap size={14} className={llmState === 'closed' ? 'fill-green-500 text-green-500' : llmState === 'open' ? 'text-red-500' : 'fill-yellow-500 text-yellow-500'} />
              {llmState === 'closed'
                ? (t('admin.stats.llmAvailable') || 'LLM Available')
                : llmState === 'open' ? (t('admin.stats.llmUnavailable') || 'LLM Unavailable') : t('admin.systemConfig.circuitBreaker.states.half_open')}
            </div>
          )}

          {/* Refresh button — rightmost */}
          <button
            onClick={() => { loadStats(); loadLlmStatus(); }}
            className="flex items-center gap-2 px-4 py-2 bg-white text-[#0369a1] rounded-xl border border-[#0369a1]/20 hover:border-[#0369a1] transition-all shadow-sm"
          >
            <RefreshCw size={16} />
            <span className="text-sm font-normal">{t('common.refresh') || 'Refresh'}</span>
          </button>
        </div>

      </div>

      {/* Stat Blocks */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">

        {/* ── Books ── */}
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <Book size={16} className="text-[#0369a1]" />
              <h4 className="text-base font-semibold text-[#0369a1] uppercase tracking-wide">
                {t('admin.stats.booksByStatus') || 'Books by Status'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600">{t('admin.stats.totalBooks') || 'Total Books'}</span>
                <span className="text-2xl font-bold text-slate-800">{stats.total_books.toLocaleString()}</span>
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
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <FileText size={16} className="text-[#0369a1]" />
              <h4 className="text-base font-semibold text-[#0369a1] uppercase tracking-wide">
                {t('admin.stats.pageStats') || 'Page Statistics'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600">{t('admin.stats.totalPages') || 'Total Pages'}</span>
                <span className="text-2xl font-bold text-slate-800">{stats.page_stats.total.toLocaleString()}</span>
              </div>
            </div>

            {/* Indexed */}
            <div className="p-4 bg-green-50 border-2 border-green-200 rounded-xl">
              <div className="flex items-center justify-between mb-2">
                <span className="flex items-center gap-1.5 text-sm font-medium text-green-700">
                  <CheckCircle size={14} />
                  {t('admin.stats.indexedPages') || 'Indexed Pages'}
                </span>
                <span className="text-2xl font-bold text-green-700">{stats.page_stats.indexed.toLocaleString()}</span>
              </div>
              <div className="w-full bg-white/60 rounded-full h-1.5 overflow-hidden">
                <div className="bg-green-500 h-full rounded-full transition-all duration-700" style={{ width: `${stats.page_stats.percentage_indexed}%` }} />
              </div>
              <div className="text-xs text-green-700 mt-1 text-right opacity-75">{stats.page_stats.percentage_indexed.toFixed(1)}%</div>
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
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <Hash size={16} className="text-[#0369a1]" />
              <h4 className="text-base font-semibold text-[#0369a1] uppercase tracking-wide">
                {t('admin.stats.chunkStats') || 'Chunk Statistics'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600">{t('admin.stats.totalChunks') || 'Total Chunks'}</span>
                <span className="text-2xl font-bold text-slate-800">{stats.chunk_stats.total.toLocaleString()}</span>
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
      </div>
    </div>
  );
};

export default StatsPanel;
