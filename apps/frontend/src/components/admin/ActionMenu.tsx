import React from 'react';
import { createPortal } from 'react-dom';
import { BookOpen, RefreshCw, RotateCcw, Trash2, Image, BookOpenCheck, ScanText, Cuboid } from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';
import { useIsAdmin } from '../../hooks/useAuth';

interface ActionMenuProps {
  book: Book;
  close: () => void;
  anchorRect: DOMRect;
  menuRef: React.RefObject<HTMLDivElement>;
}

export const ActionMenu: React.FC<ActionMenuProps> = ({ book, close, anchorRect, menuRef }) => {
  const { bookActions } = useAppContext();
  const { t } = useI18n();
  const isAdmin = useIsAdmin();
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  // Reindex: re-embed a ready book without re-doing OCR
  const canReindex = book.pipelineStep === 'ready';
  // Reset Failed Pages: available when there are failed pages (in-progress or error state)
  const canResetFailed = book.pipelineStep !== null
    && (book.pipelineStep !== 'ready' || book.status === 'error');

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
          onClick={() => { bookActions.handleTriggerSpellCheck(book.id); close(); }} 
          disabled={!canReindex} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-violet-600 hover:bg-violet-50 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <BookOpenCheck size={16} />
          <span className="flex-1 text-right">{t('admin.table.triggerSpellCheck')}</span>
        </button>

        <button 
          onClick={() => { bookActions.handleReindexBook(book.id); close(); }} 
          disabled={!canReindex} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-blue-600 hover:bg-blue-50 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <Cuboid size={16} />
          <span className="flex-1 text-right">{t('admin.table.reindex')}</span>
        </button>

        <button 
          onClick={() => { bookActions.handleResetFailedPages(book.id); close(); }} 
          disabled={!canResetFailed} 
          className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-amber-600 hover:bg-amber-50 disabled:opacity-30 rounded-xl transition-all active:scale-[0.98]"
        >
          <RotateCcw size={16} className="shrink-0" />
          <span className="flex-1 text-right">{t('admin.table.resetFailed')}</span>
        </button>

        {isAdmin && (
          <button 
            onClick={() => { bookActions.handleReprocessBook(book.id); close(); }} 
            className="w-full flex items-center gap-3 px-3 py-2 text-[13px] font-semibold text-orange-600 hover:bg-orange-50 rounded-xl transition-all active:scale-[0.98]"
          >
            <ScanText size={16} />
            <span className="flex-1 text-right">{t('admin.table.redoOcr')}</span>
          </button>
        )}

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
