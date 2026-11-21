/**
 * Contact Submissions Panel - Admin view for contact form submissions
 */

import { AlertCircle, Eye, Loader, Mail, Search, Trash2, X } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { useNotification } from '../../context/NotificationContext';
import { useI18n } from '../../i18n/I18nContext';
import {
  ContactStatus,
  ContactSubmissionAdminItem,
  deleteAdminContactSubmission,
  getAdminContactSubmissions,
} from '../../services/contactService';
import { CONTACT_STATUS_STYLES, ContactDetailModal } from './ContactDetailModal';

type StatusFilter = 'all' | ContactStatus;

export function ContactSubmissionsPanel() {
  const { t } = useI18n();
  const { setModal } = useAppContext();
  const { addNotification } = useNotification();

  const [submissions, setSubmissions] = useState<ContactSubmissionAdminItem[]>([]);
  const [selectedSubmission, setSelectedSubmission] =
    useState<ContactSubmissionAdminItem | null>(null);
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
      const data = await getAdminContactSubmissions(
        statusFilter !== 'all' ? statusFilter : undefined
      );
      setSubmissions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.contacts.error'));
    } finally {
      setIsLoading(false);
    }
  };

  const getStatusStyle = (status: ContactStatus) => {
    return CONTACT_STATUS_STYLES[status] || CONTACT_STATUS_STYLES.new;
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const handleSubmissionUpdated = (updated: ContactSubmissionAdminItem) => {
    setSelectedSubmission(updated);
    setSubmissions((prev) => {
      if (statusFilter !== 'all' && updated.status !== statusFilter) {
        return prev.filter((item) => item.id !== updated.id);
      }
      return prev.map((item) => (item.id === updated.id ? updated : item));
    });
  };

  const handleSubmissionDeletedFromModal = (deletedId: number) => {
    setSubmissions((prev) => prev.filter((item) => item.id !== deletedId));
    setSelectedSubmission(null);
    addNotification(t('admin.contacts.deleteSuccess'), 'success');
  };

  const handleDeleteRow = (
    event: React.MouseEvent,
    submission: ContactSubmissionAdminItem
  ) => {
    event.stopPropagation();
    setModal({
      isOpen: true,
      title: t('common.delete'),
      message: t('admin.contacts.confirmDelete', { name: submission.name }),
      type: 'confirm',
      confirmText: t('common.delete'),
      destructive: true,
      onConfirm: async () => {
        setModal((prev: any) => ({ ...prev, isLoading: true }));
        try {
          await deleteAdminContactSubmission(submission.id);
          setSubmissions((prev) => prev.filter((s) => s.id !== submission.id));
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('admin.contacts.deleteSuccess'), 'success');
        } catch {
          setModal((prev: any) => ({ ...prev, isOpen: false }));
          addNotification(t('admin.contacts.deleteError'), 'error');
        }
      },
    });
  };

  const filteredSubmissions = submissions.filter(
    (s) =>
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.message.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div
      className="space-y-6 md:space-y-8 animate-fade-in w-full max-w-full min-w-0"
      dir="rtl"
      lang="ug"
    >
      {/* Search and Filter Row */}
      <div className="flex flex-col-reverse md:flex-row gap-3 md:gap-4 items-center">
        <div className="relative flex-1 lg:flex-none lg:w-[30%] group w-full">
          <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8]">
            <Search size={18} strokeWidth={3} aria-hidden="true" />
          </div>
          <input
            type="search"
            aria-label={t('common.search')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            ref={inputRef}
            placeholder={t('common.search')}
            className="w-full pr-12 pl-10 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text shadow-sm text-base"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              aria-label={t('common.clear')}
              className="absolute inset-y-0 left-3 flex items-center p-1 text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors"
            >
              <X size={18} aria-hidden="true" />
            </button>
          )}
        </div>

        <div className="flex gap-2 flex-wrap w-full justify-end md:w-auto md:justify-start md:mr-auto">
          {(
            ['all', 'new', 'reviewed', 'contacted', 'archived'] as StatusFilter[]
          ).map((filter) => (
            <button
              key={filter}
              type="button"
              aria-pressed={statusFilter === filter}
              onClick={() => setStatusFilter(filter)}
              className={`px-3 sm:px-4 py-2 rounded-xl text-xs sm:text-sm font-normal uppercase transition-all ${
                statusFilter === filter
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                  : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              {t(
                `admin.contacts.filter${
                  filter.charAt(0).toUpperCase() + filter.slice(1)
                }`
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader
            className="w-8 h-8 text-[#0369a1] dark:text-[#38bdf8] animate-spin"
            aria-hidden="true"
          />
        </div>
      ) : error ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-center glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-12 rounded-[24px]">
            <AlertCircle
              className="w-12 h-12 text-red-500 mx-auto mb-3"
              aria-hidden="true"
            />
            <p className="text-red-600 dark:text-red-400 font-normal">{error}</p>
          </div>
        </div>
      ) : filteredSubmissions.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <div className="text-center glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-12 rounded-[24px]">
            <Mail
              className="w-12 h-12 text-slate-400 dark:text-slate-600 mx-auto mb-3"
              aria-hidden="true"
            />
            <p className="text-slate-500 dark:text-slate-400 font-normal">
              {t(
                searchQuery
                  ? 'admin.contacts.noSearchResults'
                  : 'admin.contacts.noSubmissions'
              )}
            </p>
          </div>
        </div>
      ) : (
        <div
          className="glass-panel dark:bg-slate-900/60 shadow-xl border border-[#0369a1]/10 dark:border-slate-800 rounded-[16px] md:rounded-[24px] w-full max-w-full min-w-0"
          style={{ padding: 0, overflow: 'hidden' }}
        >
          <div className="overflow-x-auto rounded-[16px] md:rounded-[24px] w-full max-w-full min-w-0">
            <table
              className="w-full min-w-[540px] lg:min-w-[900px] text-right"
              dir="rtl"
            >
              <thead>
                <tr className="bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] dark:text-[#38bdf8] uppercase border-b border-[#0369a1]/10 dark:border-slate-800">
                  <th
                    scope="col"
                    className="px-4 md:px-6 py-3 md:py-5 text-right font-normal"
                  >
                    {t('admin.contacts.name')}
                  </th>
                  <th
                    scope="col"
                    className="hidden md:table-cell px-4 md:px-6 py-3 md:py-5 text-right font-normal"
                  >
                    {t('admin.contacts.email')}
                  </th>
                  <th
                    scope="col"
                    className="hidden lg:table-cell px-4 md:px-6 py-3 md:py-5 text-right font-normal"
                  >
                    {t('admin.contacts.interest')}
                  </th>
                  <th
                    scope="col"
                    className="px-4 md:px-6 py-3 md:py-5 text-right font-normal"
                  >
                    {t('admin.contacts.message')}
                  </th>
                  <th
                    scope="col"
                    className="hidden md:table-cell px-4 md:px-6 py-3 md:py-5 text-right font-normal"
                  >
                    {t('admin.contacts.status')}
                  </th>
                  <th
                    scope="col"
                    className="hidden sm:table-cell px-4 md:px-6 py-3 md:py-5 text-right font-normal"
                  >
                    {t('admin.contacts.createdAt')}
                  </th>
                  <th
                    scope="col"
                    className="px-3 md:px-6 py-3 md:py-5 text-center font-normal"
                  >
                    {t('admin.contacts.actions')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredSubmissions.map((submission) => {
                  const statusStyle = getStatusStyle(submission.status);
                  return (
                    <tr
                      key={submission.id}
                      onClick={(e) => {
                        const target = e.target as HTMLElement;
                        if (target.closest('button, a')) return;
                        setSelectedSubmission(submission);
                      }}
                      className="border-b border-[#0369a1]/5 dark:border-slate-800/30 hover:bg-[#e8f4f8]/30 dark:hover:bg-[#38bdf8]/5 transition-colors cursor-pointer group/row"
                    >
                      <td className="px-4 md:px-6 py-3 md:py-5">
                        <div
                          dir="auto"
                          className="font-normal text-[#1a1a1a] dark:text-slate-100 text-[14px] md:text-[16px] lg:text-[17px] group-hover/row:text-[#0369a1] dark:group-hover/row:text-[#38bdf8] transition-colors"
                        >
                          {submission.name}
                        </div>
                        <div
                          className="md:hidden text-[11px] font-normal text-[#94a3b8] dark:text-slate-400 uppercase truncate max-w-[160px] mt-1"
                          dir="ltr"
                        >
                          {submission.email}
                        </div>
                        <div className="md:hidden mt-1">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 ${statusStyle.bg} ${statusStyle.text} rounded-lg text-[11px] font-normal uppercase border border-current/10`}
                          >
                            {t(
                              `admin.contacts.status${
                                submission.status.charAt(0).toUpperCase() +
                                submission.status.slice(1)
                              }`
                            )}
                          </span>
                        </div>
                      </td>
                      <td
                        className="hidden md:table-cell px-4 md:px-6 py-3 md:py-5 text-[11px] md:text-[13px] font-normal text-[#94a3b8] dark:text-slate-400 uppercase"
                        dir="ltr"
                      >
                        {submission.email}
                      </td>
                      <td className="hidden lg:table-cell px-4 md:px-6 py-3 md:py-5">
                        <span className="text-[14px] md:text-[15px] font-normal text-[#1a1a1a] dark:text-slate-100">
                          {t(
                            `admin.contacts.interest${
                              submission.interest.charAt(0).toUpperCase() +
                              submission.interest.slice(1)
                            }`
                          )}
                        </span>
                      </td>
                      <td className="px-4 md:px-6 py-3 md:py-5 max-w-[200px] sm:max-w-xs lg:max-w-md">
                        <button
                          type="button"
                          onClick={() => setSelectedSubmission(submission)}
                          className="w-full text-start focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#0369a1] dark:focus-visible:outline-[#38bdf8] rounded-lg"
                        >
                          <span
                            dir="auto"
                            className="block text-[13px] md:text-[15px] font-normal text-slate-600 dark:text-slate-300 group-hover/row:text-slate-900 dark:group-hover/row:text-slate-100 line-clamp-2 break-words transition-colors"
                          >
                            {submission.message}
                          </span>
                        </button>
                      </td>
                      <td className="hidden md:table-cell px-4 md:px-6 py-3 md:py-5 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center gap-1 md:gap-2 px-2.5 py-1 ${statusStyle.bg} ${statusStyle.text} rounded-lg text-[11px] md:text-[13px] font-normal uppercase border border-current/10`}
                        >
                          {t(
                            `admin.contacts.status${
                              submission.status.charAt(0).toUpperCase() +
                              submission.status.slice(1)
                            }`
                          )}
                        </span>
                      </td>
                      <td
                        className="hidden sm:table-cell px-4 md:px-6 py-3 md:py-5 text-[11px] md:text-[13px] font-normal text-[#94a3b8] dark:text-slate-400 whitespace-nowrap"
                        dir="ltr"
                      >
                        {formatDate(submission.createdAt)}
                      </td>
                      <td className="px-3 md:px-6 py-3 md:py-5">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => setSelectedSubmission(submission)}
                            aria-label={`${t('admin.contacts.viewMessage')} — ${submission.name}`}
                            className="p-2 rounded-xl text-slate-500 hover:text-[#0369a1] dark:text-slate-400 dark:hover:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 transition-colors"
                          >
                            <Eye size={17} aria-hidden="true" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => handleDeleteRow(e, submission)}
                            aria-label={`${t('common.delete')} — ${submission.name}`}
                            className="p-2 rounded-xl text-slate-400 hover:text-red-600 dark:text-slate-500 dark:hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          >
                            <Trash2 size={17} aria-hidden="true" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedSubmission && (
        <ContactDetailModal
          submission={selectedSubmission}
          onClose={() => setSelectedSubmission(null)}
          onUpdated={handleSubmissionUpdated}
          onDeleted={handleSubmissionDeletedFromModal}
        />
      )}
    </div>
  );
}

export default ContactSubmissionsPanel;
