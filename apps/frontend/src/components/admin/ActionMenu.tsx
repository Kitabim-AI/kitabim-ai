import React from 'react';
import { BookOpen, Shield, Globe, ScanText, RotateCcw, RefreshCw, Trash2, CheckCircle } from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';
import { useHasRole } from '../../hooks/useAuth';

interface ActionMenuProps {
  book: Book;
  close: () => void;
}

export const ActionMenu: React.FC<ActionMenuProps> = ({ book, close }) => {
  const { bookActions } = useAppContext();
  const { t } = useI18n();
  const isEditorOrAdmin = useHasRole('admin', 'editor');
  const isStale = (book.status === 'ocr_processing' || book.status === 'indexing') && book.processingLockExpiresAt && new Date(book.processingLockExpiresAt) < new Date();
  const isActuallyProcessing = (book.status === 'ocr_processing' || book.status === 'indexing') && !isStale;
  const hasFailedPages = (book.errorCount ?? 0) > 0 || (book.pages?.some(r => r.status === 'error') ?? false);
  // Start OCR: only for books that haven't started processing yet
  const canStartOcr = book.status === 'pending';
  // Retry: book errored out or has page-level failures or is stuck (stale lock)
  const canRetry = (hasFailedPages || book.status === 'error' || isStale) && !isActuallyProcessing;
  // Reindex: re-embed an already-ready book, or resume indexing for ocr_done books
  const canReindex = book.status === 'ready' || book.status === 'ocr_done';
  // Force complete: unstick actively processing, stale, or errored books
  const canForceComplete = isEditorOrAdmin && (isStale || book.status === 'ocr_processing' || book.status === 'indexing' || book.status === 'error');

  return (
    <div className="absolute left-0 top-full mt-2 w-52 glass-panel shadow-2xl z-50 py-2 rounded-[16px] border border-[#0369a1]/10">
      <button onClick={() => { bookActions.openReader(book, () => { }, () => { }, () => { }); close(); }} disabled={book.status === 'pending' || book.status === 'uploading'} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-[#1a1a1a] hover:bg-[#0369a1]/10 disabled:text-slate-200 transition-colors"><BookOpen size={14} /> {t('admin.table.view')}</button>
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => { bookActions.handleStartOcr(book.id); close(); }} disabled={!canStartOcr} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-[#0369a1] hover:bg-[#0369a1]/10 disabled:text-slate-200 transition-colors"><ScanText size={14} /> {t('admin.table.startOcr')}</button>
      <button onClick={() => { bookActions.handleRetryFailedOcr(book); close(); }} disabled={!canRetry} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-amber-600 hover:bg-amber-50 disabled:text-slate-200 transition-colors"><RotateCcw size={14} /> {t('admin.table.retryOcr')}</button>
      <button onClick={() => { bookActions.handleReindexBook(book.id); close(); }} disabled={!canReindex} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-blue-600 hover:bg-blue-50 disabled:text-slate-200 transition-colors"><RefreshCw size={14} /> {t('admin.table.reindex')}</button>
      {isEditorOrAdmin && <button onClick={() => { bookActions.handleForceComplete(book); close(); }} disabled={!canForceComplete} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-emerald-600 hover:bg-emerald-50 disabled:text-slate-200 transition-colors"><CheckCircle size={14} /> {t('admin.table.forceComplete')}</button>}
      <div className="h-px bg-slate-100 my-1 mx-4" />
      <button onClick={() => { bookActions.handleDeleteBook(book.id); close(); }} className="w-full flex items-center gap-3 px-4 py-2 text-sm font-black text-red-600 hover:bg-red-50 transition-colors"><Trash2 size={14} /> {t('admin.table.delete')}</button>
    </div>
  );
};
