/**
 * Contact Submissions Panel - Admin view for contact form submissions
 */

import { AlertCircle, Loader, Mail, Search, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { authFetch } from '../../services/authService';


interface ContactSubmission {
  id: number;
  name: string;
  email: string;
  interest: 'editor' | 'developer' | 'other';
  message: string;
  status: 'new' | 'reviewed' | 'contacted' | 'archived';
  adminNotes?: string;
  reviewedBy?: string;
  reviewedAt?: string;
  createdAt: string;
}

type StatusFilter = 'all' | 'new' | 'reviewed' | 'contacted' | 'archived';

const STATUS_STYLES: Record<string, { bg: string; text: string }> = {
  new: { bg: 'bg-blue-500/5 dark:bg-blue-400/5', text: 'text-blue-500 dark:text-blue-400' },
  reviewed: { bg: 'bg-amber-500/5 dark:bg-amber-400/5', text: 'text-amber-500 dark:text-amber-400' },
  contacted: { bg: 'bg-emerald-500/5 dark:bg-emerald-400/5', text: 'text-emerald-500 dark:text-emerald-400' },
  archived: { bg: 'bg-slate-500/5 dark:bg-slate-400/5', text: 'text-slate-500 dark:text-slate-400' },
};

export function ContactSubmissionsPanel() {
  const { t } = useI18n();
  const [submissions, setSubmissions] = useState<ContactSubmission[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchSubmissions();
  }, [statusFilter]);

  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, []);

  const fetchSubmissions = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const queryParams = statusFilter !== 'all' ? `?status=${statusFilter}` : '';
      const response = await authFetch(`/api/contact/admin/submissions${queryParams}`);

      if (!response.ok) {
        throw new Error('Failed to fetch submissions');
      }

      const data = await response.json();
      setSubmissions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.contacts.error'));
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusStyle = (status: string) => {
    return STATUS_STYLES[status] || STATUS_STYLES.new;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in w-full max-w-full min-w-0" dir="rtl" lang="ug">
      {/* Search and Filter Row - matching other tabs layout */}
      <div className="flex flex-col-reverse md:flex-row gap-3 md:gap-4 items-center">
        <div className="relative flex-1 lg:flex-none lg:w-[30%] group w-full">
          <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8]">
            <Search size={18} strokeWidth={3} />
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            ref={inputRef}
            placeholder={t('common.search')}
            className="w-full pr-12 pl-6 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text shadow-sm text-base"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors"
            >
              <X size={18} />
            </button>
          )}
        </div>

        <div className="flex gap-2 flex-wrap w-full justify-end md:w-auto md:justify-start md:mr-auto">
          {(['all', 'new', 'reviewed', 'contacted', 'archived'] as StatusFilter[]).map((filter) => (
            <button
              key={filter}
              onClick={() => setStatusFilter(filter)}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-normal uppercase transition-all ${statusFilter === filter
                ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200'
                }`}
            >
              {t(`admin.contacts.filter${filter.charAt(0).toUpperCase() + filter.slice(1)}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader className="w-8 h-8 text-[#0369a1] dark:text-[#38bdf8] animate-spin" />
        </div>
      ) : error ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-center glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-12 rounded-[24px]">
            <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-3" />
            <p className="text-red-600 dark:text-red-400 font-normal">{error}</p>
          </div>
        </div>
      ) : submissions.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-center glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-12 rounded-[24px]">
            <Mail className="w-12 h-12 text-slate-400 dark:text-slate-600 mx-auto mb-3" />
            <p className="text-slate-500 dark:text-slate-400 font-normal">{t('admin.contacts.noSubmissions')}</p>
          </div>
        </div>
      ) : (
        <div className="glass-panel dark:bg-slate-900/60 shadow-xl border border-[#0369a1]/10 dark:border-slate-800 rounded-[16px] md:rounded-[24px] w-full max-w-full min-w-0" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="overflow-x-auto rounded-[16px] md:rounded-[24px] w-full max-w-full min-w-0">
            <table className="w-full min-w-[600px] lg:min-w-[900px] text-right" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] dark:text-[#38bdf8] uppercase border-b border-[#0369a1]/10 dark:border-slate-800">
                  <th className="px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                    {t('admin.contacts.name')}
                  </th>
                  <th className="hidden md:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                    {t('admin.contacts.email')}
                  </th>
                  <th className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                    {t('admin.contacts.interest')}
                  </th>
                  <th className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                    {t('admin.contacts.message')}
                  </th>
                  <th className="hidden md:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                    {t('admin.contacts.status')}
                  </th>
                  <th className="px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                    {t('admin.contacts.createdAt')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {submissions.filter(s => 
                  s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                  s.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
                  s.message.toLowerCase().includes(searchQuery.toLowerCase())
                ).map((submission) => {
                  const statusStyle = getStatusStyle(submission.status);
                  return (
                    <tr
                      key={submission.id}
                      className="border-b border-[#0369a1]/5 dark:border-slate-800/30 hover:bg-[#e8f4f8]/20 dark:hover:bg-[#38bdf8]/5 transition-colors group/row"
                    >
                      <td className="px-4 md:px-8 py-3 md:py-5">
                        <div className="font-normal text-[#1a1a1a] dark:text-slate-100 text-[14px] md:text-[16px] lg:text-[18px]">{submission.name}</div>
                        <div className="md:hidden text-[11px] md:text-[13px] font-normal text-[#94a3b8] dark:text-slate-400 uppercase truncate max-w-[150px] md:max-w-none mt-1" dir="ltr">
                          {submission.email}
                        </div>
                        <div className="md:hidden mt-1">
                          <span className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${statusStyle.bg} ${statusStyle.text} rounded-lg text-[11px] md:text-[14px] font-normal uppercase border border-current/10`}>
                            {t(`admin.contacts.status${submission.status.charAt(0).toUpperCase() + submission.status.slice(1)}`)}
                          </span>
                        </div>
                      </td>
                      <td className="hidden md:table-cell px-4 md:px-8 py-3 md:py-5 text-[11px] md:text-[13px] font-normal text-[#94a3b8] dark:text-slate-400 uppercase" dir="ltr">
                        {submission.email}
                      </td>
                      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5">
                        <span className="text-[14px] md:text-[16px] font-normal text-[#1a1a1a] dark:text-slate-100">
                          {t(`admin.contacts.interest${submission.interest.charAt(0).toUpperCase() + submission.interest.slice(1)}`)}
                        </span>
                      </td>
                      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5">
                        <div className="text-[14px] md:text-[16px] font-normal text-[#94a3b8] dark:text-slate-400 truncate max-w-xs" title={submission.message}>
                          {submission.message}
                        </div>
                      </td>
                      <td className="hidden md:table-cell px-4 md:px-8 py-3 md:py-5">
                        <span className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${statusStyle.bg} ${statusStyle.text} rounded-lg text-[11px] md:text-[14px] font-normal uppercase border border-current/10`}>
                          {t(`admin.contacts.status${submission.status.charAt(0).toUpperCase() + submission.status.slice(1)}`)}
                        </span>
                      </td>
                      <td className="px-4 md:px-8 py-3 md:py-5 text-[11px] md:text-[13px] font-normal text-[#94a3b8] dark:text-slate-400" dir="ltr">
                        {formatDate(submission.createdAt)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

export default ContactSubmissionsPanel;
