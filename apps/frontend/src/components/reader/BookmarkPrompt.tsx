import { Bookmark as BookmarkIcon, Trash2 } from 'lucide-react';
import React from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { OAuthButtonGroup } from '../auth/AuthButton';

interface BookmarkPromptProps {
  top: number;
  left: number;
  mode: 'create' | 'edit';
  defaultName: string;
  isAuthenticated: boolean;
  onSave: (name: string) => Promise<void>;
  onDelete?: () => Promise<void>;
  onClose: () => void;
}

export const BookmarkPrompt: React.FC<BookmarkPromptProps> = ({
  top, left, mode, defaultName, isAuthenticated, onSave, onDelete, onClose,
}) => {
  const { t } = useI18n();
  const [name, setName] = React.useState(defaultName);

  const handleSave = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    await onSave(trimmed);
    onClose();
  };

  const handleDelete = async () => {
    await onDelete?.();
    onClose();
  };

  return createPortal(
    <div
      style={{ position: 'fixed', top, left, transform: 'translateX(-50%)' }}
      className="z-[260] w-72 bg-white dark:bg-slate-900 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 rounded-2xl shadow-2xl p-4"
    >
      {isAuthenticated ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[#0369a1] dark:text-[#38bdf8] text-sm font-bold">
            <BookmarkIcon size={16} />
            {t(mode === 'create' ? 'bookmarks.newBookmark' : 'bookmarks.editBookmark')}
          </div>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full px-3 py-2 rounded-xl border border-[#0369a1]/20 dark:border-[#38bdf8]/20 bg-white dark:bg-slate-800 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
            autoFocus
          />
          <div className="flex items-center justify-between gap-2">
            {mode === 'edit' && onDelete && (
              <button
                onClick={handleDelete}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 text-xs font-bold uppercase"
              >
                <Trash2 size={14} /> {t('bookmarks.delete')}
              </button>
            )}
            <div className="flex items-center gap-2 ms-auto">
              <button onClick={onClose} className="px-3 py-1.5 rounded-xl text-slate-400 dark:text-slate-500 text-xs font-bold uppercase">
                {t('common.cancel')}
              </button>
              <button
                onClick={handleSave}
                className="px-3 py-1.5 rounded-xl bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs font-bold uppercase"
              >
                {t('bookmarks.save')}
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-3 text-center">
          <p className="text-sm text-[#1a1a1a] dark:text-slate-100">{t('bookmarks.signInToSave')}</p>
          <OAuthButtonGroup align="down" side="center" />
        </div>
      )}
    </div>,
    document.body
  );
};
