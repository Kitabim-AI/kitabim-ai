import React from 'react';
import { BookOpen, RefreshCw, RotateCcw, Trash2, Image, BookOpenCheck } from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

interface ActionMenuProps {
  book: Book;
  close: () => void;
}

export const ActionMenu: React.FC<ActionMenuProps> = ({ book, close }) => {
  const { bookActions } = useAppContext();
  const { t } = useI18n();
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

  return (
    <div className="absolute left-0 top-full mt-2 w-52 glass-panel shadow-2xl z-50 py-2 rounded-[16px] border border-[#0369a1]/10">
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept="image/*"
        onChange={handleFileChange}
      />
      <button onClick={() => { bookActions.openReader(book, () => { }, () => { }, () => { }); close(); }} disabled={book.pipelineStep === null && book.status === 'pending'} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-[#1a1a1a] hover:bg-[#0369a1]/10 disabled:text-slate-200 transition-colors"><BookOpen size={14} /> {t('admin.table.view')}</button>
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => fileInputRef.current?.click()} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-[#0369a1] hover:bg-[#0369a1]/10 transition-colors">
        <Image size={14} /> {t('admin.table.replaceCover') || 'مۇقاۋىنى ئالماشتۇرۇش'}
      </button>
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => { bookActions.handleTriggerSpellCheck(book.id); close(); }} disabled={!canReindex} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-violet-600 hover:bg-violet-50 disabled:text-slate-200 transition-colors"><BookOpenCheck size={14} /> {t('admin.table.triggerSpellCheck')}</button>
      <button onClick={() => { bookActions.handleReindexBook(book.id); close(); }} disabled={!canReindex} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-blue-600 hover:bg-blue-50 disabled:text-slate-200 transition-colors"><RefreshCw size={14} /> {t('admin.table.reindex')}</button>
      <button onClick={() => { bookActions.handleResetFailedPages(book.id); close(); }} disabled={!canResetFailed} className="w-full flex items-start gap-3 px-4 py-2 text-sm font-black text-amber-600 hover:bg-amber-50 disabled:text-slate-200 transition-colors"><RotateCcw size={14} className="mt-0.5 shrink-0" /> {t('admin.table.resetFailed')}</button>
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => { bookActions.handleDeleteBook(book.id); close(); }} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-red-600 hover:bg-red-50 transition-colors"><Trash2 size={14} /> {t('admin.table.delete')}</button>
    </div>
  );
};
