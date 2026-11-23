import {
  AlertCircle,
  Check,
  Copy,
  ExternalLink,
  Loader2,
  Mail,
  Save,
  Trash2,
  User,
  X,
} from 'lucide-react';
import React, { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import {
  ContactStatus,
  ContactSubmissionAdminItem,
  deleteAdminContactSubmission,
  updateAdminContactSubmission,
} from '../../services/contactService';

export const CONTACT_STATUS_STYLES: Record<
  ContactStatus,
  { bg: string; text: string; activeBg: string }
> = {
  new: {
    bg: 'bg-blue-500/10 dark:bg-blue-400/10',
    text: 'text-blue-600 dark:text-blue-400',
    activeBg: 'bg-blue-600 dark:bg-blue-500 text-white dark:text-slate-950',
  },
  reviewed: {
    bg: 'bg-amber-500/10 dark:bg-amber-400/10',
    text: 'text-amber-600 dark:text-amber-400',
    activeBg: 'bg-amber-500 dark:bg-amber-400 text-white dark:text-slate-950',
  },
  contacted: {
    bg: 'bg-emerald-500/10 dark:bg-emerald-400/10',
    text: 'text-emerald-600 dark:text-emerald-400',
    activeBg: 'bg-emerald-600 dark:bg-emerald-500 text-white dark:text-slate-950',
  },
  archived: {
    bg: 'bg-slate-500/10 dark:bg-slate-400/10',
    text: 'text-slate-600 dark:text-slate-400',
    activeBg: 'bg-slate-600 dark:bg-slate-400 text-white dark:text-slate-950',
  },
};

const ALL_STATUSES: ContactStatus[] = ['new', 'reviewed', 'contacted', 'archived'];

interface ContactDetailModalProps {
  submission: ContactSubmissionAdminItem;
  onClose: () => void;
  onUpdated: (updated: ContactSubmissionAdminItem) => void;
  onDeleted: (id: number) => void;
}

function formatDetailDate(dateString: string): string {
  try {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

export const ContactDetailModal: React.FC<ContactDetailModalProps> = ({
  submission,
  onClose,
  onUpdated,
  onDeleted,
}) => {
  const { t } = useI18n();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const notesId = useId();

  const [notes, setNotes] = useState(submission.adminNotes ?? '');
  const [copiedEmail, setCopiedEmail] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState<ContactStatus | null>(null);
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  useEffect(() => {
    setNotes(submission.adminNotes ?? '');
  }, [submission.id, submission.adminNotes]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (!dialog.open && typeof dialog.showModal === 'function') {
      dialog.showModal();
    }

    if (!('closedBy' in HTMLDialogElement.prototype)) {
      const handleBackdropClick = (event: MouseEvent) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (isDialogContent) return;
        dialog.close();
      };
      dialog.addEventListener('click', handleBackdropClick);
      return () => dialog.removeEventListener('click', handleBackdropClick);
    }
  }, []);

  useEffect(() => {
    if (confirmingDelete) {
      cancelDeleteRef.current?.focus();
    }
  }, [confirmingDelete]);

  const handleDialogClose = () => {
    if (dialogRef.current) {
      dialogRef.current.returnValue = '';
    }
    onClose();
  };

  const closeDialog = () => {
    const dialog = dialogRef.current;
    if (dialog && dialog.open && typeof dialog.close === 'function') {
      dialog.close();
    } else {
      onClose();
    }
  };

  const handleCopyEmail = async () => {
    try {
      await navigator.clipboard.writeText(submission.email);
      setCopiedEmail(true);
      setTimeout(() => setCopiedEmail(false), 2000);
    } catch {
      // Ignore clipboard failures in restricted contexts
    }
  };

  const handleStatusChange = async (nextStatus: ContactStatus) => {
    if (nextStatus === submission.status || updatingStatus) return;
    setUpdatingStatus(nextStatus);
    setFeedback(null);
    try {
      const updated = await updateAdminContactSubmission(submission.id, {
        status: nextStatus,
      });
      onUpdated(updated);
      setFeedback({ type: 'success', text: t('admin.contacts.statusUpdated') });
    } catch {
      setFeedback({ type: 'error', text: t('admin.contacts.updateError') });
    } finally {
      setUpdatingStatus(null);
    }
  };

  const notesDirty = notes.trim() !== (submission.adminNotes ?? '').trim();

  const handleSaveNotes = async () => {
    if (!notesDirty || isSavingNotes) return;
    setIsSavingNotes(true);
    setFeedback(null);
    try {
      const updated = await updateAdminContactSubmission(submission.id, {
        adminNotes: notes.trim() || null,
      });
      onUpdated(updated);
      setFeedback({ type: 'success', text: t('admin.contacts.notesSaved') });
    } catch {
      setFeedback({ type: 'error', text: t('admin.contacts.updateError') });
    } finally {
      setIsSavingNotes(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (isDeleting) return;
    setIsDeleting(true);
    setFeedback(null);
    try {
      await deleteAdminContactSubmission(submission.id);
      const deletedId = submission.id;
      closeDialog();
      onDeleted(deletedId);
    } catch {
      setIsDeleting(false);
      setConfirmingDelete(false);
      setFeedback({ type: 'error', text: t('admin.contacts.deleteError') });
    }
  };

  const interestKey = `admin.contacts.interest${
    submission.interest.charAt(0).toUpperCase() + submission.interest.slice(1)
  }`;

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      onClose={handleDialogClose}
      {...({ closedby: 'any' } as any)}
      dir="rtl"
      lang="ug"
      className="fixed inset-0 p-0 m-auto h-fit w-[calc(100%-1.5rem)] max-w-2xl max-h-[90vh] open:flex flex-col bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-3xl sm:rounded-[32px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] dark:shadow-black/60 overflow-hidden border border-slate-200/80 dark:border-slate-800 text-right text-slate-900 dark:text-slate-100"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 sm:px-7 py-4 sm:py-5 border-b border-slate-100 dark:border-slate-800/80 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          <div className="p-2.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-2xl shrink-0">
            <Mail size={20} strokeWidth={2.2} aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <h2
              id={titleId}
              className="text-base sm:text-lg font-normal text-slate-900 dark:text-slate-100 uyghur-text truncate"
            >
              {t('admin.contacts.detailTitle')}
            </h2>
            <p
              className="text-xs text-slate-400 dark:text-slate-500 mt-0.5"
              dir="ltr"
            >
              {formatDetailDate(submission.createdAt)}
            </p>
          </div>
        </div>
        <button
          type="button"
          autoFocus
          onClick={closeDialog}
          aria-label={t('common.close')}
          className="p-2 text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors shrink-0"
        >
          <X size={20} aria-hidden="true" />
        </button>
      </div>

      {/* Scrollable Body */}
      <div className="p-5 sm:p-7 space-y-5 overflow-y-auto custom-scrollbar flex-1 min-h-0">
        {/* Sender Card */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl bg-slate-50/80 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-800">
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <User
                size={16}
                className="text-[#0369a1] dark:text-[#38bdf8] shrink-0"
                aria-hidden="true"
              />
              <span
                dir="auto"
                className="text-base sm:text-lg font-normal text-slate-900 dark:text-slate-100 break-words"
              >
                {submission.name}
              </span>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8]">
                {t(interestKey)}
              </span>
            </div>
            <div
              className="flex items-center gap-2 text-xs sm:text-sm text-slate-600 dark:text-slate-300 break-all"
              dir="ltr"
            >
              <span>{submission.email}</span>
              <button
                type="button"
                onClick={handleCopyEmail}
                aria-label={t('admin.contacts.copyEmail')}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-slate-500 hover:text-[#0369a1] dark:text-slate-400 dark:hover:text-[#38bdf8] hover:bg-slate-200/60 dark:hover:bg-slate-700/60 transition-colors"
              >
                {copiedEmail ? (
                  <>
                    <Check size={13} aria-hidden="true" />
                    <span>{t('admin.contacts.emailCopied')}</span>
                  </>
                ) : (
                  <Copy size={13} aria-hidden="true" />
                )}
              </button>
              <a
                href={`mailto:${encodeURIComponent(submission.email)}`}
                aria-label={`${t('admin.contacts.replyEmail')} (${submission.email})`}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs text-slate-500 hover:text-[#0369a1] dark:text-slate-400 dark:hover:text-[#38bdf8] hover:bg-slate-200/60 dark:hover:bg-slate-700/60 transition-colors"
              >
                <ExternalLink size={13} aria-hidden="true" />
              </a>
            </div>
          </div>
        </div>

        {/* Status Selector */}
        <div className="space-y-2">
          <span className="block text-xs text-slate-500 dark:text-slate-400">
            {t('admin.contacts.status')}
          </span>
          <div className="flex flex-wrap gap-2">
            {ALL_STATUSES.map((st) => {
              const isSelected = submission.status === st;
              const isBusy = updatingStatus === st;
              const style = CONTACT_STATUS_STYLES[st];
              const labelKey = `admin.contacts.status${
                st.charAt(0).toUpperCase() + st.slice(1)
              }`;
              return (
                <button
                  key={st}
                  type="button"
                  disabled={updatingStatus !== null}
                  aria-pressed={isSelected}
                  onClick={() => handleStatusChange(st)}
                  className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs sm:text-sm transition-all disabled:opacity-60 ${
                    isSelected
                      ? `${style.activeBg} shadow-sm`
                      : `${style.bg} ${style.text} border border-current/15 hover:opacity-90`
                  }`}
                >
                  {isBusy && (
                    <Loader2
                      size={14}
                      className="animate-spin"
                      aria-hidden="true"
                    />
                  )}
                  {t(labelKey)}
                </button>
              );
            })}
          </div>
        </div>

        {/* Full Message Body */}
        <div className="space-y-2">
          <span className="block text-xs text-slate-500 dark:text-slate-400">
            {t('admin.contacts.message')}
          </span>
          <div className="p-4 sm:p-5 rounded-2xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200/80 dark:border-slate-800">
            <p
              dir="auto"
              className="text-sm sm:text-base text-slate-800 dark:text-slate-100 whitespace-pre-wrap break-words leading-relaxed"
            >
              {submission.message}
            </p>
          </div>
        </div>

        {/* Admin Notes */}
        <div className="space-y-2">
          <label
            htmlFor={notesId}
            className="block text-xs text-slate-500 dark:text-slate-400"
          >
            {t('admin.contacts.adminNotes')}
          </label>
          <textarea
            id={notesId}
            dir="auto"
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={t('admin.contacts.adminNotesPlaceholder')}
            className="w-full p-3.5 rounded-2xl bg-white dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 focus:border-[#0369a1] dark:focus:border-[#38bdf8] outline-none text-sm sm:text-base text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 transition-colors resize-y"
          />
          {notesDirty && (
            <div className="flex justify-end">
              <button
                type="button"
                disabled={isSavingNotes}
                onClick={handleSaveNotes}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 hover:opacity-90 transition-all disabled:opacity-50"
              >
                {isSavingNotes ? (
                  <Loader2
                    size={14}
                    className="animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Save size={14} aria-hidden="true" />
                )}
                {t('admin.contacts.saveNotes')}
              </button>
            </div>
          )}
        </div>

        {/* Inline Status / Error Feedback */}
        {feedback && (
          <div
            role={feedback.type === 'error' ? 'alert' : 'status'}
            className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs sm:text-sm ${
              feedback.type === 'error'
                ? 'bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 border border-red-200/60 dark:border-red-900/50'
                : 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-900/50'
            }`}
          >
            {feedback.type === 'error' ? (
              <AlertCircle size={15} aria-hidden="true" />
            ) : (
              <Check size={15} aria-hidden="true" />
            )}
            <span>{feedback.text}</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-5 sm:px-7 py-4 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/50 shrink-0">
        {confirmingDelete ? (
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {/* Place safe Cancel button where Delete was so accidental double-clicks cancel */}
              <button
                ref={cancelDeleteRef}
                type="button"
                disabled={isDeleting}
                onClick={() => setConfirmingDelete(false)}
                className="px-4 py-2 rounded-xl text-xs sm:text-sm bg-slate-200/80 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300/80 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={handleConfirmDelete}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs sm:text-sm bg-red-600 hover:bg-red-700 text-white transition-colors disabled:opacity-50"
              >
                {isDeleting ? (
                  <Loader2
                    size={14}
                    className="animate-spin"
                    aria-hidden="true"
                  />
                ) : (
                  <Trash2 size={14} aria-hidden="true" />
                )}
                {t('common.delete')}
              </button>
            </div>
            <p className="text-xs sm:text-sm text-red-600 dark:text-red-400">
              {t('admin.contacts.confirmDelete', { name: submission.name })}
            </p>
          </div>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              onClick={() => setConfirmingDelete(true)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs sm:text-sm bg-red-500/10 hover:bg-red-500/20 text-red-600 dark:text-red-400 transition-colors"
            >
              <Trash2 size={15} aria-hidden="true" />
              {t('common.delete')}
            </button>
            <button
              type="button"
              onClick={closeDialog}
              className="px-5 py-2 rounded-xl text-xs sm:text-sm bg-slate-200/80 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-300/80 dark:hover:bg-slate-700 transition-colors"
            >
              {t('common.close')}
            </button>
          </div>
        )}
      </div>
    </dialog>,
    document.body
  );
};

export default ContactDetailModal;
