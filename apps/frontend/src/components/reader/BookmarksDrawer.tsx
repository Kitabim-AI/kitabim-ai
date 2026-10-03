import { BookMarked, Check, Edit3, Quote, Trash2, X } from 'lucide-react';
import { Bookmark } from '@shared/types';
import React from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';

interface BookmarksDrawerProps {
  bookmarks: Bookmark[];
  onJumpTo: (pageNumber: number, quoteText?: string) => void;
  onRename: (id: string, name: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onClose: () => void;
}

export const BookmarksDrawer: React.FC<BookmarksDrawerProps> = ({
  bookmarks,
  onJumpTo,
  onRename,
  onDelete,
  onClose,
}) => {
  const { t } = useI18n();
  const sorted = [...bookmarks].sort((a, b) => a.pageNumber - b.pageNumber);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingName, setEditingName] = React.useState('');

  const startEditing = (bookmark: Bookmark) => {
    setEditingId(bookmark.id);
    setEditingName(bookmark.name);
  };

  const saveEditing = async () => {
    const trimmed = editingName.trim();
    if (editingId && trimmed) {
      await onRename(editingId, trimmed);
    }
    setEditingId(null);
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex justify-start bg-slate-900/60 backdrop-blur-sm transition-opacity"
      onClick={onClose}
      dir="rtl"
    >
      <div
        className="h-full w-full max-w-md bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl shadow-2xl p-5 sm:p-6 overflow-y-auto flex flex-col border-s border-slate-200 dark:border-slate-800"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between pb-4 mb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl shadow-sm">
              <BookMarked size={18} strokeWidth={2.2} />
            </div>
            <h3 className="text-lg font-bold text-[#1a1a1a] dark:text-slate-100 uyghur-text">
              {t('bookmarks.drawerTitle')}
            </h3>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        {sorted.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-20 text-center space-y-3">
            <div className="p-4 bg-slate-100 dark:bg-slate-800 rounded-2xl text-slate-400 dark:text-slate-500">
              <BookMarked size={28} strokeWidth={1.5} />
            </div>
            <p className="text-sm font-medium text-slate-400 dark:text-slate-500 uyghur-text">
              {t('bookmarks.emptyForBook')}
            </p>
          </div>
        ) : (
          <ul className="space-y-3 flex-1">
            {sorted.map((bookmark) => (
              <li
                key={bookmark.id}
                className="bg-slate-50/70 dark:bg-slate-800/50 rounded-2xl border border-slate-200/80 dark:border-slate-800 hover:border-[#0369a1]/30 dark:hover:border-[#38bdf8]/30 transition-all shadow-sm p-3.5"
              >
                {editingId === bookmark.id ? (
                  <div className="space-y-3" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveEditing();
                        if (e.key === 'Escape') setEditingId(null);
                      }}
                      className="w-full px-3 py-2 rounded-xl border border-[#0369a1] dark:border-[#38bdf8] bg-white dark:bg-slate-800 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none uyghur-text shadow-sm"
                      autoFocus
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => setEditingId(null)}
                        className="px-3 py-1.5 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs font-bold uppercase transition-colors"
                      >
                        {t('common.cancel')}
                      </button>
                      <button
                        onClick={saveEditing}
                        className="flex items-center gap-1 px-3.5 py-1.5 rounded-xl bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs font-bold uppercase shadow-sm transition-opacity hover:opacity-90"
                      >
                        <Check size={12} strokeWidth={2.5} />
                        <span>{t('bookmarks.save')}</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onJumpTo(bookmark.pageNumber, bookmark.quoteText ?? undefined)}
                      className="w-full text-start group/btn space-y-2"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span
                          data-testid="bookmark-drawer-name"
                          className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100 uyghur-text group-hover/btn:text-[#0369a1] dark:group-hover/btn:text-[#38bdf8] transition-colors"
                        >
                          {bookmark.name}
                        </span>
                        <span className="px-2 py-0.5 rounded-lg bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] text-xs font-bold shrink-0">
                          {t('chat.pageNumber', { page: bookmark.pageNumber })}
                        </span>
                      </div>
                      {bookmark.quoteText && (
                        <div className="p-2.5 bg-white dark:bg-slate-900/60 rounded-xl border-r-3 border-[#0369a1] dark:border-[#38bdf8] text-xs text-slate-600 dark:text-slate-300 uyghur-text line-clamp-3 leading-relaxed relative">
                          <Quote size={11} className="inline-block text-[#0369a1]/40 dark:text-[#38bdf8]/40 me-1 -scale-x-100" />
                          <span>{bookmark.quoteText}</span>
                        </div>
                      )}
                    </button>
                    <div className="flex justify-end gap-1 pt-2 mt-2 border-t border-slate-200/60 dark:border-slate-800">
                      <button
                        onClick={() => startEditing(bookmark)}
                        title={t('bookmarks.rename')}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 transition-colors"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => onDelete(bookmark.id)}
                        title={t('bookmarks.delete')}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>,
    document.body
  );
};
