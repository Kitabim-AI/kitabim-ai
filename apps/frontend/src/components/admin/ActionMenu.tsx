import React from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, RotateCcw, Trash2, Image, BookOpenCheck, ScanText, Cuboid, Scissors, WholeWord, Loader2 } from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';
import { useIsAdmin } from '../../hooks/useAuth';

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
      className="w-64 glass-panel shadow-2xl py-2.5 rounded-[20px] border border-[#0369a1]/15 animate-in fade-in slide-in-from-top-2 duration-200"
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
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-[#1a1a1a] hover:bg-[#0369a1]/5 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <BookOpen size={16} className="text-slate-500" />
          <span className="flex-1 text-right">{t('admin.table.view')}</span>
        </button>

        <div className="h-px bg-slate-100/60 my-1.5 mx-2" />

        <button 
          onClick={() => fileInputRef.current?.click()} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-[#0369a1] hover:bg-[#0369a1]/5 rounded-xl transition-all active:scale-[0.98]"
        >
          <Image size={16} />
          <span className="flex-1 text-right">{t('admin.table.replaceCover') || 'مۇقاۋىنى ئالماشتۇرۇش'}</span>
        </button>

        <div className="h-px bg-slate-100/60 my-1.5 mx-2" />

        <button 
          onClick={() => { bookActions.handleRetryFailedPages(book.id); close(); }} 
          disabled={!canResetFailed} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-amber-600 hover:bg-amber-50 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <RotateCcw size={16} className="shrink-0" />
          <span className="flex-1 text-right">{t('admin.table.retryFailed') || 'مەغلۇپ بەتلەرنى قايتا سىناش'}</span>
        </button>

        <div className="h-px bg-slate-100/60 my-1.5 mx-2" />

        {isAdmin && (
          <button
            onClick={() => { bookActions.handleReprocessStep(book.id, 'ocr'); close(); }}
            disabled={reprocessingStep === 'ocr'}
            className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-orange-600 hover:bg-orange-50 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
          >
            {reprocessingStep === 'ocr' ? <Loader2 size={16} className="animate-spin" /> : <ScanText size={16} />}
            <span className="flex-1 text-right">{t('admin.table.reprocess.ocr') || 'قايتا OCR'}</span>
          </button>
        )}

        <button
          onClick={() => { bookActions.handleReprocessStep(book.id, 'chunking'); close(); }}
          disabled={book.pipelineStep === null || reprocessingStep === 'chunking'}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-blue-600 hover:bg-blue-50 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === 'chunking' ? <Loader2 size={16} className="animate-spin" /> : <Scissors size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.chunking') || 'قايتا پارچىلاش'}</span>
        </button>

        <button
          onClick={() => { bookActions.handleReprocessStep(book.id, 'embedding'); close(); }}
          disabled={book.pipelineStep === null || reprocessingStep === 'embedding'}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-indigo-600 hover:bg-indigo-50 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === 'embedding' ? <Loader2 size={16} className="animate-spin" /> : <Cuboid size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.embedding') || 'قايتا ۋېكتورلاش'}</span>
        </button>

        {/* Word Index - Hidden (disabled in pipeline) */}
        {/* <button
          onClick={() => { bookActions.handleReprocessStep(book.id, 'word-index'); close(); }}
          disabled={book.pipelineStep === null || reprocessingStep === 'word-index'}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-emerald-600 hover:bg-emerald-50 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === 'word-index' ? <Loader2 size={16} className="animate-spin" /> : <WholeWord size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.word_index') || 'قايتا سۆز تىزىملىكى ھاسىللاش'}</span>
        </button> */}

        <button
          onClick={() => { bookActions.handleReprocessStep(book.id, 'spell-check'); close(); }}
          disabled={book.pipelineStep === null || !spellCheckEnabled || reprocessingStep === 'spell-check'}
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-violet-600 hover:bg-violet-50 disabled:opacity-30 disabled:cursor-not-allowed rounded-xl transition-all active:scale-[0.98]"
        >
          {reprocessingStep === 'spell-check' ? <Loader2 size={16} className="animate-spin" /> : <BookOpenCheck size={16} />}
          <span className="flex-1 text-right">{t('admin.table.reprocess.spell_check') || 'قايتا ئىملا تەكشۈرۈش'}</span>
        </button>

        <div className="h-px bg-slate-100/60 my-1.5 mx-2" />

        <button 
          onClick={() => { bookActions.handleDeleteBook(book.id); close(); }} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-red-600 hover:bg-red-50 rounded-xl transition-all active:scale-[0.98]"
        >
          <Trash2 size={16} />
          <span className="flex-1 text-right">{t('admin.table.delete')}</span>
        </button>
      </div>
    </div>,
    document.body
  );
};
