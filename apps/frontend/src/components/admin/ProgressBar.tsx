import React from 'react';
import { Book } from '@shared/types';

interface ProgressBarProps {
  book: Book;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ book }) => {
  const percent = ((book.completedCount || book.pages?.filter(p => p.status === 'completed').length) / (book.totalPages || 1)) * 100;
  const isStale = book.status === 'processing' && book.processingLockExpiresAt && new Date(book.processingLockExpiresAt) < new Date();
  const color = (book.status === 'error' || isStale) ? 'bg-red-500' : book.status === 'ready' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' : 'bg-[#75C5F0] animate-pulse';

  return (
    <div className="w-full bg-[#0369a1]/10 h-1.5 rounded-full overflow-hidden">
      <div className={`h-full transition-all duration-500 ${color}`} style={{ width: `${percent}%` }} />
    </div>
  );
};
