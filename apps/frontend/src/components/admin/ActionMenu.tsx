import React from 'react';
import { BookOpen, RefreshCw, RotateCcw, Trash2 } from 'lucide-react';
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
  // Reindex: re-embed a ready or ocr_done book without re-doing OCR
  const canReindex = book.status === 'ready' || book.status === 'ocr_done';
  // Reset Failed Pages: available for non-ready, non-pending books that may have exhausted retries
  const canResetFailed = book.status !== 'ready' && book.status !== 'pending';

  return (
    <div className="absolute left-0 top-full mt-2 w-52 glass-panel shadow-2xl z-50 py-2 rounded-[16px] border border-[#0369a1]/10">
      <button onClick={() => { bookActions.openReader(book, () => { }, () => { }, () => { }); close(); }} disabled={book.status === 'pending' || book.status === 'uploading'} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-[#1a1a1a] hover:bg-[#0369a1]/10 disabled:text-slate-200 transition-colors"><BookOpen size={14} /> {t('admin.table.view')}</button>
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => { bookActions.handleReindexBook(book.id); close(); }} disabled={!canReindex} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-blue-600 hover:bg-blue-50 disabled:text-slate-200 transition-colors"><RefreshCw size={14} /> {t('admin.table.reindex')}</button>
      <button onClick={() => { bookActions.handleResetFailedPages(book.id); close(); }} disabled={!canResetFailed} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-amber-600 hover:bg-amber-50 disabled:text-slate-200 transition-colors"><RotateCcw size={14} /> {t('admin.table.resetFailed')}</button>
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => { bookActions.handleDeleteBook(book.id); close(); }} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-red-600 hover:bg-red-50 transition-colors"><Trash2 size={14} /> {t('admin.table.delete')}</button>
    </div>
  );
};
