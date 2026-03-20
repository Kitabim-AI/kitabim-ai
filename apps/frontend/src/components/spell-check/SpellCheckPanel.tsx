import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  BookOpenCheck, BookOpen, Check, X, RefreshCw, Clock, RotateCcw, Inbox, FileText, ChevronRight, ChevronLeft, Loader2, Plus
} from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { SpellIssue } from '../../hooks/useSpellCheck';
import { MarkdownContent } from '../common/MarkdownContent';
import { useNotification } from '../../context/NotificationContext';
import { useIsAdmin } from '../../hooks/useAuth';
import { PersistenceService } from '../../services/persistenceService';

interface SpellCheckPanelProps {
  pageNumber: number;
  totalPages?: number;
  pageText?: string;
  fontSize: number;
  issues: SpellIssue[];
  isLoading: boolean;
  isScanning: boolean;
  hasLoaded: boolean;
  navigationMode?: 'auto' | 'manual';
  onAddPending: (issueId: number, correctedWord: string, originalWord: string, options?: { isPhrase?: boolean; range?: [number, number]; isAutoCorrection?: boolean; isDictionaryAddition?: boolean; isIgnore?: boolean; isSkip?: boolean }) => void | Promise<void>;
  pendingIssueIds: number[];
  onRemoveFromPending?: (issueId: number) => void;
  skippedIds: number[];
  onToggleSkip: (issueId: number) => void;
  onNextPage: () => void;
  onPrevPage?: () => void;
  globalIssueOffset?: number;
  totalBookIssues?: number;
  bookTitle?: string;
  bookAuthor?: string | null;
}

function extractContext(
  pageText: string,
  charOffset: number | null,
  charEnd: number | null,
): { before: string; word: string; after: string; contextStart: number; contextEnd: number } | null {
  if (charOffset === null || charEnd === null || charOffset < 0) return null;
  if (charOffset >= charEnd) return null;
  const safeEnd = Math.min(charEnd, pageText.length);
  if (charOffset >= safeEnd) return null;
  const word = pageText.slice(charOffset, safeEnd);
  if (!word.trim()) return null;
  const beforeText = pageText.slice(0, charOffset);
  const afterText = pageText.slice(safeEnd);
  const beforeSlice = beforeText.split(/(\s+)/).filter(Boolean).slice(-40).join('');
  const afterSlice = afterText.split(/(\s+)/).filter(Boolean).slice(0, 40).join('');
  return {
    before: beforeSlice,
    word,
    after: afterSlice,
    contextStart: charOffset - beforeSlice.length,
    contextEnd: safeEnd + afterSlice.length,
  };
}

