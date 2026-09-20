import { Bookmark as BookmarkIcon, Edit3, Trash2, X } from 'lucide-react';
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

export const BookmarksDrawer: React.FC<BookmarksDrawerProps> = ({ bookmarks, onJumpTo, onRename, onDelete, onClose }) => {
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
    <div className="fixed inset-0 z-[300] flex justify-end bg-black/20" onClick={onClose}>
      <div
        className="h-full w-full max-w-sm bg-white dark:bg-slate-900 shadow-2xl p-5 overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-[#1a1a1a] dark:text-slate-100 flex items-center gap-2">
            <BookmarkIcon size={18} className="text-[#0369a1] dark:text-[#38bdf8]" />
            {t('bookmarks.drawerTitle')}
          </h3>
          <button onClick={onClose} className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={18} />
          </button>
        </div>

        {sorted.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500 text-center py-10">{t('bookmarks.emptyForBook')}</p>
        ) : (
          <ul className="space-y-2">
            {sorted.map((bookmark) => (
              <li key={bookmark.id} className="rounded-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10">
                {editingId === bookmark.id ? (
                  <div className="p-3 space-y-2">
                    <input
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      className="w-full px-2 py-1.5 rounded-lg border border-[#0369a1]/20 dark:border-[#38bdf8]/20 bg-white dark:bg-slate-800 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none"
                      autoFocus
                    />
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setEditingId(null)} className="px-2 py-1 rounded-lg text-slate-400 text-xs font-bold uppercase">
                        {t('common.cancel')}
                      </button>
                      <button onClick={saveEditing} className="px-2 py-1 rounded-lg bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs font-bold uppercase">
                        {t('bookmarks.save')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button
                      onClick={() => onJumpTo(bookmark.pageNumber, bookmark.quoteText ?? undefined)}
                      className="w-full text-start p-3"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span data-testid="bookmark-drawer-name" className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100">
                          {bookmark.name}
                        </span>
                        <span className="text-xs text-slate-400 dark:text-slate-500">{bookmark.pageNumber}</span>
                      </div>
                      {bookmark.quoteText && (
                        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">{bookmark.quoteText}</p>
                      )}
                    </button>
                    <div className="flex justify-end gap-1 px-3 pb-2">
                      <button
                        onClick={() => startEditing(bookmark)}
                        title={t('bookmarks.rename')}
                        className="p-1.5 rounded-lg text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10"
                      >
                        <Edit3 size={14} />
                      </button>
                      <button
                        onClick={() => onDelete(bookmark.id)}
                        title={t('bookmarks.delete')}
                        className="p-1.5 rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
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
