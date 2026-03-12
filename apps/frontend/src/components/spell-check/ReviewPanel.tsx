import React from 'react';
import { X, Check, Loader2, ClipboardList, AlertTriangle } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { PendingCorrection } from '../../hooks/usePendingCorrections';

interface ReviewPanelProps {
  pending: PendingCorrection[];
  isConfirming: boolean;
  confirmError: string | null;
  fontSize: number;
  onRemove: (id: string) => void;
  onClearAll: () => void;
  onConfirmAll: () => void;
  onClose: () => void;
}

export const ReviewPanel: React.FC<ReviewPanelProps> = ({
  pending,
  isConfirming,
  confirmError,
  fontSize,
  onRemove,
  onClearAll,
  onConfirmAll,
  onClose,
}) => {
  const { t } = useI18n();

  // Sort by addedAt (insertion order)
  const sorted = [...pending].sort((a, b) => a.addedAt - b.addedAt);
  const multiBook = new Set(sorted.map(p => p.bookId)).size > 1;

  return (
    <div className="h-full flex flex-col gap-3 animate-fade-in" dir="rtl">
      {/* Top bar */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <ClipboardList size={16} className="text-[#0369a1]" strokeWidth={2.5} />
          <span className="text-sm font-bold text-[#1a1a1a] uppercase tracking-wide">
            {t('spellCheck.reviewTitle')}
          </span>
          {pending.length > 0 && (
            <span className="px-2 py-0.5 bg-amber-500 text-white text-xs font-bold rounded-full">
              {pending.length}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-xl transition-all active:scale-95"
        >
          <X size={16} strokeWidth={2.5} />
        </button>
      </div>

      {/* Table or empty state */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {sorted.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-4 py-16 text-center h-full">
            <div className="p-5 bg-slate-50 rounded-[28px] shadow-inner text-slate-300">
              <Check size={32} strokeWidth={2.5} />
            </div>
            <p className="font-normal text-slate-400 uyghur-text" style={{ fontSize: `${fontSize}px` }}>
              {t('spellCheck.reviewEmpty')}
            </p>
            <p className="text-sm text-slate-300 uyghur-text leading-relaxed" style={{ fontSize: `${fontSize - 2}px` }}>
              {t('spellCheck.reviewEmptyNote')}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {/* Column headers */}
            <div className="flex items-center gap-2 px-3 py-1.5">
              <span className="w-12 text-[10px] font-bold text-slate-300 uppercase tracking-wider text-center flex-shrink-0">
                {t('spellCheck.reviewPage')}
              </span>
              <span className="flex-1 text-[10px] font-bold text-slate-300 uppercase tracking-wider text-right">
                {t('spellCheck.reviewOriginal')}
              </span>
              <span className="w-5 flex-shrink-0" />
              <span className="flex-1 text-[10px] font-bold text-slate-300 uppercase tracking-wider text-right">
                {t('spellCheck.reviewReplacement')}
              </span>
              <span className="w-8 flex-shrink-0" />
            </div>

            {sorted.map((correction) => (
              <div
                key={correction.id}
                className="flex items-center gap-2 px-3 py-3 bg-white/80 backdrop-blur-md border border-[#0369a1]/10 rounded-2xl shadow-sm"
              >
                {/* Page number (+ book title if multi-book) */}
                <div className="w-12 text-center flex-shrink-0 space-y-0.5">
                  <span className="block px-2 py-0.5 bg-[#0369a1]/10 text-[#0369a1] text-xs font-bold rounded-lg">
                    {correction.pageNum}
                  </span>
                  {multiBook && correction.bookTitle && (
                    <span className="block text-[9px] text-slate-300 truncate uyghur-text leading-tight">
                      {correction.bookTitle}
                    </span>
                  )}
                </div>

                {/* Original word */}
                <span
                  className="flex-1 text-red-500 font-semibold uyghur-text text-right truncate"
                  style={{ fontSize: `${fontSize}px` }}
                >
                  {correction.originalWord}
                </span>

                {/* Arrow */}
                <span className="w-5 flex-shrink-0 text-slate-300 text-center text-xs">←</span>

                {/* Replacement word */}
                <span
                  className="flex-1 text-[#0369a1] font-semibold uyghur-text text-right truncate"
                  style={{ fontSize: `${fontSize}px` }}
                >
                  {correction.correctedWord}
                </span>

                {/* Remove button */}
                <button
                  onClick={() => onRemove(correction.id)}
                  disabled={isConfirming}
                  className="w-8 h-8 flex items-center justify-center flex-shrink-0 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-xl transition-all disabled:opacity-30"
                  title={t('spellCheck.removeFromQueue')}
                >
                  <X size={14} strokeWidth={2.5} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom action bar */}
      <div className="flex-shrink-0 space-y-2">
        {/* Error banner */}
        {confirmError && (
          <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-2xl animate-fade-in">
            <AlertTriangle size={14} className="text-amber-500 flex-shrink-0" strokeWidth={2.5} />
            <p className="text-sm text-amber-700 font-normal uyghur-text flex-1" style={{ fontSize: `${fontSize - 2}px` }}>
              {t('spellCheck.confirmError', { count: pending.length })}
            </p>
          </div>
        )}

        <div className="flex gap-2">
          {pending.length > 0 && (
            <button
              onClick={onClearAll}
              disabled={isConfirming}
              className="px-5 py-2.5 bg-slate-100 text-slate-500 hover:bg-slate-200 rounded-2xl text-sm font-normal transition-all active:scale-95 disabled:opacity-40 uppercase"
            >
              {t('spellCheck.clearAll')}
            </button>
          )}
          <button
            onClick={onConfirmAll}
            disabled={isConfirming || pending.length === 0}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-[#0369a1] text-white rounded-2xl text-sm font-normal transition-all active:scale-95 disabled:opacity-40 shadow-lg shadow-[#0369a1]/20 hover:bg-[#0284c7] uppercase"
          >
            {isConfirming ? (
              <Loader2 size={16} strokeWidth={2.5} className="animate-spin" />
            ) : (
              <Check size={16} strokeWidth={2.5} />
            )}
            {t('spellCheck.confirmAll', { count: pending.length })}
          </button>
        </div>
      </div>
    </div>
  );
};
