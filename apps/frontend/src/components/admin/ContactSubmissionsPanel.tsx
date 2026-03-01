/**
 * Contact Submissions Panel - Admin view for contact form submissions
 */

import React, { useState, useEffect } from 'react';
import { Mail, Loader, AlertCircle } from 'lucide-react';
import { authFetch } from '../../services/authService';
import { useI18n } from '../../i18n/I18nContext';

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
  new: { bg: 'bg-blue-50', text: 'text-blue-700' },
  reviewed: { bg: 'bg-amber-50', text: 'text-amber-700' },
  contacted: { bg: 'bg-green-50', text: 'text-green-700' },
  archived: { bg: 'bg-slate-50', text: 'text-slate-500' },
};

export function ContactSubmissionsPanel() {
  const { t } = useI18n();
  const [submissions, setSubmissions] = useState<ContactSubmission[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');

  useEffect(() => {
    fetchSubmissions();
  }, [statusFilter]);

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
    <div className="space-y-6 md:space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-3 md:gap-4 group">
          <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
            <Mail size={20} className="md:w-6 md:h-6" />
          </div>
          <div>
            <h2 className="text-xl md:text-2xl lg:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.contacts.title')}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-6 md:w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <p className="text-[11px] md:text-[14px] font-normal text-[#94a3b8] uppercase">
                {t('admin.contacts.subtitle')}
              </p>
            </div>
          </div>
        </div>

        {/* Status Filter */}
        <div className="flex gap-2 flex-wrap">
          {(['all', 'new', 'reviewed', 'contacted', 'archived'] as StatusFilter[]).map((filter) => (
            <button
              key={filter}
              onClick={() => setStatusFilter(filter)}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-normal uppercase transition-all ${
                statusFilter === filter
                  ? 'bg-[#0369a1] text-white shadow-sm'
                  : 'bg-white text-slate-600 hover:bg-slate-50 border border-slate-200'
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
          <Loader className="w-8 h-8 text-[#0369a1] animate-spin" />
        </div>
      ) : error ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-3" />
            <p className="text-red-600">{error}</p>
          </div>
        </div>
      ) : submissions.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <Mail className="w-12 h-12 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500">{t('admin.contacts.noSubmissions')}</p>
          </div>
        </div>
      ) : (
        <div className="glass-panel rounded-[16px] md:rounded-[24px]" style={{ padding: 0, overflow: 'visible' }}>
          <div className="overflow-x-auto rounded-[16px] md:rounded-[24px]" style={{ overflow: 'hidden' }}>
            <table className="w-full text-right lg:min-w-[900px]" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] uppercase border-b border-[#0369a1]/10">
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
                {submissions.map((submission) => {
                  const statusStyle = getStatusStyle(submission.status);
                  return (
                    <tr
                      key={submission.id}
                      className="border-b border-[#0369a1]/5 hover:bg-[#0369a1]/5 transition-colors group/row"
                    >
                      <td className="px-4 md:px-8 py-3 md:py-5">
                        <div className="font-normal text-[#1a1a1a] text-[14px] md:text-[16px] lg:text-[18px]">{submission.name}</div>
                        <div className="md:hidden text-[11px] md:text-[13px] font-normal text-[#94a3b8] uppercase truncate max-w-[150px] md:max-w-none mt-1" dir="ltr">
                          {submission.email}
                        </div>
                        <div className="md:hidden mt-1">
                          <span className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${statusStyle.bg} ${statusStyle.text} rounded-lg text-[11px] md:text-[14px] font-normal uppercase`}>
                            {t(`admin.contacts.status${submission.status.charAt(0).toUpperCase() + submission.status.slice(1)}`)}
                          </span>
                        </div>
                      </td>
                      <td className="hidden md:table-cell px-4 md:px-8 py-3 md:py-5 text-[11px] md:text-[13px] font-normal text-[#94a3b8] uppercase" dir="ltr">
                        {submission.email}
                      </td>
                      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5">
                        <span className="text-[14px] md:text-[16px] font-normal text-[#1a1a1a]">
                          {t(`admin.contacts.interest${submission.interest.charAt(0).toUpperCase() + submission.interest.slice(1)}`)}
                        </span>
                      </td>
                      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5">
                        <div className="text-[14px] md:text-[16px] font-normal text-[#94a3b8] truncate max-w-xs" title={submission.message}>
                          {submission.message}
                        </div>
                      </td>
                      <td className="hidden md:table-cell px-4 md:px-8 py-3 md:py-5">
                        <span className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${statusStyle.bg} ${statusStyle.text} rounded-lg text-[11px] md:text-[14px] font-normal uppercase`}>
                          {t(`admin.contacts.status${submission.status.charAt(0).toUpperCase() + submission.status.slice(1)}`)}
                        </span>
                      </td>
                      <td className="px-4 md:px-8 py-3 md:py-5 text-[11px] md:text-[13px] font-normal text-[#94a3b8]" dir="ltr">
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
