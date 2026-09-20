import { Edit3, Search, Trash2 } from 'lucide-react';
import React from 'react';
import { useBookmarks } from '../../hooks/useBookmarks';
import { useI18n } from '../../i18n/I18nContext';
import { GuestAuthWall } from '../reader/GuestAuthWall';
import { useAuth } from '../../hooks/useAuth';

interface BookmarksTabProps {
  onOpenBookmark: (bookId: string, pageNumber: number, quoteText?: string) => void;
}

export const BookmarksTab: React.FC<BookmarksTabProps> = ({ onOpenBookmark }) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const { bookmarks, rename, remove } = useBookmarks();
  const [query, setQuery] = React.useState('');
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [editingName, setEditingName] = React.useState('');

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  const q = query.trim().toLowerCase();
  const filtered = bookmarks.filter(b =>
    !q || b.name.toLowerCase().includes(q) || (b.bookTitle || '').toLowerCase().includes(q)
  );

  const grouped = filtered.reduce<Record<string, typeof filtered>>((acc, bookmark) => {
    const key = bookmark.bookTitle || bookmark.bookId;
    (acc[key] ||= []).push(bookmark);
    return acc;
  }, {});

  const startEditing = (id: string, currentName: string) => {
    setEditingId(id);
    setEditingName(currentName);
  };

  const saveEditing = async () => {
    const trimmed = editingName.trim();
    if (editingId && trimmed) {
      await rename(editingId, trimmed);
    }
    setEditingId(null);
  };

  return (
    <div className="space-y-6">
      <div className="relative max-w-md">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('library.bookmarksTab.searchPlaceholder')}
          className="w-full ps-9 pe-3 py-2.5 rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 bg-white dark:bg-slate-900 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
        />
      </div>

      {bookmarks.length === 0 ? (
        <p className="text-center text-slate-400 dark:text-slate-500 py-20">{t('library.bookmarksTab.empty')}</p>
      ) : (
        <div className="space-y-8">
          {Object.entries(grouped).map(([bookTitle, group]) => (
            <div key={bookTitle}>
              <h4 className="font-bold text-[#1a1a1a] dark:text-slate-100 mb-2">{bookTitle}</h4>
              <ul className="space-y-2">
                {group.map(bookmark => (
                  <li key={bookmark.id} className="rounded-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 p-3">
                    {editingId === bookmark.id ? (
                      <div className="space-y-2">
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
                      <div className="flex items-center justify-between gap-2">
                        <button
                          onClick={() => onOpenBookmark(bookmark.bookId, bookmark.pageNumber, bookmark.quoteText ?? undefined)}
                          className="text-start flex-1"
                        >
                          <p className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100">{bookmark.name}</p>
                          {bookmark.quoteText && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">{bookmark.quoteText}</p>
                          )}
                        </button>
                        <button
                          onClick={() => startEditing(bookmark.id, bookmark.name)}
                          title={t('bookmarks.rename')}
                          className="p-1.5 rounded-lg text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10"
                        >
                          <Edit3 size={14} />
                        </button>
                        <button
                          onClick={() => remove(bookmark.id)}
                          title={t('bookmarks.delete')}
                          className="p-1.5 rounded-lg text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
