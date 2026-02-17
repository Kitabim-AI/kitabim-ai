import React from 'react';
import { Wand2, Check, X, Loader2 } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

export interface SpellCorrection {
  original: string;
  corrected: string;
  position?: number;
  confidence: number;
  reason: string;
  context?: string;
}

export interface SpellCheckResult {
  bookId: string;
  pageNumber: number;
  corrections: SpellCorrection[];
  totalIssues: number;
  checkedAt: string;
}

interface SpellCheckPanelProps {
  bookId: string;
  pageNumber: number;
  pageText: string;
  isChecking: boolean;
  spellCheckResult: SpellCheckResult | null;
  onRunSpellCheck: () => void;
  onApplyCorrection: (correction: SpellCorrection) => void;
  onIgnoreCorrection: (correction: SpellCorrection) => void;
  appliedCorrections: Set<string>;
  ignoredCorrections: Set<string>;
}

export const SpellCheckPanel: React.FC<SpellCheckPanelProps> = ({
  bookId,
  pageNumber,
  pageText,
  isChecking,
  spellCheckResult,
  onRunSpellCheck,
  onApplyCorrection,
  onIgnoreCorrection,
  appliedCorrections,
  ignoredCorrections,
}) => {
  const { t } = useI18n();
  const getPendingCorrections = () => {
    if (!spellCheckResult) return [];
    return spellCheckResult.corrections.filter(
      (c) => !appliedCorrections.has(c.original) && !ignoredCorrections.has(c.original)
    );
  };

  const pendingCorrections = getPendingCorrections();

  return (
    <div className="h-full flex flex-col gap-6 animate-fade-in relative" dir="rtl">
      {/* Header */}
      <div className="bg-white/60 backdrop-blur-xl p-6 flex flex-col gap-5 border border-[#75C5F0]/10 shadow-sm" style={{ borderRadius: '28px' }}>
        <div className="flex items-center gap-4">
          <div className="p-3 bg-[#e8f4f8] text-[#75C5F0] rounded-2xl shadow-xl shadow-[#75C5F0]/5">
            <Wand2 size={24} strokeWidth={2.5} />
          </div>
          <div>
            <h3 className="text-xl font-black text-[#1a1a1a]">{t('spellCheck.title')}</h3>
            <p className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.1em]">{t('spellCheck.subtitle')}</p>
          </div>
        </div>

        <button
          onClick={onRunSpellCheck}
          disabled={isChecking || !pageText.trim()}
          className="w-full flex items-center justify-center gap-4 px-6 py-4 bg-[#75C5F0] text-white rounded-2xl font-black text-sm transition-all active:scale-95 shadow-xl shadow-[#75C5F0]/20 disabled:opacity-30 disabled:grayscale group"
        >
          {isChecking ? (
            <>
              <Loader2 size={18} className="animate-spin" strokeWidth={3} />
              {t('spellCheck.checking')}
            </>
          ) : (
            <>
              <Wand2 size={18} className="group-hover:rotate-12 transition-transform" strokeWidth={3} />
              {t('spellCheck.runCheck')}
            </>
          )}
        </button>
      </div>

      {/* Body */}
      <div className="flex-grow overflow-y-auto space-y-6 px-2 custom-scrollbar-mini py-4">
        {!spellCheckResult && !isChecking && (
          <div className="text-center py-24 flex flex-col items-center gap-6 opacity-30 group">
            <div className="p-8 bg-[#e8f4f8] rounded-[40px] transition-all group-hover:scale-110">
              <Wand2 size={48} className="text-[#75C5F0]" strokeWidth={1} />
            </div>
            <p className="text-sm font-black text-[#1a1a1a] tracking-widest uppercase">{t('spellCheck.clickTip')}</p>
          </div>
        )}

        {isChecking && (
          <div className="text-center py-24 flex flex-col items-center gap-6">
            <div className="relative">
              <div className="w-16 h-16 border-4 border-[#e8f4f8] border-t-[#75C5F0] rounded-full animate-spin"></div>
              <div className="absolute inset-0 flex items-center justify-center text-[#75C5F0]">
                <Wand2 size={24} className="animate-pulse" />
              </div>
            </div>
            <p className="text-sm font-black text-[#1a1a1a] tracking-widest uppercase animate-pulse">{t('spellCheck.analyzing')}</p>
          </div>
        )}

        {spellCheckResult && pendingCorrections.length === 0 && !isChecking && (
          <div className="text-center py-24 flex flex-col items-center gap-6 animate-fade-in">
            <div className="p-8 bg-emerald-50 text-emerald-500 rounded-[40px] shadow-lg shadow-emerald-100">
              <Check size={48} strokeWidth={3} />
            </div>
            <p className="text-lg font-black text-[#1a1a1a]">{t('spellCheck.noErrors')}</p>
            <p className="text-sm font-bold text-[#94a3b8] px-10 leading-loose">{t('spellCheck.noErrorsDetail')}</p>
          </div>
        )}

        {pendingCorrections.length > 0 && (
          <div className="space-y-5 animate-fade-in">
            <div className="flex items-center gap-3 px-2">
              <span className="w-2 h-2 bg-red-400 rounded-full animate-ping" />
              <div className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.2em]">
                {t('spellCheck.errorsCount', { count: pendingCorrections.length })}
              </div>
            </div>

            {pendingCorrections.map((correction, idx) => (
              <div
                key={idx}
                className="bg-white/80 backdrop-blur-md border border-[#75C5F0]/10 rounded-3xl p-6 space-y-5 shadow-sm hover:shadow-xl hover:shadow-[#75C5F0]/5 transition-all group animate-fade-in"
                style={{ animationDelay: `${idx * 0.1}s` }}
              >
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="text-red-500 font-black text-2xl uyghur-text leading-tight group-hover:scale-105 origin-right transition-transform">
                      {correction.original}
                    </div>
                    <div className="text-[14px] font-black text-slate-300 uppercase tracking-widest">
                      {t('spellCheck.confidence', { percent: Math.round(correction.confidence * 100) })}
                    </div>
                  </div>

                  {correction.context && (
                    <div className="p-4 bg-[#f8fafc] rounded-2xl border border-slate-100 uyghur-text text-sm leading-loose text-slate-500 italic relative overflow-hidden">
                      <div className="absolute top-0 right-0 w-1 h-full bg-[#75C5F0]/30" />
                      ...{correction.context}...
                    </div>
                  )}

                  <div className="text-sm font-bold text-slate-400 leading-relaxed px-1">
                    {correction.reason}
                  </div>
                </div>

                <div className="grid grid-cols-1 gap-2">
                  <span className="text-[14px] font-black text-slate-300 uppercase tracking-widest px-1">{t('spellCheck.suggestion')}</span>
                  <button
                    onClick={() => onApplyCorrection(correction)}
                    className="flex items-center justify-between px-6 py-4 bg-[#75C5F0] text-white rounded-2xl font-black text-lg transition-all active:scale-95 shadow-lg shadow-[#75C5F0]/10 hover:shadow-xl hover:shadow-[#75C5F0]/20"
                  >
                    <span className="uyghur-text">{correction.corrected}</span>
                    <Check size={20} strokeWidth={3} />
                  </button>
                  <button
                    onClick={() => onIgnoreCorrection(correction)}
                    className="flex items-center justify-center gap-3 px-6 py-3 bg-slate-50 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-2xl font-black text-sm transition-all active:scale-95 uppercase tracking-widest"
                  >
                    <X size={14} strokeWidth={3} />
                    {t('spellCheck.ignore')}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {spellCheckResult && (appliedCorrections.size > 0 || ignoredCorrections.size > 0) && (
        <div className="bg-white/40 backdrop-blur-md px-6 py-4 border border-[#75C5F0]/5 flex items-center justify-between text-[14px] font-black text-[#94a3b8] uppercase tracking-widest" style={{ borderRadius: '20px' }}>
          <span>{t('spellCheck.applied')}: <span className="text-[#1a1a1a]">{appliedCorrections.size}</span></span>
          <div className="w-1 h-1 bg-slate-200 rounded-full" />
          <span>{t('spellCheck.ignored')}: <span className="text-[#1a1a1a]">{ignoredCorrections.size}</span></span>
        </div>
      )}
    </div>
  );
};
