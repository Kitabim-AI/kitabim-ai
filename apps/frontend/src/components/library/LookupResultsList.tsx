import { RefreshCw, Search, Share2 } from 'lucide-react';
import React, { useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { parseDefinition } from '../../utils/uyghurAlphabet';
import { ShareSearchResultModal } from '../share/ShareSearchResultModal';

export interface LookupItem {
  id: number | string;
  primary: string;
  secondary?: string | null;
  primaryClassName?: string;
  secondaryClassName?: string;
  primaryDir?: 'rtl' | 'ltr' | 'auto';
  secondaryDir?: 'rtl' | 'ltr' | 'auto';
  excludeSecondaryOnShare?: boolean;
  badge?: {
    text: string;
    variant?: 'ai' | 'web';
  };
}

interface LookupResultsListProps {
  items: LookupItem[];
  isLoading: boolean;
  hasQuery: boolean;
  noResultsTitleKey?: string;
}

export const LookupResultsList: React.FC<LookupResultsListProps> = ({ items, isLoading, hasQuery, noResultsTitleKey }) => {
  const { t } = useI18n();
  const [shareItem, setShareItem] = useState<LookupItem | null>(null);

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
          className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 px-5 py-4 shadow-md flex flex-col gap-2"
          dir="rtl"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <p
                className={item.primaryClassName ?? 'text-base font-bold text-[#1a1a1a] dark:text-slate-100 uyghur-text'}
                dir={item.primaryDir}
              >
                {item.primary}
              </p>
              {item.badge && (
                <span
                  className={`px-2 py-0.5 rounded-md text-[11px] font-bold font-sans tracking-wide uppercase border ${
                    item.badge.variant === 'ai'
                      ? 'bg-sky-500/10 text-[#0369a1] dark:text-[#38bdf8] border-[#0369a1]/20 dark:border-[#38bdf8]/20'
                      : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
                  }`}
                >
                  {item.badge.text}
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={() => setShareItem(item)}
              className="p-1.5 text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] rounded-lg transition-colors"
              title={t('share.shareSearchResult')}
            >
              <Share2 size={16} strokeWidth={2} />
            </button>
          </div>

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
                return <span key={idx}>{chunk.content}</span>;
              })}
            </p>
          )}
        </div>
      ))}

      {shareItem && (
        <ShareSearchResultModal
          title={shareItem.primary}
          content={shareItem.excludeSecondaryOnShare ? '' : (shareItem.secondary || '')}
          onClose={() => setShareItem(null)}
        />
      )}
    </div>
  );
};
