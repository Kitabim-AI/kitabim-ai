import React, { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  BookOpenCheck, Check, X, RefreshCw, Clock, RotateCcw, Inbox, FileText, Edit3, ChevronRight, ChevronLeft,
} from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { SpellIssue } from '../../hooks/useSpellCheck';
import { MarkdownContent } from '../common/MarkdownContent';
import { useNotification } from '../../context/NotificationContext';

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
  onUpdatePageText?: (text: string) => Promise<boolean>;
  onAddPending: (issueId: number, correctedWord: string, originalWord: string, options?: { isPhrase?: boolean; range?: [number, number] }) => void;
  pendingIssueIds: number[];
  onRemoveFromPending?: (issueId: number) => void;
  onIgnoreIssue: (issueId: number) => void;
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
  // Clamp charEnd to text length — guards against stale offsets computed on
  // a previously-normalised version of the text (shorter than raw page.text).
  const safeEnd = Math.min(charEnd, pageText.length);
  if (charOffset >= safeEnd) return null;
  const word = pageText.slice(charOffset, safeEnd);
  if (!word.trim()) return null; // extracted slice is whitespace-only — stale offset
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
  onUpdatePageText,
  onAddPending,
  pendingIssueIds,
  onRemoveFromPending,
  onIgnoreIssue,
  onNextPage,
  onPrevPage,
  globalIssueOffset = 0,
  totalBookIssues,
  bookTitle,
  bookAuthor,
}) => {
  const { t } = useI18n();
  const { addNotification } = useNotification();

  // ─── Single-finding model state ───────────────────────────────────────────
  const [activeIssueId, setActiveIssueId] = useState<number | null>(null);
  const [skippedIds, setSkippedIds] = useState<number[]>([]);
  const [customInput, setCustomInput] = useState('');
  const [phraseEdit, setPhraseEdit] = useState('');
  const [isEditingPhrase, setIsEditingPhrase] = useState(false);
  const [showMoreSuggestions, setShowMoreSuggestions] = useState(false);
  const [showPageModal, setShowPageModal] = useState(false);

  // S-NEW-3: unsaved phrase edit guard
  const [showUnsavedGuard, setShowUnsavedGuard] = useState(false);
  const [pendingNavAction, setPendingNavAction] = useState<(() => void) | null>(null);

  const wordRef = useRef<HTMLSpanElement>(null);
  const lastKnownIndexRef = useRef(0);
  const autoAdvanceTriggered = useRef(false);
  const prevPendingLengthRef = useRef(pendingIssueIds.length);

  const isBusy = isLoading || isScanning;

  // ─── Derived state ─────────────────────────────────────────────────────────
  const stepperIndex = activeIssueId !== null
    ? Math.max(0, issues.findIndex(i => i.id === activeIssueId))
    : 0;
  const activeIssue = issues.length > 0 ? (issues[stepperIndex] ?? issues[0]) : null;
  const isActiveSkipped = activeIssue ? skippedIds.includes(activeIssue.id) : false;
  const nonSkippedIssues = issues.filter((i: SpellIssue) => !skippedIds.includes(i.id) && !pendingIssueIds.includes(i.id));
  // ─── Page reset ────────────────────────────────────────────────────────────
  useEffect(() => {
    setActiveIssueId(null);
    setSkippedIds([]);
    setCustomInput('');
    setIsEditingPhrase(false);
    setPhraseEdit('');
    setShowMoreSuggestions(false);
    setShowUnsavedGuard(false);
    setPendingNavAction(null);
    autoAdvanceTriggered.current = false;
  }, [pageNumber]);

  // ─── Initialize / advance active issue when issues change ─────────────────
  useEffect(() => {
    if (issues.length === 0) {
      setActiveIssueId(null);
      return;
    }
    if (activeIssueId === null) {
      const first = issues.find(i => !skippedIds.includes(i.id));
      setActiveIssueId(first?.id ?? issues[0].id);
      return;
    }
    if (!issues.find(i => i.id === activeIssueId)) {
      // Issue was removed (corrected / ignored): advance from last known position
      const targetIdx = Math.min(lastKnownIndexRef.current, issues.length - 1);
      const forward = issues.slice(targetIdx).find(i => !skippedIds.includes(i.id));
      const backward = forward ?? issues.slice(0, targetIdx).find(i => !skippedIds.includes(i.id));
      setActiveIssueId(backward?.id ?? issues[targetIdx]?.id ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issues.length]);

  // Auto-advance when active issue gets queued (item added to pendingIssueIds)
  useEffect(() => {
    const added = pendingIssueIds.length > prevPendingLengthRef.current;
    prevPendingLengthRef.current = pendingIssueIds.length;
    if (!added || !activeIssueId) return;
    if (!pendingIssueIds.includes(activeIssueId)) return;
    // Active issue was just queued — advance to next unresolved issue
    const currentIdx = issues.findIndex(i => i.id === activeIssueId);
    const searchOrder = [...issues.slice(currentIdx + 1), ...issues.slice(0, currentIdx)];
    const next = searchOrder.find((i: SpellIssue) => !skippedIds.includes(i.id) && !pendingIssueIds.includes(i.id));
    if (next) setActiveIssueId(next.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingIssueIds.length]);

  // Track last known stepper position for smart advance
  useEffect(() => {
    const idx = issues.findIndex(i => i.id === activeIssueId);
    if (idx >= 0) lastKnownIndexRef.current = idx;
  }, [activeIssueId, issues]);

  // ─── Scroll highlighted word into view when active issue changes ──────────
  useEffect(() => {
    if (!activeIssueId || !wordRef.current) return;
    const timer = setTimeout(() => {
      wordRef.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }, 60);
    return () => clearTimeout(timer);
  }, [activeIssueId]);

  // ─── Auto-advance (only in 'auto' mode) ────────────────────────────────────
  useEffect(() => {
    if (navigationMode !== 'auto') return;
    if (!hasLoaded || isBusy || nonSkippedIssues.length > 0) return;
    if (autoAdvanceTriggered.current) return;
    autoAdvanceTriggered.current = true;
    onNextPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasLoaded, isBusy, nonSkippedIssues.length, navigationMode]);


  // ─── Action handlers ──────────────────────────────────────────────────────
  const handleSkip = (issueId: number) => {
    const currentIdx = issues.findIndex(i => i.id === issueId);
    setSkippedIds(prev => [...prev, issueId]);
    // Advance to next non-skipped
    const next = issues.slice(currentIdx + 1).find(i => !skippedIds.includes(i.id) && i.id !== issueId);
    const fallback = next ?? issues.slice(0, currentIdx).find(i => !skippedIds.includes(i.id) && i.id !== issueId);
    if (fallback) setActiveIssueId(fallback.id);
  };

  const handleUndoSkip = (issueId: number) => {
    setSkippedIds(prev => prev.filter(id => id !== issueId));
    setActiveIssueId(issueId);
  };

  const handleOcrApply = (correction: string) => {
    if (!activeIssue) return;
    const options = activeIssue.char_offset !== null && activeIssue.char_end !== null
      ? { range: [activeIssue.char_offset, activeIssue.char_end] as [number, number] }
      : undefined;
    onAddPending(activeIssue.id, correction, activeIssue.word, options);
  };

  const handleCustomApply = () => {
    const val = customInput.trim();
    if (!val || !activeIssue) return;
    const options = activeIssue.char_offset !== null && activeIssue.char_end !== null
      ? { range: [activeIssue.char_offset, activeIssue.char_end] as [number, number] }
      : undefined;
    onAddPending(activeIssue.id, val, activeIssue.word, options);
    setCustomInput('');
  };

  const handlePageTextSave = async () => {
    if (!onUpdatePageText) return;
    const success = await onUpdatePageText(phraseEdit);
    setIsEditingPhrase(false);
    setPhraseEdit('');
    if (success) {
      addNotification(t('spellCheck.applied'), 'success');
    }
  };

  const handleIgnore = (issueId: number) => {
    onIgnoreIssue(issueId);
  };

  // ─── Context extraction ───────────────────────────────────────────────────
  const ctx = activeIssue && pageText
    ? extractContext(pageText, activeIssue.char_offset, activeIssue.char_end)
    : null;

  // =========================================================================
  // RENDER helpers
  // =========================================================================

  const renderPanelHeader = () => {
    return (
      <div className="flex items-center justify-between gap-2 flex-shrink-0">
        <div className="flex items-center gap-2">
          {issues.length > 0 && (
            <span className="px-3 py-1 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl text-xs font-bold">
              {t('spellCheck.findingProgress', {
                current: globalIssueOffset + stepperIndex + 1,
                total: totalBookIssues ?? issues.length,
              })}
            </span>
          )}
          {totalPages && (
            <span className="px-3 py-1 bg-slate-100 text-slate-400 rounded-2xl text-xs font-bold">
              {t('chat.pageNumber', { page: pageNumber })}
              {' / '}
              {totalPages}
            </span>
          )}
        </div>
        {(onPrevPage) && (
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                if (isEditingPhrase) { setShowUnsavedGuard(true); setPendingNavAction(() => onPrevPage); }
                else onPrevPage?.();
              }}
              className="p-1.5 text-slate-400 hover:text-[#0369a1] hover:bg-[#0369a1]/10 rounded-lg transition-all"
              title={t('common.previous')}
            >
              <ChevronRight size={16} />
            </button>
            <button
              onClick={() => {
                if (isEditingPhrase) { setShowUnsavedGuard(true); setPendingNavAction(() => onNextPage); }
                else onNextPage();
              }}
              className="p-1.5 text-slate-400 hover:text-[#0369a1] hover:bg-[#0369a1]/10 rounded-lg transition-all"
              title={t('common.next')}
            >
              <ChevronLeft size={16} />
            </button>
          </div>
        )}
      </div>
    );
  };


  const renderContextSection = () => {
    if (!activeIssue) return null;

    // Full-page editor
    if (isEditingPhrase) {
      return (
        <div className="flex-1 flex flex-col min-h-0 gap-3">
          <textarea
            dir="rtl"
            value={phraseEdit}
            onChange={(e) => setPhraseEdit(e.target.value)}
            className="flex-1 min-h-0 w-full p-3 uyghur-text leading-loose border-2 border-[#0369a1]/30 rounded-2xl outline-none focus:border-[#0369a1] bg-slate-50 shadow-inner resize-none overflow-y-auto"
            style={{ fontSize: `${fontSize}px` }}
          />
          <div className="flex gap-2">
            <button
              onClick={handlePageTextSave}
              className="flex-1 px-4 py-2.5 bg-[#0369a1] text-white rounded-xl font-bold shadow-lg shadow-[#0369a1]/20 active:scale-95 transition-all"
              style={{ fontSize: `${fontSize}px` }}
            >
              {t('spellCheck.apply')}
            </button>
            <button
              onClick={() => { setIsEditingPhrase(false); setPhraseEdit(''); }}
              className="px-4 py-2.5 bg-slate-100 text-slate-500 rounded-xl font-bold active:scale-95 transition-all hover:bg-slate-200"
              style={{ fontSize: `${fontSize}px` }}
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      );
    }

    // Skeleton shimmer while pageText loads
    if (pageText === undefined) {
      return (
        <div className="space-y-2">
          <div className="h-4 bg-slate-100 rounded-xl animate-pulse" style={{ height: `${fontSize + 4}px` }} />
          <div className="h-4 bg-slate-100 rounded-xl animate-pulse w-3/4" style={{ height: `${fontSize + 4}px` }} />
        </div>
      );
    }

    if (!ctx) {
      // Offset null or out of bounds: show word only
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
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowPageModal(true)}
              className="text-xs font-bold text-slate-400 px-3 py-1.5 bg-slate-100 rounded-lg hover:bg-slate-200 transition-all uppercase flex items-center gap-2"
            >
              <FileText size={12} />
              {t('spellCheck.viewPage')}
            </button>
            <button
              onClick={() => {
                setIsEditingPhrase(true);
                setPhraseEdit(pageText || '');
              }}
              className="text-xs font-bold text-[#0369a1] px-3 py-1.5 bg-[#0369a1]/10 rounded-lg hover:bg-[#0369a1] hover:text-white transition-all uppercase flex items-center gap-2"
            >
              <Edit3 size={12} />
              {t('common.edit')}
            </button>
          </div>
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

  const renderQueuedCard = () => {
    if (!activeIssue) return null;
    return (
      <div className="bg-[#0369a1]/5 border border-[#0369a1]/20 rounded-3xl p-5 space-y-4 animate-fade-in">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-[#0369a1] uyghur-text" style={{ fontSize: `${fontSize}px` }}>
            {activeIssue.word}
          </span>
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-[#0369a1]/10 rounded-xl">
            <Inbox size={12} className="text-[#0369a1]" strokeWidth={2.5} />
            <span className="text-[10px] font-bold text-[#0369a1] uppercase">
              {t('spellCheck.queued')}
            </span>
          </div>
        </div>
        {onRemoveFromPending && (
          <button
            onClick={() => onRemoveFromPending(activeIssue.id)}
            className="w-full flex items-center justify-center gap-2 px-5 py-2.5 bg-white/60 text-slate-400 hover:text-red-500 hover:bg-red-50 border border-slate-200 rounded-2xl text-sm font-normal transition-all active:scale-95 uppercase"
          >
            <X size={13} strokeWidth={2.5} />
            {t('spellCheck.removeFromQueue')}
          </button>
        )}
      </div>
    );
  };

  const renderActiveCard = () => {
    if (!activeIssue) return null;
    if (pendingIssueIds.includes(activeIssue.id)) return renderQueuedCard();
    if (isActiveSkipped) return renderSkippedCard();

    const suggestions = activeIssue.ocr_corrections;
    const visibleSuggestions = showMoreSuggestions ? suggestions : suggestions.slice(0, 3);

    return (
      <div className={`bg-white/80 backdrop-blur-md border border-[#0369a1]/10 rounded-3xl p-4 sm:p-5 shadow-sm animate-fade-in${isEditingPhrase ? ' flex-1 flex flex-col min-h-0' : ' space-y-4'}`}>
        {/* Context section */}
        {renderContextSection()}

        {/* Action area — hidden while editing phrase */}
        {!isEditingPhrase && (
          <>
            {/* OCR suggestions */}
            {suggestions.length > 0 && (
              <div className="space-y-2">
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">{t('spellCheck.suggestion')}</span>
                {/* Mobile: horizontal scroll row; Desktop: vertical stack */}
                <div className="sm:hidden flex flex-row gap-2 overflow-x-auto pb-1 -mx-1 px-1">
                  {visibleSuggestions.map((correction) => (
                    <button
                      key={correction}
                      onClick={() => handleOcrApply(correction)}
                      disabled={isBusy}
                      className="flex-shrink-0 flex items-center gap-2 px-4 py-2.5 bg-[#0369a1] text-white rounded-2xl font-normal transition-all active:scale-95 shadow-md shadow-[#0369a1]/10 hover:shadow-lg hover:shadow-[#0369a1]/20 disabled:opacity-40"
                      style={{ fontSize: `${fontSize}px` }}
                    >
                      <span className="uyghur-text">{correction}</span>
                      <Check size={14} strokeWidth={2.5} className="flex-shrink-0" />
                    </button>
                  ))}
                </div>
                <div className="hidden sm:flex flex-col gap-1.5">
                  {visibleSuggestions.map((correction) => (
                    <button
                      key={correction}
                      onClick={() => handleOcrApply(correction)}
                      disabled={isBusy}
                      className="flex items-center justify-between px-5 py-2.5 bg-[#0369a1] text-white rounded-2xl font-normal transition-all active:scale-95 shadow-md shadow-[#0369a1]/10 hover:shadow-lg hover:shadow-[#0369a1]/20 disabled:opacity-40"
                      style={{ fontSize: `${fontSize}px` }}
                    >
                      <span className="uyghur-text">{correction}</span>
                      <Check size={16} strokeWidth={2.5} />
                    </button>
                  ))}
                </div>
                {suggestions.length > 3 && (
                  <button
                    onClick={() => setShowMoreSuggestions(prev => !prev)}
                    className="text-xs text-[#0369a1] font-bold uppercase hover:underline"
                  >
                    {showMoreSuggestions ? '▲' : `▼ +${suggestions.length - 3}`}
                  </button>
                )}
              </div>
            )}

            {/* Manual correction input */}
            <div className="flex gap-2">
              <input
                type="text"
                dir="rtl"
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleCustomApply(); }}
                placeholder={t('spellCheck.typeCorrection')}
                className="flex-1 px-4 py-2.5 uyghur-text border-2 border-[#0369a1]/20 rounded-2xl outline-none focus:border-[#0369a1] bg-white transition-colors"
                style={{ fontSize: `${fontSize}px` }}
                disabled={isBusy}
              />
              <button
                onClick={handleCustomApply}
                disabled={!customInput.trim() || isBusy}
                className="px-4 py-2.5 bg-[#0369a1] text-white rounded-2xl text-sm font-bold transition-all disabled:opacity-30 active:scale-95 hover:bg-[#0284c7]"
              >
                {t('spellCheck.apply')}
              </button>
            </div>

            {/* Skip / Ignore */}
            <div className="flex gap-2">
              <button
                onClick={() => handleSkip(activeIssue.id)}
                disabled={isBusy}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-50 text-slate-400 hover:text-slate-600 hover:bg-slate-100 disabled:opacity-40 rounded-2xl font-normal transition-all active:scale-95 uppercase"
                style={{ fontSize: `${fontSize}px` }}
              >
                <Clock size={13} strokeWidth={2.5} />
                {t('spellCheck.skipLater')}
              </button>
              <button
                onClick={() => handleIgnore(activeIssue.id)}
                disabled={isBusy}
                title={t('spellCheck.ignoreTooltip')}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-50 text-slate-400 hover:text-red-500 hover:bg-red-50 disabled:opacity-40 rounded-2xl font-normal transition-all active:scale-95 uppercase"
                style={{ fontSize: `${fontSize}px` }}
              >
                <X size={13} strokeWidth={2.5} />
                {t('spellCheck.ignore')}
              </button>
            </div>
          </>
        )}
      </div>
    );
  };


  // =========================================================================
  // MAIN RENDER
  // =========================================================================
  return (
    <div
      className={`flex flex-col gap-3 animate-fade-in${isEditingPhrase ? ' flex-1 min-h-0' : ''}`}
      dir="rtl"
    >
      {/* Panel Header */}
      {renderPanelHeader()}

      {/* S-NEW-3: Unsaved phrase edit guard */}
      {showUnsavedGuard && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-3 flex-shrink-0 animate-fade-in">
          <p className="text-sm text-amber-700 font-normal uyghur-text mb-2" style={{ fontSize: `${fontSize - 2}px` }}>
            {t('spellCheck.unsavedEdit')}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setIsEditingPhrase(false);
                setPhraseEdit('');
                setShowUnsavedGuard(false);
                pendingNavAction?.();
                setPendingNavAction(null);
              }}
              className="flex-1 px-3 py-1.5 bg-amber-100 text-amber-700 hover:bg-amber-200 rounded-xl text-xs font-bold transition-all"
            >
              {t('spellCheck.discardEdit')}
            </button>
            <button
              onClick={() => { setShowUnsavedGuard(false); setPendingNavAction(null); }}
              className="flex-1 px-3 py-1.5 bg-white text-slate-600 hover:bg-slate-50 rounded-xl text-xs font-bold transition-all border border-slate-200"
            >
              {t('spellCheck.stayAndEdit')}
            </button>
          </div>
        </div>
      )}

      {/* Body */}
      <div className={`flex flex-col gap-3${isEditingPhrase ? ' flex-1 min-h-0' : ''}`}>

        {/* Rescanning spinner — no issues visible yet */}
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

        {/* Initial loading spinner */}
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

        {/* Issues — single active finding */}
        {hasLoaded && issues.length > 0 && (
          <div className={`flex flex-col gap-3 animate-fade-in${isEditingPhrase ? ' flex-1 min-h-0' : ''}`}>
            {/* Rescanning indicator when issues are visible */}
            {isScanning && (
              <div className="flex items-center gap-2 px-3 py-2 bg-[#0369a1]/5 rounded-2xl">
                <RefreshCw size={13} className="animate-spin text-[#0369a1]" strokeWidth={2.5} />
                <span className="text-xs text-[#0369a1] font-bold uppercase">{t('spellCheck.rescanning', { page: pageNumber })}</span>
              </div>
            )}
            {renderActiveCard()}
          </div>
        )}

      </div>

      {/* Page content modal — portalled to body to escape transform stacking context */}
      {showPageModal && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 sm:p-10 bg-black/40 backdrop-blur-sm animate-fade-in"
          onClick={() => setShowPageModal(false)}
        >
          <div
            className="glass-panel w-full max-w-3xl max-h-[80dvh] flex flex-col overflow-hidden rounded-[32px] border border-white/60 shadow-2xl"
            onClick={(e: React.MouseEvent) => e.stopPropagation()}
          >
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 pt-4 pb-3 flex-shrink-0 border-b border-[#0369a1]/5" dir="rtl">
              <div className="flex flex-col gap-0.5">
                {bookTitle && (
                  <span className="font-normal text-[#1a1a1a] uyghur-text leading-tight" style={{ fontSize: `${fontSize + 2}px` }}>
                    {bookTitle}
                  </span>
                )}
                <div className="flex items-center gap-3">
                  {bookAuthor && (
                    <span className="text-xs text-slate-400 font-normal uyghur-text">{bookAuthor}</span>
                  )}
                  <span className="text-xs font-bold text-[#94a3b8] uppercase">{t('chat.pageNumber', { page: pageNumber })}</span>
                </div>
              </div>
              <button
                onClick={() => setShowPageModal(false)}
                className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-white/60 rounded-xl transition-all flex-shrink-0"
              >
                <X size={16} />
              </button>
            </div>
            {/* Page card — same styling as reader PageItem */}
            <div className="flex-1 overflow-y-auto px-4 pb-4 custom-scrollbar" dir="rtl">
              <div className="bg-white rounded-[24px] shadow-xl border border-[#0369a1]/10 p-6">
                <MarkdownContent
                  content={pageText || ''}
                  className="uyghur-text text-[#1a1a1a] leading-relaxed"
                  style={{ fontSize: `${fontSize}px` }}
                />
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};
