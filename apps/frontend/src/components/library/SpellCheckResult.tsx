import { CheckCircle2, RefreshCw, Search, XCircle } from 'lucide-react';
import React from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { SpellingCheckResult } from '../../services/searchTabsService';

interface SpellCheckResultProps {
  result: SpellingCheckResult | null;
  isLoading: boolean;
  hasQuery: boolean;
}

export const SpellCheckResultView: React.FC<SpellCheckResultProps> = ({ result, isLoading, hasQuery }) => {
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center gap-4">
        <RefreshCw className="w-8 h-8 text-[#0369a1] dark:text-[#38bdf8] animate-spin" />
        <span className="text-xs font-black text-[#0369a1] dark:text-[#38bdf8] uppercase">{t('common.loading')}</span>
      </div>
    );
  }

  if (!hasQuery || !result) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center opacity-40">
        <Search size={40} strokeWidth={1} className="text-[#0369a1] dark:text-[#38bdf8] mb-4" />
        <p className="text-slate-500 dark:text-slate-400 uyghur-text">{t('home.searchPlaceholder')}</p>
      </div>
    );
  }

  return (
    <div className="w-full max-w-3xl mx-auto flex flex-col gap-4" dir="rtl">
      <div
        className={`flex items-center gap-3 px-5 py-4 rounded-2xl border shadow-md ${
          result.isKnown
            ? 'bg-emerald-50/80 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/20'
            : 'bg-amber-50/80 dark:bg-amber-500/10 border-amber-200 dark:border-amber-500/20'
        }`}
      >
        {result.isKnown ? (
          <CheckCircle2 className="w-6 h-6 text-emerald-600 dark:text-emerald-400 flex-shrink-0" />
        ) : (
          <XCircle className="w-6 h-6 text-amber-600 dark:text-amber-400 flex-shrink-0" />
        )}
        <p className="uyghur-text text-base sm:text-lg text-[#1a1a1a] dark:text-slate-100">
          {t(result.isKnown ? 'home.spellCheck.known' : 'home.spellCheck.unknown', { word: result.word || '' })}
        </p>
      </div>

      {!result.isKnown && result.suggestions.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-black text-[#94a3b8] uppercase px-1">{t('home.spellCheck.suggestions')}</p>
          {result.suggestions.map((s) => (
            <div
              key={s.id}
              className="bg-white/70 dark:bg-slate-900/70 backdrop-blur-xl rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 px-5 py-3 shadow-sm"
            >
              <p className="uyghur-text text-base text-[#1a1a1a] dark:text-slate-100">{s.word}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