export const SpellCheckPanel: React.FC<SpellCheckPanelProps> = ({
  pageNumber,
  totalPages,
  pageText,
  fontSize,
  issues,
  isLoading,
  isScanning,
  hasLoaded,
  navigationMode = 'auto',
  onAddPending,
  pendingIssueIds,
  onRemoveFromPending,
  onNextPage,
  onPrevPage,
  globalIssueOffset = 0,
  totalBookIssues,
  bookTitle,
  bookAuthor,
  skippedIds,
  onToggleSkip,
}) => {
  const { t } = useI18n();
  const { addNotification } = useNotification();
  const isAdmin = useIsAdmin();

  const [activeIssueId, setActiveIssueId] = useState<number | null>(null);
  const [customInput, setCustomInput] = useState('');
  const [showPageModal, setShowPageModal] = useState(false);
  
  const [isIgnoring, setIsIgnoring] = useState(false);
  const [isApplying, setIsApplying] = useState<string | null>(null);

  const wordRef = useRef<HTMLSpanElement>(null);
  const lastKnownIndexRef = useRef(0);
  const autoAdvanceTriggered = useRef(false);
  const prevPendingLengthRef = useRef(pendingIssueIds.length);

  // ROOT CAUSE PROTECTION: Track ready state and busy transitions
  const isBusy = isLoading || isScanning || isApplying !== null || isIgnoring;
  const [readyToAdvance, setReadyToAdvance] = useState(false);
  const wasBusyRef = useRef(isBusy);

  const stepperIndex = activeIssueId !== null
    ? Math.max(0, issues.findIndex(i => i.id === activeIssueId))
    : 0;
  const activeIssue = issues.length > 0 ? (issues[stepperIndex] ?? issues[0]) : null;
  const isActiveSkipped = activeIssue ? skippedIds.includes(activeIssue.id) : false;
  const nonSkippedIssues = issues.filter((i: SpellIssue) => !skippedIds.includes(i.id) && !pendingIssueIds.includes(i.id));

  useEffect(() => {
    setActiveIssueId(null);
    setCustomInput('');
    autoAdvanceTriggered.current = false;
    setReadyToAdvance(false);
  }, [pageNumber]);

  useEffect(() => {
    if (issues.length === 0) {
      setActiveIssueId(null);
      return;
    }
    if (activeIssueId === null) {
      const first = issues.find(i => !skippedIds.includes(i.id));
      setActiveIssueId(first?.id ?? issues[0].id);
    } else if (!issues.find(i => i.id === activeIssueId)) {
      const targetIdx = Math.min(lastKnownIndexRef.current, issues.length - 1);
      const forward = issues.slice(targetIdx).find(i => !skippedIds.includes(i.id));
      const backward = forward ?? issues.slice(0, targetIdx).find(i => !skippedIds.includes(i.id));
      setActiveIssueId(backward?.id ?? issues[targetIdx]?.id ?? null);
    }
  }, [issues.length]);

  useEffect(() => {
    const added = pendingIssueIds.length > prevPendingLengthRef.current;
    prevPendingLengthRef.current = pendingIssueIds.length;
    if (!added || !activeIssueId) return;
    if (!pendingIssueIds.includes(activeIssueId)) return;
    const currentIdx = issues.findIndex(i => i.id === activeIssueId);
    const searchOrder = [...issues.slice(currentIdx + 1), ...issues.slice(0, currentIdx)];
    const next = searchOrder.find((i: SpellIssue) => !skippedIds.includes(i.id) && !pendingIssueIds.includes(i.id));
    if (next) setActiveIssueId(next.id);
  }, [pendingIssueIds.length]);

  useEffect(() => {
    const idx = issues.findIndex(i => i.id === activeIssueId);
    if (idx >= 0) lastKnownIndexRef.current = idx;
  }, [activeIssueId, issues]);

  useEffect(() => {
    if (!activeIssueId || !wordRef.current) return;
    const timer = setTimeout(() => {
      wordRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 60);
    return () => clearTimeout(timer);
  }, [activeIssueId]);

  // ROOT CAUSE FIX: Only allow advancement after a busy cycle completes
  useEffect(() => {
    if (!isBusy && wasBusyRef.current) {
      const timer = setTimeout(() => setReadyToAdvance(true), 400);
      return () => clearTimeout(timer);
    }
    wasBusyRef.current = isBusy;
  }, [isBusy]);

  useEffect(() => {
    if (navigationMode !== 'auto') return;
    if (!hasLoaded || isBusy || !readyToAdvance || nonSkippedIssues.length > 0) return;
    if (autoAdvanceTriggered.current) return;

    autoAdvanceTriggered.current = true;
    
    const timer = setTimeout(() => {
      onNextPage();
    }, 100);
    return () => clearTimeout(timer);
  }, [hasLoaded, isBusy, nonSkippedIssues.length, navigationMode, readyToAdvance, onNextPage]);


  const handleUndoSkip = (issueId: number) => {
    onToggleSkip(issueId);
    setActiveIssueId(issueId);
  };

  const handleOcrApply = async (correction: string) => {
    if (!activeIssue) return;
    const options = activeIssue.char_offset !== null && activeIssue.char_end !== null
      ? { range: [activeIssue.char_offset, activeIssue.char_end] as [number, number] }
      : {};
    
    setIsApplying(correction);
    await onAddPending(activeIssue.id, correction, activeIssue.word, options);
    await new Promise(resolve => setTimeout(resolve, 300));
    setIsApplying(null);
  };

  const handleCustomApply = async () => {
    const val = customInput.trim();
    if (!val || !activeIssue) return;
    const options = activeIssue.char_offset !== null && activeIssue.char_end !== null
      ? { range: [activeIssue.char_offset, activeIssue.char_end] as [number, number] }
      : {};
    
    setIsApplying('custom');
    await onAddPending(activeIssue.id, val, activeIssue.word, options);
    await new Promise(resolve => setTimeout(resolve, 300));
    setCustomInput('');
    setIsApplying(null);
  };

  const handleIgnore = async (issueId: number) => {
    if (!activeIssue) return;
    setIsIgnoring(true);
    await onAddPending(issueId, activeIssue.word, activeIssue.word, { isIgnore: true });
    await new Promise(resolve => setTimeout(resolve, 300));
    setIsIgnoring(false);
  };


  const ctx = activeIssue && pageText
    ? extractContext(pageText, activeIssue.char_offset, activeIssue.char_end)
    : null;

  const renderPanelHeader = () => {
    return (
      <div className="flex items-center justify-between px-1 sm:px-2 gap-3 flex-shrink-0 mb-2">
        <div className="flex items-center gap-2 sm:gap-3">
          {issues.length > 0 && (
            <span className="px-3 py-1.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl text-[10px] sm:text-xs font-bold whitespace-nowrap">
              {t('spellCheck.findingProgress', {
                current: globalIssueOffset + stepperIndex + 1,
                total: totalBookIssues ?? issues.length,
              })}
            </span>
          )}
          {pageText !== undefined && (
            <button
              onClick={() => setShowPageModal(true)}
              className="text-[10px] font-bold text-slate-400 px-3 py-1.5 bg-slate-100 rounded-xl hover:bg-slate-200 transition-all uppercase flex items-center gap-1.5 whitespace-nowrap"
            >
              <FileText size={12} />
              {t('spellCheck.viewPage')} ({t('chat.pageNumber', { page: pageNumber })})
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderContextSection = () => {
    if (!activeIssue) return null;
    if (pageText === undefined) {
      return (
        <div className="space-y-2">
          <div className="h-4 bg-slate-100 rounded-xl animate-pulse" style={{ height: `${fontSize + 4}px` }} />
          <div className="h-4 bg-slate-100 rounded-xl animate-pulse w-3/4" style={{ height: `${fontSize + 4}px` }} />
        </div>
      );
    }
    if (!ctx) {
      return (
        <div className="text-red-500 font-semibold uyghur-text leading-loose" style={{ fontSize: `${fontSize}px` }}>
          {activeIssue.word}
        </div>
      );
    }
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">{t('chat.referenceTitle')}</span>
        </div>
        <div className="uyghur-text leading-loose text-[#1a1a1a] whitespace-pre-wrap animate-fade-in" dir="rtl" style={{ fontSize: `${fontSize}px` }}>
          {ctx.before && <span>{ctx.before}</span>}
          <span ref={wordRef} className="text-red-500 font-semibold bg-red-50 rounded px-0.5">{ctx.word}</span>
          {ctx.after && <span>{ctx.after}</span>}
        </div>
      </div>
    );
  };

  const renderSkippedCard = () => {
    if (!activeIssue) return null;
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-3xl p-5 space-y-4 animate-fade-in">
        <div className="flex items-center justify-between">
          <span className="text-sm font-bold text-slate-400 uyghur-text" style={{ fontSize: `${fontSize}px` }}>
            {activeIssue.word}
          </span>
          <span className="text-[10px] font-bold text-slate-300 uppercase px-2 py-1 bg-slate-100 rounded-lg">
            {t('spellCheck.skipLater')}
          </span>
        </div>
        <button
          onClick={() => handleUndoSkip(activeIssue.id)}
          className="w-full flex items-center justify-center gap-2 px-5 py-2.5 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-2xl text-sm font-bold transition-all active:scale-95"
        >
          <RotateCcw size={14} strokeWidth={2.5} />
          {t('spellCheck.undoSkip')}
        </button>
      </div>
    );
  };

  const renderActiveCard = () => {
    if (!activeIssue) return null;
    
    const isPending = pendingIssueIds.includes(activeIssue.id);
    const isSkipped = skippedIds.includes(activeIssue.id);

    // If we've already dealt with this issue on this page, show a small loader 
    // while the selection logic or auto-advance logic catches up.
    if (isPending || isSkipped) {
      return (
        <div className="bg-white/80 backdrop-blur-md border border-[#0369a1]/10 rounded-3xl p-16 shadow-sm animate-fade-in flex flex-col items-center justify-center gap-4">
          <Loader2 size={32} className="animate-spin text-[#0369a1]/40" strokeWidth={2} />
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            {isPending ? t('spellCheck.applying') : t('spellCheck.skipping')}
          </p>
        </div>
      );
    }

    const suggestions = activeIssue.ocr_corrections || [];

    return (
      <div className="bg-white/80 backdrop-blur-md border border-[#0369a1]/10 rounded-3xl p-4 sm:p-6 shadow-sm animate-fade-in flex flex-col gap-4">
        {renderContextSection()}
        <div className="flex flex-col gap-5 mt-4">
            <div className="flex flex-col gap-2 relative z-10">
              {suggestions.length > 0 && (
                <div className="flex flex-col gap-1.5 mb-1">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-1">
                    {t('spellCheck.suggestion')}
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {suggestions.map((correction) => (
                      <button
                        key={correction}
                        onClick={() => { setCustomInput(correction); handleCustomApply(); }}
                        disabled={isBusy || isApplying !== null}
                        className="px-3 py-1.5 bg-slate-100 text-slate-600 hover:bg-[#0369a1] hover:text-white rounded-xl text-xs sm:text-sm font-bold transition-all shadow-sm active:scale-95 uyghur-text relative overflow-hidden"
                        style={{ fontSize: `${Math.max(14, fontSize - 2)}px` }}
                      >
                        {isApplying === correction ? (
                          <div className="absolute inset-0 flex items-center justify-center bg-[#0369a1]">
                            <Loader2 size={14} className="animate-spin text-white" />
                          </div>
                        ) : correction}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-col sm:flex-row gap-2 sm:items-center bg-white border-2 border-slate-200 focus-within:border-[#0369a1] rounded-[24px] p-1.5 shadow-sm transition-all relative">
                <input
                  type="text"
                  dir="rtl"
                  value={customInput}
                  onChange={(e) => setCustomInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCustomApply(); }}
                  placeholder={suggestions.length > 0 ? '' : t('spellCheck.typeCorrection')}
                  className="flex-1 px-4 py-2.5 uyghur-text outline-none bg-transparent min-w-0"
                  style={{ fontSize: `${fontSize}px` }}
                  disabled={isBusy}
                />
                
                <div className="flex items-center gap-1.5 justify-end sm:justify-center border-t border-slate-100 sm:border-t-0 pt-2 sm:pt-0 pl-1">
                  <button
                    onClick={handleCustomApply}
                    disabled={!customInput.trim() || isBusy || isApplying !== null}
                    className="px-5 py-2.5 bg-[#0369a1] text-white rounded-[16px] text-xs sm:text-sm font-bold transition-all disabled:opacity-30 active:scale-95 hover:bg-[#0284c7] flex items-center justify-center min-w-[80px] shadow-sm whitespace-nowrap"
                  >
                    {isApplying !== null ? <Loader2 size={16} className="animate-spin" /> : t('spellCheck.apply')}
                  </button>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-between gap-2 mt-4 pt-4 border-t border-slate-100">
              {onPrevPage && (
                <button
                  onClick={() => onPrevPage?.()}
                  disabled={isBusy}
                  className="flex items-center gap-1.5 px-3 sm:px-4 py-2 bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 disabled:opacity-40 rounded-xl font-bold transition-all active:scale-95 text-xs sm:text-sm uyghur-text whitespace-nowrap"
                >
                  <ChevronRight size={16} strokeWidth={2.5} />
                  {t('pagination.previous')}
                </button>
              )}

              <button
                onClick={() => handleIgnore(activeIssue.id)}
                disabled={isBusy || isIgnoring}
                title={t('spellCheck.acceptOriginalTooltip')}
                className="flex items-center justify-center gap-1.5 px-4 sm:px-6 py-2 border-2 border-slate-200 text-slate-500 hover:border-emerald-500 hover:text-emerald-600 hover:bg-emerald-50 disabled:opacity-40 rounded-xl font-bold transition-all active:scale-95 text-xs sm:text-sm tracking-wider uyghur-text whitespace-nowrap"
              >
                {isIgnoring ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} strokeWidth={2.5} />}
                {t('spellCheck.acceptOriginal')}
              </button>

              <button
                onClick={() => onNextPage()}
                disabled={isBusy}
                className="flex items-center gap-1.5 px-3 sm:px-4 py-2 bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-800 disabled:opacity-40 rounded-xl font-bold transition-all active:scale-95 text-xs sm:text-sm uyghur-text whitespace-nowrap"
              >
                {t('pagination.next')}
                <ChevronLeft size={16} strokeWidth={2.5} />
              </button>
            </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-3 animate-fade-in" dir="rtl">
      {renderPanelHeader()}
      <div className="flex flex-col gap-3 pr-0.5">
        {isScanning && issues.length === 0 && (
          <div className="flex-1 flex flex-col items-center justify-center gap-5 py-16 animate-fade-in">
            <div className="relative">
              <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                <BookOpenCheck size={18} className="animate-pulse" />
              </div>
            </div>
            <p className="text-xs font-bold text-[#1a1a1a] uppercase animate-pulse">{t('spellCheck.rescanning', { page: pageNumber })}</p>
          </div>
        )}
        {isLoading && !hasLoaded && (
          <div className="flex-1 flex flex-col items-center justify-center gap-5 py-16">
            <div className="relative">
              <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                <BookOpenCheck size={18} className="animate-pulse" />
              </div>
            </div>
            <p className="text-xs font-bold text-[#1a1a1a] uppercase animate-pulse">{t('spellCheck.analyzing')}</p>
          </div>
        )}
        {hasLoaded && issues.length > 0 && (
          <div className="flex flex-col gap-3 animate-fade-in">
            {isScanning && (
              <div className="flex items-center gap-2 px-3 py-2 bg-[#0369a1]/5 rounded-2xl">
                <RefreshCw size={13} className="animate-spin text-[#0369a1]" strokeWidth={2.5} />
                <span className="text-xs text-[#0369a1] font-bold uppercase">{t('spellCheck.rescanning', { page: pageNumber })}</span>
              </div>
            )}
            {renderActiveCard()}
            <div className="h-6 sm:h-8 flex-shrink-0" />
          </div>
        )}
      </div>

      {showPageModal && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-2 sm:p-4 md:p-8" dir="rtl" lang="ug">
          <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in" onClick={() => setShowPageModal(false)} />
          <div
            className="bg-white/90 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] md:rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.3)] w-full max-w-2xl max-h-[95vh] sm:max-h-[90vh] relative z-10 overflow-hidden animate-scale-up border border-white/40 flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-4 pb-3 sm:p-6 sm:pb-4 md:p-8 md:pb-6 border-b border-slate-100 flex items-start justify-between bg-white/50">
              <div className="flex items-center gap-3 sm:gap-4 md:gap-6">
                <div className="p-2.5 sm:p-3 md:p-4 bg-[#0369a1] text-white rounded-2xl sm:rounded-[24px] shadow-xl shadow-[#0369a1]/20 shrink-0">
                  <BookOpen size={20} strokeWidth={2.5} className="sm:hidden" />
                  <BookOpen size={28} strokeWidth={2.5} className="hidden sm:block" />
                </div>
                <div>
                  <h3 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] mb-2 leading-tight flex items-center flex-wrap gap-2 text-right">
                    <span>{bookTitle}</span>
                    {bookAuthor && <span className="text-base sm:text-lg text-slate-400 font-normal">({bookAuthor})</span>}
                  </h3>
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1.5 px-3 py-1 bg-[#0369a1]/10 text-[#0369a1] rounded-full text-xs">
                      {t('chat.pageNumber', { page: pageNumber })}
                    </span>
                  </div>
                </div>
              </div>
              <button onClick={() => setShowPageModal(false)} className="p-2 sm:p-3 hover:bg-red-50 text-slate-300 hover:text-red-500 rounded-2xl transition-all">
                <X size={20} strokeWidth={3} className="sm:hidden" />
                <X size={28} strokeWidth={3} className="hidden sm:block" />
              </button>
            </div>
            <div className="flex-grow overflow-y-auto p-4 sm:p-6 md:p-10 bg-[#f8fafc]/30 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              <div className="bg-white/80 p-6 sm:p-8 md:p-10 rounded-[20px] sm:rounded-[24px] md:rounded-[32px] shadow-sm border border-white relative">
                <MarkdownContent content={pageText || ''} className="uyghur-text text-[#1e293b] leading-[2]" style={{ fontSize: `${fontSize}px` }} />
              </div>
            </div>
            <div className="p-4 px-4 sm:p-4 sm:px-6 md:p-6 md:px-10 bg-white/50 border-t border-slate-100 flex items-center justify-end">
              <button onClick={() => setShowPageModal(false)} className="px-6 py-2.5 bg-slate-900 text-white rounded-2xl font-bold uppercase tracking-widest text-sm transition-all active:scale-95 shadow-lg shadow-black/10">
                {t('common.close')}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};
