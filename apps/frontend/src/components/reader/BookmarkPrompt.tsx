import { Bookmark as BookmarkIcon, Loader2, Quote, Trash2 } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { OAuthButtonGroup } from '../auth/AuthButton';

interface BookmarkPromptProps {
  top?: number;
  left?: number;
  mode: 'create' | 'edit';
  defaultName: string;
  quoteText?: string | null;
  isAuthenticated: boolean;
  onSave: (name: string) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

export const BookmarkPrompt: React.FC<BookmarkPromptProps> = ({
  mode,
  defaultName,
  quoteText,
  isAuthenticated,
  onSave,
  onDelete,
  onClose,
}) => {
  const { t } = useI18n();
  const [name, setName] = useState(defaultName);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed || isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onSave(trimmed);
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onDelete?.();
      onClose();
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-6" dir="rtl" lang="ug">
      {/* Full Backdrop Overlay */}
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-md animate-fade-in"
        onClick={onClose}
      />

      {/* Standard Modal Window Card */}
      <div
        className="bg-white/90 dark:bg-slate-900/90 backdrop-blur-2xl rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.15)] dark:shadow-black/50 w-full max-w-md relative z-10 overflow-hidden animate-fade-in border border-white/40 dark:border-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-10">
          {/* Header */}
          <div className="flex items-center gap-4 mb-6">
            <div className="p-3 rounded-2xl bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] shrink-0">
              <BookmarkIcon size={32} strokeWidth={2.5} />
            </div>
            <h3 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] dark:text-slate-100 uyghur-text">
              {t(mode === 'create' ? 'bookmarks.newBookmark' : 'bookmarks.editBookmark')}
            </h3>
          </div>

          {/* Content Body */}
          {isAuthenticated ? (
            <div className="space-y-6">
              {/* Passage quote preview (if quoting selected text) */}
              {quoteText && (
                <div className="p-4 bg-slate-50 dark:bg-slate-800/60 rounded-[20px] border-r-4 border-[#0369a1] dark:border-[#38bdf8] flex items-start gap-3">
                  <Quote size={16} className="text-[#0369a1] dark:text-[#38bdf8] shrink-0 mt-0.5 rotate-180" />
                  <p className="text-sm text-slate-600 dark:text-slate-300 font-serif italic line-clamp-3 leading-relaxed uyghur-text">
                    "{quoteText}"
                  </p>
                </div>
              )}

              {/* Bookmark Name Input */}
              <div>
                <label className="block text-sm font-normal text-[#94a3b8] dark:text-slate-400 mb-2 uyghur-text">
                  {t('bookmarks.bookmarkName')}
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleSave();
                    if (e.key === 'Escape') onClose();
                  }}
                  autoFocus
                  className="w-full px-5 py-4 bg-slate-50/80 dark:bg-slate-800/80 border-2 border-slate-100 dark:border-slate-700/80 rounded-[20px] uyghur-text outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] focus:bg-white dark:focus:bg-slate-800 text-slate-800 dark:text-slate-100 text-base sm:text-lg transition-all shadow-sm placeholder:text-slate-400 dark:placeholder:text-slate-500"
                  placeholder={t('bookmarks.namePlaceholder')}
                />
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-4 pt-2">
                {mode === 'edit' && onDelete && (
                  <button
                    type="button"
                    onClick={handleDelete}
                    disabled={isSubmitting}
                    className="py-4 px-5 bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-950/40 text-red-500 font-normal rounded-[20px] transition-all active:scale-95 text-sm sm:text-base flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                    title={t('bookmarks.delete')}
                  >
                    <Trash2 size={18} strokeWidth={2.2} />
                    <span>{t('bookmarks.delete')}</span>
                  </button>
                )}
                <button
                  onClick={onClose}
                  disabled={isSubmitting}
                  className="flex-1 py-4 px-6 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[#94a3b8] dark:text-slate-400 font-normal rounded-[20px] transition-all active:scale-95 text-sm sm:text-base disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                >
                  {t('common.cancel')}
                </button>
                <button
                  onClick={handleSave}
                  disabled={!name.trim() || isSubmitting}
                  className="flex-1 py-4 px-6 font-normal rounded-[20px] transition-all shadow-xl active:scale-95 text-sm sm:text-base disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 bg-[#0369a1] dark:bg-[#38bdf8] hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 text-white dark:text-slate-950 shadow-[#0369a1]/30 dark:shadow-none cursor-pointer"
                >
                  {isSubmitting && <Loader2 size={18} className="animate-spin" />}
                  <span>{t('bookmarks.save')}</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-6 text-center">
              <p className="text-[#94a3b8] dark:text-slate-400 font-normal leading-loose text-base sm:text-lg uyghur-text">
                {t('bookmarks.signInToSave')}
              </p>
              <div className="flex justify-center">
                <OAuthButtonGroup align="down" side="center" />
              </div>
              <div className="pt-2">
                <button
                  onClick={onClose}
                  className="w-full py-4 px-6 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[#94a3b8] dark:text-slate-400 font-normal rounded-[20px] transition-all active:scale-95 text-sm sm:text-base cursor-pointer"
                >
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};
export default BookmarkPrompt;
