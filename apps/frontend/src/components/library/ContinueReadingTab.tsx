import { Search } from 'lucide-react';
import { ReadingProgressEntry } from '@shared/types';
import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { GuestAuthWall } from '../reader/GuestAuthWall';

interface ContinueReadingTabProps {
  onOpenBook: (bookId: string) => void;
}

export const ContinueReadingTab: React.FC<ContinueReadingTabProps> = ({ onOpenBook }) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const [items, setItems] = React.useState<ReadingProgressEntry[]>([]);
  const [query, setQuery] = React.useState('');

  React.useEffect(() => {
    if (!isAuthenticated) return;
    PersistenceService.listReadingProgress().then(setItems);
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  const filtered = items.filter(item =>
    (item.bookTitle || '').toLowerCase().includes(query.trim().toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="relative max-w-md">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-slate-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('library.continueReading.searchPlaceholder')}
          className="w-full ps-9 pe-3 py-2.5 rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 bg-white dark:bg-slate-900 text-sm text-[#1a1a1a] dark:text-slate-100 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
        />
      </div>

      {items.length === 0 ? (
        <p className="text-center text-slate-400 dark:text-slate-500 py-20">{t('library.continueReading.empty')}</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-6">
          {filtered.map(item => (
            <button
              key={item.bookId}
              onClick={() => onOpenBook(item.bookId)}
              className="text-start rounded-2xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 p-4 hover:shadow-lg transition-all bg-white dark:bg-slate-900"
            >
              <p className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100 truncate">{item.bookTitle}</p>
              <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
                {t('chat.pageNumber', { page: item.pageNumber })}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};
