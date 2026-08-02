import { RefreshCw, Search } from 'lucide-react';
import React from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { QuranAyah } from '../../services/searchTabsService';

interface QuranResultsListProps {
  items: QuranAyah[];
  isLoading: boolean;
  hasQuery: boolean;
  noResultsTitleKey?: string;
}

export const QuranResultsList: React.FC<QuranResultsListProps> = ({ items, isLoading, hasQuery, noResultsTitleKey }) => {
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
        <p className="text-[#1a1a1a] dark:text-slate-100 font-bold text-lg sm:text-xl mb-2 uyghur-text">{t(noResultsTitleKey || 'library.noResults.title')}</p>
        <p className="text-[#94a3b8] dark:text-slate-400 font-medium text-sm max-w-sm uyghur-text">{t('library.noResults.message')}</p>
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col gap-4">
      {items.map((ayah) => (
        <div
          key={ayah.id}
          className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 px-5 py-4 shadow-md"
        >
          <div className="flex items-center justify-between mb-3" dir="rtl">
            <span className="uyghur-text text-lg text-[#1a1a1a] dark:text-slate-100">{ayah.surahNameUg}</span>
            <span className="px-3 py-1 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-full text-xs">
              {ayah.surah}:{ayah.ayah}
            </span>
          </div>
          <p dir="rtl" className="arabic-text text-xl sm:text-2xl leading-loose text-[#1a1a1a] dark:text-slate-100 mb-3">
            {ayah.textAr}
          </p>
          <p dir="rtl" className="uyghur-text text-lg text-slate-600 dark:text-slate-300">
            {ayah.textUg}
          </p>
        </div>
      ))}
    </div>
  );
};
