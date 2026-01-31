import React from 'react';
import { Wand2, Check, X, Loader2 } from 'lucide-react';

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
  const getPendingCorrections = () => {
    if (!spellCheckResult) return [];
    return spellCheckResult.corrections.filter(
      (c) => !appliedCorrections.has(c.original) && !ignoredCorrections.has(c.original)
    );
  };

  const pendingCorrections = getPendingCorrections();

  return (
    <div className="w-[420px] bg-white border border-slate-200 rounded-2xl shadow-sm flex flex-col overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-100 bg-slate-50/50">
        <div className="flex items-center gap-2 mb-3">
          <Wand2 size={20} className="text-indigo-600" />
          <h3 className="font-bold text-slate-900">Spell Check</h3>
        </div>
        <button
          onClick={onRunSpellCheck}
          disabled={isChecking || !pageText.trim()}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-indigo-100"
        >
          {isChecking ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Checking...
            </>
          ) : (
            <>
              <Wand2 size={16} />
              Run Spell Check
            </>
          )}
        </button>
      </div>

      <div className="flex-grow overflow-y-auto p-4">
        {!spellCheckResult && !isChecking && (
          <div className="text-center py-12 text-slate-400">
            <Wand2 size={48} className="mx-auto mb-3 opacity-20" />
            <p className="text-sm">Click "Run Spell Check" to analyze this page</p>
          </div>
        )}

        {spellCheckResult && pendingCorrections.length === 0 && !isChecking && (
          <div className="text-center py-12 text-green-600">
            <Check size={48} className="mx-auto mb-3" />
            <p className="text-sm font-semibold">No spelling issues detected!</p>
          </div>
        )}

        {pendingCorrections.length > 0 && (
          <div className="space-y-4">
            <div className="text-xs font-bold text-slate-400 uppercase tracking-wide">
              {pendingCorrections.length} Issue{pendingCorrections.length !== 1 ? 's' : ''} Found
            </div>
            {pendingCorrections.map((correction, idx) => (
              <div
                key={idx}
                className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3 animate-in fade-in slide-in-from-bottom-2"
                style={{ animationDelay: `${idx * 50}ms` }}
              >
                <div>
                  <div className="text-red-600 font-bold text-lg uyghur-text" dir="rtl">
                    {correction.original}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    Page {pageNumber} · Confidence: {Math.round(correction.confidence * 100)}%
                  </div>
                  {correction.context && (
                    <div className="text-xs text-slate-500 mt-2 p-2 bg-white rounded border border-slate-100 uyghur-text" dir="rtl">
                      ...{correction.context}...
                    </div>
                  )}
                  <div className="text-xs text-slate-600 mt-2 italic">
                    {correction.reason}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">
                    Suggestion
                  </div>
                  <button
                    onClick={() => onApplyCorrection(correction)}
                    className="w-full flex items-center justify-between gap-2 px-3 py-2 bg-indigo-50 border border-indigo-200 text-indigo-700 text-sm font-semibold rounded-lg hover:bg-indigo-100 transition-colors group"
                  >
                    <span className="uyghur-text" dir="rtl">{correction.corrected}</span>
                    <Check size={16} className="text-indigo-400 group-hover:text-indigo-600" />
                  </button>
                  <button
                    onClick={() => onIgnoreCorrection(correction)}
                    className="w-full flex items-center justify-center gap-2 px-3 py-1.5 bg-slate-100 text-slate-600 text-xs font-semibold rounded-lg hover:bg-slate-200 transition-colors"
                  >
                    <X size={14} />
                    Ignore
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {spellCheckResult && (appliedCorrections.size > 0 || ignoredCorrections.size > 0) && (
        <div className="border-t border-slate-100 px-4 py-3 bg-slate-50/50">
          <div className="text-xs text-slate-500 flex items-center justify-between">
            <span>{appliedCorrections.size} applied</span>
            <span>{ignoredCorrections.size} ignored</span>
          </div>
        </div>
      )}
    </div>
  );
};
