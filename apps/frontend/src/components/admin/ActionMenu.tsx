import { Book } from '@shared/types';
import { BookOpen, BookOpenCheck, Cuboid, FileText, Image, Loader2, Network, RotateCcw, ScanText, Scissors, Trash2 } from 'lucide-react';
import React from 'react';
import { createPortal } from 'react-dom';
import { REPROCESS_STEP } from '../../constants/milestones';
import { useAppContext } from '../../context/AppContext';
import { useIsAdmin } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';

interface ActionMenuProps {
  book: Book;
  close: () => void;
  anchorRect: DOMRect;
  menuRef: React.RefObject<HTMLDivElement>;
  spellCheckEnabled?: boolean;
}

export const ActionMenu: React.FC<ActionMenuProps> = ({ book, close, anchorRect, menuRef, spellCheckEnabled = true }) => {
  const { bookActions } = useAppContext();
  const { t } = useI18n();
  const isAdmin = useIsAdmin();
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const reprocessingStep = bookActions.reprocessingBooks.get(book.id);

  const hasFailures = Object.entries(book.pipelineStats || {}).some(([k, v]) => 
    k.toLowerCase().includes('failed') && typeof v === 'number' && v > 0
  );

  const canResetFailed = book.pipelineStep !== null
    && (book.pipelineStep !== 'ready' || book.status === 'error' || hasFailures);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      bookActions.handleReplaceCover(book.id, file);
      close();
    }
  };

  return createPortal(
    <div
      ref={menuRef}
      dir="rtl"
      style={{ 
        position: 'fixed', 
        top: anchorRect.bottom + 8, 
        left: anchorRect.left, 
        zIndex: 9999 
      }}
      className="w-64 glass-panel dark:bg-slate-900/95 dark:border-slate-850 shadow-2xl py-2.5 rounded-[20px] border border-[#0369a1]/15 animate-in fade-in slide-in-from-top-2 duration-200"
    >
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept="image/*"
        onChange={handleFileChange}
      />
      
      <div className="px-2 space-y-0.5">
        <button 
          onClick={() => { bookActions.openReader(book, () => { }, () => { }, () => { }); close(); }} 
          disabled={book.pipelineStep === null && book.status === 'pending'} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-[#1a1a1a] dark:text-slate-100 hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/10 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <BookOpen size={16} className="text-slate-500" />
          <span className="flex-1 text-right">{t('admin.table.view')}</span>
        </button>
 
        <div className="h-px bg-slate-100/60 dark:bg-slate-800 my-1.5 mx-2" />
 
        <button 
          onClick={() => fileInputRef.current?.click()} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/10 rounded-xl transition-all active:scale-[0.98]"
        >
          <Image size={16} />
          <span className="flex-1 text-right">{t('admin.table.replaceCover') || 'مۇقاۋىنى ئالماشتۇرۇش'}</span>
        </button>
 
        <div className="h-px bg-slate-100/60 dark:bg-slate-800 my-1.5 mx-2" />
 
        <button 
          onClick={() => { bookActions.handleRetryFailedPages(book.id); close(); }} 
          disabled={!canResetFailed} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-amber-600 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950/20 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <RotateCcw size={16} className="shrink-0" />
          <span className="flex-1 text-right">{t('admin.table.retryFailed') || 'مەغلۇپ بەتلەرنى قايتا سىناش'}</span>
        </button>
 
        <div className="h-px bg-slate-100/60 dark:bg-slate-800 my-1.5 mx-2" />
 
        {isAdmin && (
          <button
            onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.OCR); close(); }}
            disabled={reprocessingStep === REPROCESS_STEP.OCR}
            className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-orange-600 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-950/20 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
          >
            {reprocessingStep === REPROCESS_STEP.OCR ? <Loader2 size={16} className="animate-spin" /> : <ScanText size={16} />}
            <span className="flex-1 text-right">{t('admin.table.reprocess.ocr') || 'قايتا OCR'}</span>
          </button>
        )}
 
        <button
          onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.CHUNKING); close(); }}
          disabled={book.pipelineStep === null || reprocessingStep === REPROCESS_STEP.CHUNKING}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-950/20 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === REPROCESS_STEP.CHUNKING ? <Loader2 size={16} className="animate-spin" /> : <Scissors size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.chunking') || 'قايتا پارچىلاش'}</span>
        </button>
 
        <button
          onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.EMBEDDING); close(); }}
          disabled={book.pipelineStep === null || reprocessingStep === REPROCESS_STEP.EMBEDDING}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-indigo-600 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/20 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === REPROCESS_STEP.EMBEDDING ? <Loader2 size={16} className="animate-spin" /> : <Cuboid size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.embedding') || 'قايتا ۋېكتورلاش'}</span>
        </button>
 
 
        <button
          onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.SPELL_CHECK); close(); }}
          disabled={book.pipelineStep === null || !spellCheckEnabled || reprocessingStep === REPROCESS_STEP.SPELL_CHECK}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-violet-600 dark:text-violet-400 hover:bg-violet-50 dark:hover:bg-violet-950/20 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === REPROCESS_STEP.SPELL_CHECK ? <Loader2 size={16} className="animate-spin" /> : <BookOpenCheck size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.spell_check') || 'قايتا ئىملا تەكشۈرۈش'}</span>
        </button>
 
        {isAdmin && (
          <button
            onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.GRAPH); close(); }}
            disabled={book.pipelineStep === null || reprocessingStep === REPROCESS_STEP.GRAPH}
            className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-teal-600 dark:text-teal-400 hover:bg-teal-50 dark:hover:bg-teal-950/20 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
          >
            {reprocessingStep === REPROCESS_STEP.GRAPH ? <Loader2 size={16} className="animate-spin" /> : <Network size={16} />}
            <span className="flex-1 text-right">{t('admin.table.reprocess.graph') || 'قايتا گىراف تۈزۈش'}</span>
          </button>
        )}
 
        {isAdmin && (
          <button
            onClick={() => { bookActions.handleReprocessStep(book.id, REPROCESS_STEP.SUMMARY); close(); }}
            disabled={book.pipelineStep === null || reprocessingStep === REPROCESS_STEP.SUMMARY}
            className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-sky-600 dark:text-sky-400 hover:bg-sky-50 dark:hover:bg-sky-950/20 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
          >
            {reprocessingStep === REPROCESS_STEP.SUMMARY ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
            <span className="flex-1 text-right">{t('admin.table.reprocess.summary') || 'قىسقىچە مەزمۇنىنى قايتا ھاسىللاش'}</span>
          </button>
        )}
 
        <div className="h-px bg-slate-100/60 dark:bg-slate-800 my-1.5 mx-2" />
 
        <button 
          onClick={() => { bookActions.handleDeleteBook(book.id); close(); }} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 rounded-xl transition-all active:scale-[0.98]"
        >
          <Trash2 size={16} />
          <span className="flex-1 text-right">{t('admin.table.delete')}</span>
        </button>
      </div>
    </div>,
    document.body
  );
};
