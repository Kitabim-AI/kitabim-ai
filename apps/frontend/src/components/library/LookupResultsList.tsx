import { RefreshCw, Search } from 'lucide-react';
import React from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { highlightText } from '../../utils/highlightText';
import { parseDefinition } from '../../utils/uyghurAlphabet';

export interface LookupItem {
  id: number | string;
  primary: string;
  secondary?: string | null;
  primaryClassName?: string;
  secondaryClassName?: string;
  primaryDir?: 'rtl' | 'ltr' | 'auto';
  secondaryDir?: 'rtl' | 'ltr' | 'auto';
}

interface LookupResultsListProps {
  items: LookupItem[];
  isLoading: boolean;
  hasQuery: boolean;
  query: string;
  noResultsTitleKey?: string;
}

export const LookupResultsList: React.FC<LookupResultsListProps> = ({ items, isLoading, hasQuery, query, noResultsTitleKey }) => {
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
      <div className="w-full py-12 sm:py-20 px-6 sm:px-8 text-center glass-panel flex flex-col items-center justify-center rounded-[32px]">
        <p className="text-[#1a1a1a] dark:text-slate-100 font-bold text-lg sm:text-xl mb-2 uyghur-text max-w-md">{t(noResultsTitleKey || 'library.noResults.title')}</p>
        <p className="text-[#94a3b8] dark:text-slate-400 font-medium text-sm max-w-sm uyghur-text">{t('library.noResults.message')}</p>
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col gap-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 px-5 py-4 shadow-md"
          dir="rtl"
        >
          <p
            className={item.primaryClassName ?? 'text-base font-bold text-[#1a1a1a] dark:text-slate-100 uyghur-text'}
            dir={item.primaryDir}
          >
            {highlightText(item.primary, query)}
          </p>
          {item.secondary && (
            <p
              className={item.secondaryClassName ?? 'mt-1 text-base text-slate-500 dark:text-slate-400 uyghur-text whitespace-pre-wrap'}
              dir={item.secondaryDir}
            >
              {parseDefinition(item.secondary).map((chunk, idx) => {
                if (chunk.type === 'br') {
                  return <br key={idx} />;
                }
                if (chunk.type === 'metadata') {
                  return (
                    <strong key={idx} className="font-bold text-slate-800 dark:text-slate-200">
                      {chunk.content}
                    </strong>
                  );
                }
                return <span key={idx}>{highlightText(chunk.content, query)}</span>;
              })}
            </p>
          )}
        </div>
      ))}
    </div>
  );
};
