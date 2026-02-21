import React, { useState, useEffect } from 'react';
import { Book, FileText, CheckCircle, XCircle, RefreshCw, BarChart3 } from 'lucide-react';
import { authFetch } from '../../services/authService';
import { useI18n } from '../../i18n/I18nContext';

interface BookStatusCount {
  status: string;
  count: number;
}

interface PageStats {
  total: number;
  indexed: number;
  unindexed: number;
  percentage_indexed: number;
}

interface JobStatusCount {
  status: string;
  count: number;
}

interface JobTypeCount {
  type: string;
  count: number;
}

interface SystemStats {
  total_books: number;
  books_by_status: BookStatusCount[];
  page_stats: PageStats;
  jobs_by_status: JobStatusCount[];
  jobs_by_type: JobTypeCount[];
}

export const StatsPanel: React.FC = () => {
  const { t } = useI18n();
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStats = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await authFetch('/api/stats/');
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setStats(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load statistics');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStats();
  }, []);

  if (isLoading) {
    return (
      <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center animate-pulse">
          <BarChart3 className="w-16 h-16 text-[#0369a1] mb-6 animate-bounce" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
          <p className="text-slate-500 font-normal">{t('admin.stats.loading') || 'Loading statistics...'}</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
          <div className="p-4 bg-red-50 text-red-500 rounded-3xl mb-6">
            <XCircle size={48} />
          </div>
          <h3 className="text-xl font-normal text-[#1a1a1a] mb-2">
            {t('admin.stats.loadError') || 'Failed to load statistics'}
          </h3>
          <p className="text-[#94a3b8] font-normal mb-6">{error}</p>
          <button
            onClick={loadStats}
            className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg"
          >
            <RefreshCw size={18} />
            <span className="text-sm font-normal uppercase">{t('common.refresh') || 'Retry'}</span>
          </button>
        </div>
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'ready':
      case 'success':
      case 'succeeded':
      case 'completed':
        return 'bg-green-50 border-green-200 text-green-700';
      case 'processing':
      case 'running':
      case 'in_progress':
        return 'bg-blue-50 border-blue-200 text-blue-700';
      case 'pending':
      case 'queued':
      case 'deferred':
        return 'bg-yellow-50 border-yellow-200 text-yellow-700';
      case 'error':
      case 'failed':
        return 'bg-red-50 border-red-200 text-red-700';
      case 'aborted':
      case 'cancelled':
        return 'bg-slate-50 border-slate-200 text-slate-700';
      default:
        return 'bg-slate-50 border-slate-200 text-slate-700';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'ready':
      case 'success':
      case 'succeeded':
      case 'completed':
        return <CheckCircle size={16} />;
      case 'processing':
      case 'running':
      case 'in_progress':
        return <RefreshCw size={16} className="animate-spin" />;
      case 'error':
      case 'failed':
        return <XCircle size={16} />;
      default:
        return <Book size={16} />;
    }
  };

  const getStatusLabel = (status: string) => {
    const labels: Record<string, string> = {
      ready: t('admin.stats.ready') || 'Ready',
      completed: t('admin.stats.completed') || 'Completed',
      processing: t('admin.stats.processing') || 'Processing',
      error: t('admin.stats.error') || 'Error',
      pending: t('admin.stats.pending') || 'Pending',
      success: t('common.success') || 'Success',
      succeeded: t('common.success') || 'Success',
      failed: t('common.error') || 'Failed',
    };
    return labels[status.toLowerCase()] || status;
  };

  const getJobTypeLabel = (type: string) => {
    // Map internal job type strings to human readable labels
    const types: Record<string, string> = {
      'ocr_page': 'Gemini OCR',
      'reindex_book': 'Re-indexing',
      'extract_text': 'Text Extraction',
    };
    return types[type] || type;
  };

  const readyBooksCount = stats.books_by_status.find(b => b.status === 'ready')?.count || 0;
  const unindexedBooksCount = stats.total_books - readyBooksCount;
  const percentageReady = stats.total_books > 0 ? (readyBooksCount / stats.total_books) * 100 : 0;

  return (
    <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Header Section */}
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
      </div>

      {/* Refresh Button */}
      <div className="flex justify-end">
        <button
          onClick={loadStats}
          className="flex items-center gap-2 px-4 py-2 bg-white text-[#0369a1] rounded-xl border border-[#0369a1]/20 hover:border-[#0369a1] transition-all shadow-sm"
        >
          <RefreshCw size={16} />
          <span className="text-sm font-normal">{t('common.refresh') || 'Refresh'}</span>
        </button>
      </div>

      {/* Stats Blocks Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {/* Books Status Block */}
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 h-full">
          <div className="space-y-3">
            <h4 className="text-sm font-normal text-[#94a3b8] px-1">
              {t('admin.stats.booksByStatus') || 'Books by Status'}
            </h4>
            <div className="space-y-3">
              <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-600">
                    {t('admin.stats.totalBooks') || 'Total Books'}
                  </span>
                  <span className="text-2xl font-bold text-slate-800">
                    {stats.total_books.toLocaleString()}
                  </span>
                </div>
              </div>

              <div className="p-4 bg-green-50 border-2 border-green-200 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-green-700">
                    {t('admin.stats.ready') || 'Ready Books'}
                  </span>
                  <span className="text-2xl font-bold text-green-700">
                    {readyBooksCount.toLocaleString()}
                  </span>
                </div>
                <div className="w-full bg-green-200 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-green-600 h-full rounded-full transition-all duration-500"
                    style={{ width: `${percentageReady}%` }}
                  />
                </div>
                <div className="text-xs text-green-600 mt-1 text-right">
                  {percentageReady.toFixed(2)}%
                </div>
              </div>

              <div className="p-4 bg-orange-50 border-2 border-orange-200 rounded-xl">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-orange-700">
                    {t('admin.stats.completed') || 'Not Ready Books'}
                  </span>
                  <span className="text-2xl font-bold text-orange-700">
                    {unindexedBooksCount.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Page Statistics Block */}
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 h-full">
          <div className="space-y-3">
            <h4 className="text-sm font-normal text-[#94a3b8] px-1">
              {t('admin.stats.pageStats') || 'Page Statistics'}
            </h4>
            <div className="space-y-3">
              <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-600">
                    {t('admin.stats.totalPages') || 'Total Pages'}
                  </span>
                  <span className="text-2xl font-bold text-slate-800">
                    {stats.page_stats.total.toLocaleString()}
                  </span>
                </div>
              </div>

              <div className="p-4 bg-green-50 border-2 border-green-200 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-green-700">
                    {t('admin.stats.indexedPages') || 'Indexed Pages'}
                  </span>
                  <span className="text-2xl font-bold text-green-700">
                    {stats.page_stats.indexed.toLocaleString()}
                  </span>
                </div>
                <div className="w-full bg-green-200 rounded-full h-2 overflow-hidden">
                  <div
                    className="bg-green-600 h-full rounded-full transition-all duration-500"
                    style={{ width: `${stats.page_stats.percentage_indexed}%` }}
                  />
                </div>
                <div className="text-xs text-green-600 mt-1 text-right">
                  {stats.page_stats.percentage_indexed.toFixed(2)}%
                </div>
              </div>

              <div className="p-4 bg-orange-50 border-2 border-orange-200 rounded-xl">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-orange-700">
                    {t('admin.stats.unindexedPages') || 'Unindexed Pages'}
                  </span>
                  <span className="text-2xl font-bold text-orange-700">
                    {stats.page_stats.unindexed.toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Job Statistics Block */}
        <div className="glass-panel overflow-hidden rounded-[24px] p-8 shadow-xl border border-[#0369a1]/10 h-full">
          <div className="space-y-8">
            <h4 className="text-sm font-normal text-[#94a3b8] px-1">
              {t('admin.stats.jobStats') || 'Job Statistics'}
            </h4>

            <div className="space-y-3">
              {/* Total Jobs */}
              <div className="p-4 bg-slate-50 border-2 border-slate-200 rounded-xl">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-slate-600">
                    {t('admin.stats.totalJobs') || 'Total Jobs'}
                  </span>
                  <span className="text-2xl font-bold text-slate-800">
                    {((stats.jobs_by_status || []).reduce((acc, curr) => acc + curr.count, 0)).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Succeeded Jobs */}
              {(() => {
                const total = (stats.jobs_by_status || []).reduce((acc, curr) => acc + curr.count, 0);
                const succeeded = (stats.jobs_by_status || []).find(j => j.status === 'succeeded')?.count || 0;
                const percentage = total > 0 ? (succeeded / total) * 100 : 0;
                return (
                  <div className="p-4 bg-green-50 border-2 border-green-200 rounded-xl">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm text-green-700">
                        {t('admin.stats.jobSucceeded') || 'Succeeded'}
                      </span>
                      <span className="text-2xl font-bold text-green-700">
                        {succeeded.toLocaleString()}
                      </span>
                    </div>
                    <div className="w-full bg-green-200 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-green-600 h-full rounded-full transition-all duration-500"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                    <div className="text-xs text-green-600 mt-1 text-right">
                      {percentage.toFixed(2)}%
                    </div>
                  </div>
                );
              })()}

              {/* Failed Jobs */}
              <div className="p-4 bg-red-50 border-2 border-red-200 rounded-xl">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-red-700">
                    {t('admin.stats.jobFailed') || 'Failed'}
                  </span>
                  <span className="text-2xl font-bold text-red-700">
                    {((stats.jobs_by_status || []).find(j => j.status === 'failed')?.count || 0).toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Skipped Jobs */}
              <div className="p-4 bg-yellow-50 border-2 border-yellow-200 rounded-xl">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-yellow-700">
                    {t('admin.stats.jobSkipped') || 'Skipped'}
                  </span>
                  <span className="text-2xl font-bold text-yellow-700">
                    {((stats.jobs_by_status || []).find(j => j.status === 'skipped')?.count || 0).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StatsPanel;
