import React, { useState, useEffect } from 'react';
import { Book, FileText, CheckCircle, XCircle, RefreshCw, BarChart3, Clock, AlertTriangle, Loader, Zap } from 'lucide-react';
import { authFetch } from '../../services/authService';
import { useI18n } from '../../i18n/I18nContext';

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

interface SystemStats {
  total_books: number;
  books_by_status: StatusCount[];
  page_stats: PageStats;
  jobs_by_status: StatusCount[];
  jobs_by_type: StatusCount[];
}

// ---- Styling helpers ----
const STATUS_STYLES: Record<string, { bg: string; border: string; text: string; bar: string }> = {
  ready: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', bar: 'bg-green-500' },
  completed: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', bar: 'bg-green-500' },
  succeeded: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', bar: 'bg-green-500' },
  indexed: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-700', bar: 'bg-green-500' },
  processing: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  running: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  queued: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-700', bar: 'bg-blue-500' },
  pending: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700', bar: 'bg-yellow-500' },
  skipped: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-700', bar: 'bg-yellow-500' },
  retrying: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', bar: 'bg-orange-500' },
  error: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', bar: 'bg-red-500' },
  failed: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-700', bar: 'bg-red-500' },
  unindexed: { bg: 'bg-orange-50', border: 'border-orange-200', text: 'text-orange-700', bar: 'bg-orange-500' },
};

const DEFAULT_STYLE = { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-700', bar: 'bg-slate-400' };

function getStyle(status: string) {
  return STATUS_STYLES[status.toLowerCase()] ?? DEFAULT_STYLE;
}

function StatusIcon({ status }: { status: string }) {
  switch (status.toLowerCase()) {
    case 'ready':
    case 'completed':
    case 'succeeded':
      return <CheckCircle size={14} />;
    case 'processing':
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
  const [llmAvailable, setLlmAvailable] = useState<boolean | null>(null);

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
      setLlmAvailable(data.overall_available ?? null);
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
    ready: t('admin.stats.ready') || 'Ready',
    completed: t('admin.stats.completed') || 'Completed',
    processing: t('admin.stats.bookProcessing') || 'Processing',
    error: t('admin.stats.error') || 'Error',
    pending: t('admin.stats.bookPending') || 'Pending',
  };

  const pageStatusLabel: Record<string, string> = {
    completed: t('admin.stats.indexedPages') || 'Completed',
    error: t('admin.stats.errorPages') || 'Error',
    processing: t('admin.stats.pageProcessing') || 'Processing',
    pending: t('admin.stats.pagePending') || 'Pending',
  };

  const jobStatusLabel: Record<string, string> = {
    succeeded: t('admin.stats.jobSucceeded') || 'Succeeded',
    failed: t('admin.stats.jobFailed') || 'Failed',
    skipped: t('admin.stats.jobSkipped') || 'Skipped',
    queued: t('admin.stats.jobQueued') || 'Queued',
    retrying: t('admin.stats.jobRetrying') || 'Retrying',
    running: t('admin.stats.jobRunning') || 'Running',
  };

  const totalJobs = (stats.jobs_by_status || []).reduce((acc, j) => acc + j.count, 0);

  return (
    <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-4 group">
          <div className="p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
            <BarChart3 size={24} />
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.stats.title') || 'System Statistics'}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <p className="text-[12px] md:text-[14px] font-normal text-[#94a3b8]">
                {t('admin.stats.subtitle') || 'View system analytics and metrics'}
              </p>
            </div>
          </div>
        </div>
        {/* Right side: LLM chip + Refresh button */}
        <div className="flex items-center gap-3 self-end md:self-auto">
          {/* LLM Status Chip — leftmost */}
          {llmAvailable !== null && (
            <div
              className={`flex items-center gap-2 px-4 py-2 rounded-xl border-2 text-sm font-medium transition-all shadow-sm ${llmAvailable
                ? 'bg-green-50 border-green-200 text-green-700'
                : 'bg-red-50 border-red-200 text-red-700'
                }`}
            >
              <Zap size={14} className={llmAvailable ? 'fill-green-500 text-green-500' : 'text-red-500'} />
              {llmAvailable
                ? (t('admin.stats.llmAvailable') || 'LLM Available')
                : (t('admin.stats.llmUnavailable') || 'LLM Unavailable')}
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

            {/* Dynamic page status breakdown (excluding completed/indexed which is above) */}
            {(stats.page_stats.pages_by_status || [])
              .filter(({ status }) => status.toLowerCase() !== 'completed')
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

        {/* ── Jobs ── */}
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10">
          <div className="space-y-3">
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 size={16} className="text-[#0369a1]" />
              <h4 className="text-sm font-semibold text-[#0369a1] uppercase tracking-wide">
                {t('admin.stats.jobStats') || 'Job Statistics'}
              </h4>
            </div>

            {/* Total */}
            <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-slate-600">{t('admin.stats.totalJobs') || 'Total Jobs'}</span>
                <span className="text-2xl font-bold text-slate-800">{totalJobs.toLocaleString()}</span>
              </div>
            </div>

            {/* Dynamic breakdown */}
            {(stats.jobs_by_status || []).map(({ status, count }) => (
              <StatCard
                key={status}
                label={jobStatusLabel[status.toLowerCase()] || status}
                count={count}
                total={totalJobs}
                status={status}
                showBar
              />
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};

export default StatsPanel;
