import React from 'react';
import { X, Check, Loader2, ClipboardList, AlertTriangle, Book, Plus, Clock, RotateCcw, EyeOff, Sparkles } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { PendingCorrection } from '../../hooks/usePendingCorrections';

interface ReviewPanelProps {
  pending: PendingCorrection[];
  isConfirming: boolean;
  confirmError: string | null;
  fontSize: number;
  onRemove: (ids: string[]) => void;
  onClearAll: () => void;
  onConfirmAll: () => void;
  onClose: () => void;
  onUndoSkip: (issueId: number) => void;
  onToggleDictionary?: (id: string | string[]) => void;
  onToggleAutoCorrection?: (id: string | string[]) => void;
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
  onUndoSkip,
  onToggleDictionary,
  onToggleAutoCorrection,
}) => {
  const { t } = useI18n();

  // Sort by addedAt (insertion order)
  const sorted = [...pending].sort((a, b) => a.addedAt - b.addedAt);

  // 2. Build unique Global Rules list for display, including ALL matching IDs for demotion
  const uniqueGlobals = new Map<string, { item: PendingCorrection; ids: string[] }>();
  sorted.forEach(p => {
    const autoKey = `auto:${p.originalWord}:${p.correctedWord}`;
    const dictKey = `dict:${p.originalWord}:${p.correctedWord}`;
    
    if (p.isAutoCorrection) {
      const existing = uniqueGlobals.get(autoKey);
      if (existing) {
        existing.ids.push(p.id);
      } else {
        uniqueGlobals.set(autoKey, { item: p, ids: [p.id] });
      }
    } else if (p.isDictionaryAddition) {
      const existing = uniqueGlobals.get(dictKey);
      if (existing) {
        existing.ids.push(p.id);
      } else {
        uniqueGlobals.set(dictKey, { item: p, ids: [p.id] });
      }
    }
  });
  const globalRules = Array.from(uniqueGlobals.values()).sort((a, b) => {
    // Put Dictionary Additions at the top, then Auto-Corrections
    if (a.item.isDictionaryAddition && !b.item.isDictionaryAddition) return -1;
    if (!a.item.isDictionaryAddition && b.item.isDictionaryAddition) return 1;
    return a.item.addedAt - b.item.addedAt;
  });
  
  // 3. Group local rules, EXCLUDING those that are already covered by a global rule
  const localMap = new Map<string, { item: PendingCorrection; ids: string[] }>();
  sorted.filter(p => !uniqueGlobals.has(`auto:${p.originalWord}:${p.correctedWord}`) && 
                     !uniqueGlobals.has(`dict:${p.originalWord}:${p.correctedWord}`))
    .forEach(p => {
      const key = `${p.bookId}:${p.pageNum}:${p.originalWord}:${p.correctedWord}:${p.isIgnore}:${p.isSkip}`;
      const existing = localMap.get(key);
      if (existing) {
        existing.ids.push(p.id);
      } else {
        localMap.set(key, { item: p, ids: [p.id] });
      }
    });

  const localRules = Array.from(localMap.values());
  const multiBook = new Set(sorted.map(p => p.bookId)).size > 1;

  const renderTableHead = (pageLabel: string) => (
    <div className="flex items-center gap-2 px-3 py-1.5 border-b border-slate-100/50 mb-1">
      <span className="hidden lg:flex w-40 text-[10px] font-bold text-slate-400 uppercase tracking-wider text-start flex-shrink-0">
        {pageLabel}
      </span>
      <span className="flex-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider text-start">
        {t('spellCheck.reviewOriginal')}
      </span>
      <span className="w-8 flex-shrink-0" />
      <span className="flex-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider text-start">
        {t('spellCheck.reviewReplacement')}
      </span>
      <span className="w-16 flex-shrink-0" />
    </div>
  );

  const renderCorrectionRow = (correction: PendingCorrection, count?: number, options?: { hideToggles?: boolean; onRemove?: () => void }) => {
    const isCorrection = !correction.isIgnore && !correction.isSkip && !correction.isDictionaryAddition;
    const { hideToggles, onRemove: onRemoveOverride } = options || {};

    return (
      <div
        key={correction.id}
        className={`flex flex-col lg:flex-row lg:items-center gap-1.5 lg:gap-2 px-3 py-2.5 lg:py-3 border rounded-2xl shadow-sm transition-all ${
          correction.isSkip ? 'bg-slate-50 border-slate-200 opacity-80' : 
          correction.isIgnore ? 'bg-amber-50/50 border-amber-100' :
          correction.isDictionaryAddition ? 'bg-emerald-50/50 border-emerald-100' :
          'bg-white border-[#0369a1]/10'
        }`}
      >
        {/* Page Info */}
        <div className="flex lg:flex-col lg:w-40 flex-shrink-0 flex-row items-center lg:items-start justify-start lg:justify-center gap-2 lg:gap-1 pr-1 lg:border-l lg:border-slate-100/50 pl-2 border-b lg:border-b-0 pb-1.5 lg:pb-0 mb-1 lg:mb-0 border-slate-100/30">
          <div className="flex items-center gap-1.5">
            <span className="inline-block px-2 py-0.5 bg-[#0369a1]/10 text-[#0369a1] text-[10px] sm:text-xs font-bold rounded-lg whitespace-nowrap shrink-0">
              {correction.pageNum}-بەت
            </span>
            {count && count > 1 && (
              <span className="flex items-center justify-center min-w-[18px] h-[18px] px-1 bg-slate-400 text-white text-[9px] font-bold rounded-full shadow-sm">
                {count}
              </span>
            )}
          </div>
          {correction.bookTitle && (
            <span className="block text-[10px] text-slate-400 font-bold uyghur-text leading-tight w-full break-words lg:truncate">
              {correction.bookTitle}
            </span>
          )}
        </div>

        {/* Action Content wrapper for mobile alignment */}
        <div className="flex-1 flex items-center gap-2 w-full">
          {/* Original word */}
          <span
            className={`flex-1 font-semibold uyghur-text text-start break-words px-1 ${
              correction.isSkip ? 'text-slate-400' :
              correction.isIgnore ? 'text-amber-600' :
              'text-red-500'
            }`}
            style={{ fontSize: `${fontSize}px` }}
          >
            {correction.originalWord}
          </span>

          {/* Status indicator / Arrow */}
          <div className="w-8 flex-shrink-0 flex items-center justify-center">
            {isCorrection ? (
              <span className="text-slate-300 text-center text-xs">←</span>
            ) : (
              <div className="h-px w-4 bg-slate-200" />
            )}
          </div>

          {/* Replacement word or Action Category */}
          <div className="flex-1 flex items-center justify-start text-start px-1">
            {correction.isDictionaryAddition ? (
              <div className="flex items-center gap-1.5 text-emerald-600 font-bold uyghur-text">
                <Book size={14} strokeWidth={2.5} />
                <span className="text-xs">{t('spellCheck.reviewCategoryDictionary')}</span>
              </div>
            ) : correction.isIgnore ? (
              <div className="flex items-center gap-1.5 text-amber-600 font-bold uyghur-text">
                <EyeOff size={14} strokeWidth={2.5} />
                <span className="text-xs">{t('spellCheck.reviewCategoryIgnore')}</span>
              </div>
            ) : correction.isSkip ? (
              <div className="flex items-center gap-1.5 text-slate-500 font-bold uyghur-text">
                <Clock size={14} strokeWidth={2.5} />
                <span className="text-xs">{t('spellCheck.reviewCategorySkip')}</span>
              </div>
            ) : (
              <div className="flex flex-col items-start gap-1 w-full">
                <span
                  className="text-[#0369a1] font-semibold uyghur-text break-words w-full text-start"
                  style={{ fontSize: `${fontSize}px` }}
                >
                  {correction.correctedWord}
                </span>
                {correction.isAutoCorrection && (
                  <div className="flex items-center gap-1 px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded text-[9px] font-bold uppercase shrink-0 w-fit whitespace-nowrap">
                    <Sparkles size={10} strokeWidth={2.5} />
                    {t('spellCheck.reviewCategoryAuto')}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Actions (Toggle Dict/Auto + Remove) */}
        <div className="flex items-center justify-end gap-2 lg:gap-1 lg:w-16 flex-shrink-0 mt-3 lg:mt-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-100/40 lg:border-none w-full lg:w-auto">
          {!hideToggles && onToggleAutoCorrection && isCorrection && (
            <button
              onClick={() => onToggleAutoCorrection(correction.id)}
              disabled={isConfirming}
              className={`flex-1 lg:flex-none h-10 lg:w-8 lg:h-8 flex items-center justify-center gap-2 rounded-xl transition-all disabled:opacity-30 ${correction.isAutoCorrection ? 'text-purple-600 bg-purple-100' : 'text-slate-400 bg-slate-50 hover:bg-purple-50 hover:text-purple-600'}`}
              title={t('spellCheck.saveAsAutoCorrection')}
            >
              <Sparkles className="w-5 h-5 lg:w-[14px] lg:h-[14px]" strokeWidth={2.5} />
              <span className="lg:hidden text-[10px] font-bold uyghur-text">{t('spellCheck.reviewCategoryAutoLabel')}</span>
            </button>
          )}

          {!hideToggles && onToggleDictionary && (correction.isIgnore || correction.isDictionaryAddition) && (
            <button
              onClick={() => onToggleDictionary(correction.id)}
              disabled={isConfirming}
              className={`flex-1 lg:flex-none h-10 lg:w-8 lg:h-8 flex items-center justify-center gap-2 rounded-xl transition-all disabled:opacity-30 ${correction.isDictionaryAddition ? 'text-emerald-600 bg-emerald-100' : 'text-slate-400 bg-slate-50 hover:bg-emerald-50 hover:text-emerald-600'}`}
              title={t('spellCheck.addToDictionary')}
            >
              <Book className="w-5 h-5 lg:w-[14px] lg:h-[14px]" strokeWidth={2.5} />
              <span className="lg:hidden text-[10px] font-bold uyghur-text">{t('spellCheck.reviewCategoryDictionaryLabel')}</span>
            </button>
          )}

          <button
            onClick={() => {
              if (correction.isSkip) {
                onUndoSkip(correction.issueId);
              } else if (onRemoveOverride) {
                onRemoveOverride();
              } else {
                onRemove([correction.id]);
              }
            }}
            disabled={isConfirming}
            className="flex-1 lg:flex-none h-10 lg:w-8 lg:h-8 flex items-center justify-center gap-2 text-slate-400 bg-slate-50 hover:text-red-600 hover:bg-red-50 rounded-xl transition-all disabled:opacity-30"
          >
            {correction.isSkip ? (
              <>
                <RotateCcw className="w-5 h-5 lg:w-[14px] lg:h-[14px]" strokeWidth={2.5} />
                <span className="lg:hidden text-[10px] font-bold uyghur-text">{t('spellCheck.undoSkip')}</span>
              </>
            ) : (
              <>
                <X className="w-5 h-5 lg:w-[14px] lg:h-[14px]" strokeWidth={2.5} />
                <span className="lg:hidden text-[10px] font-bold uyghur-text">{t('spellCheck.removeFromQueueLabel')}</span>
              </>
            )}
          </button>
        </div>
      </div>
    );
  };

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
          <div className="space-y-6">
            {/* Global Rules Section */}
            {globalRules.length > 0 && (
              <div className="space-y-3 p-4 bg-purple-50/40 border border-purple-100/50 rounded-[32px] animate-fade-in shadow-sm">
                <div className="flex flex-col gap-1 px-1">
                  <div className="flex items-center gap-2 text-purple-600">
                    <div className="p-1.5 bg-purple-100 rounded-xl">
                      <Sparkles size={16} strokeWidth={2.5} />
                    </div>
                    <h3 className="text-sm font-bold uppercase tracking-wider uyghur-text">
                      {t('spellCheck.reviewGlobalRules')}
                    </h3>
                  </div>
                  <p className="text-[10px] text-purple-400 font-bold uyghur-text leading-tight mt-1 pl-1">
                    {t('spellCheck.eventualConsistencyNote')}
                  </p>
                </div>
                
                <div className="space-y-2">
                  {renderTableHead(t('spellCheck.reviewSamplePage'))}
                  {globalRules.map(({ item, ids }) => (
                    <div key={item.id}>
                      {renderCorrectionRow(item, ids.length, { 
                        hideToggles: true,
                        onRemove: () => {
                          if (item.isAutoCorrection) onToggleAutoCorrection?.(ids);
                          if (item.isDictionaryAddition) onToggleDictionary?.(ids);
                        }
                      })}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Local Rules Section */}
            {localRules.length > 0 && (
              <div className="space-y-3 p-4 bg-slate-50/40 border border-slate-100/50 rounded-[32px] animate-fade-in shadow-sm">
                <div className="flex items-center gap-2 px-1 text-slate-500">
                  <div className="p-1.5 bg-slate-100 rounded-xl">
                    <ClipboardList size={16} strokeWidth={2.5} />
                  </div>
                  <h3 className="text-sm font-bold uppercase tracking-wider uyghur-text">
                    {t('spellCheck.reviewLocalRules')}
                  </h3>
                </div>

                <div className="space-y-2">
                  {renderTableHead(t('spellCheck.reviewPage'))}
                  {localRules.map(({ item, ids }) => (
                    <div key={item.id}>
                      {renderCorrectionRow(item, ids.length, {
                        onRemove: () => onRemove(ids)
                      })}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom action bar */}
      <div className="flex-shrink-0 space-y-2">
        {/* Error banner */}
        {confirmError && (
          <div className="flex items-center gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-2xl animate-fade-in">
            <AlertTriangle size={14} className="text-amber-500 flex-shrink-0" strokeWidth={2.5} />
            <p className="font-normal uyghur-text leading-relaxed text-amber-700 flex-1" style={{ fontSize: `${fontSize - 2}px` }}>
              {confirmError.toLowerCase().match(/failed|error|returned|denied|unauthorized/) ? (
                <>
                  {t('spellCheck.confirmError', { count: pending.length })}
                  <span className="block text-[10px] opacity-60 mt-0.5 font-sans" dir="ltr">({confirmError})</span>
                </>
              ) : confirmError}
            </p>
          </div>
        )}

        <div className="flex gap-2">
          {pending.length > 0 && (
            <button
              onClick={onClearAll}
              disabled={isConfirming}
              className="px-5 py-2.5 bg-slate-100 text-slate-500 hover:bg-slate-200 rounded-2xl text-sm font-normal transition-all active:scale-95 disabled:opacity-40 uppercase whitespace-nowrap shrink-0"
            >
              {t('spellCheck.clearAll')}
            </button>
          )}
          <button
            onClick={onConfirmAll}
            disabled={isConfirming || pending.length === 0}
            className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-[#0369a1] text-white rounded-2xl text-sm font-normal transition-all active:scale-95 disabled:opacity-40 shadow-lg shadow-[#0369a1]/20 hover:bg-[#0284c7] uppercase whitespace-nowrap"
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
