import { RefreshCw, Search } from 'lucide-react';
import React from 'react';
import { useI18n } from '../../i18n/I18nContext';

export interface LookupItem {
  id: number | string;
  primary: string;
  secondary?: string | null;
}

interface LookupResultsListProps {
  items: LookupItem[];
  isLoading: boolean;
  hasQuery: boolean;
}

export const LookupResultsList: React.FC<LookupResultsListProps> = ({ items, isLoading, hasQuery }) => {
  const { t } = useI18n();

  if (isLoading && items.length === 0) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center gap-4">
        <RefreshCw className="w-8 h-8 text-[#0369a1] dark:text-[#38bdf8] animate-spin" />
        <span className="text-xs font-black text-[#0369a1] dark:text-[#38bdf8] uppercase">{t('common.loading')}</span>
      </div>
    );
  }

  if (!hasQuery) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center opacity-40">
        <Search size={40} strokeWidth={1} className="text-[#0369a1] dark:text-[#38bdf8] mb-4" />
        <p className="text-slate-500 dark:text-slate-400 uyghur-text">{t('home.searchPlaceholder')}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="w-full py-20 text-center glass-panel flex flex-col items-center justify-center rounded-[32px]">
        <p className="text-[#1a1a1a] dark:text-slate-100 font-normal text-lg sm:text-xl mb-2">{t('library.noResults.title')}</p>
        <p className="text-[#94a3b8] font-bold text-sm max-w-sm">{t('library.noResults.message')}</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col gap-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 px-5 py-4 shadow-md"
          dir="rtl"
        >
          <p className="text-base sm:text-lg font-normal text-[#1a1a1a] dark:text-slate-100 uyghur-text">{item.primary}</p>
          {item.secondary && (
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400 uyghur-text">{item.secondary}</p>
          )}
        </div>
      ))}
    </div>
  );
};
