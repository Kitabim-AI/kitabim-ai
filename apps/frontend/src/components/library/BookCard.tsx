import React from 'react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';

interface BookCardProps {
  book: Book;
  onClick: (book: Book) => void;
  onDelete?: (bookId: string) => void;
}

const getStatusStyles = (status: string) => {
  switch (status.toLowerCase()) {
    case 'ready': return 'bg-emerald-50 text-emerald-600';
    case 'ocr_done': return 'bg-blue-50 text-blue-600';
    case 'chunking': return 'bg-indigo-50 text-indigo-600';
    case 'indexing': return 'bg-orange-50 text-orange-600';
    case 'ocr': return 'bg-blue-50 text-blue-600';
    case 'embedding': return 'bg-orange-50 text-orange-600';
    case 'ocr_processing': return 'bg-blue-50 text-blue-600';
    case 'error': return 'bg-red-50 text-red-500';
    case 'pending': return 'bg-amber-50 text-amber-600';
    default: return 'bg-slate-50 text-slate-500';
  }
};

export const BookCard: React.FC<BookCardProps> = ({ book, onClick }) => {
  const { t } = useI18n();
  const titleWithVolume = book.volume !== null && book.volume !== undefined && book.volume !== ""
    ? `${book.title} (${t('book.volume', { volume: book.volume })})`
    : book.title;
  const displayAuthor = book.author?.trim();

  return (
    <div
      onClick={() => onClick(book)}
      className="group relative w-full max-w-[300px] bg-white/80 backdrop-blur-xl rounded-2xl sm:rounded-3xl p-3 sm:p-5 cursor-pointer transition-all duration-300 border border-[#0369a1]/10 hover:border-[#0369a1]/30 hover:-translate-y-1 hover:shadow-[0_12px_24px_rgba(3,105,161,0.1)] shadow-md"
    >
      {/* Book Cover */}
      <div className="relative w-full aspect-[5/7] mb-3 sm:mb-5 rounded-xl sm:rounded-2xl overflow-hidden shadow-lg transition-transform duration-500 group-hover:scale-[1.03] group-hover:shadow-xl">
        {book.coverUrl ? (
          <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${book.coverUrl})` }} />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-[#FFD54F] via-[#FF9800] to-[#F06292] flex items-center justify-center">
            <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 20px, rgba(255,255,255,0.1) 20px, rgba(255,255,255,0.1) 40px)' }} />
            <span className="text-5xl drop-shadow-lg">📖</span>
          </div>
        )}
      </div>

      {/* Book Info */}
      <div className="text-right space-y-1 sm:space-y-4" dir="rtl">
        <h3 className="font-bold text-[#1a1a1a] text-sm sm:text-lg leading-snug line-clamp-2 min-h-[2.5rem] sm:min-h-[3.5rem]" title={titleWithVolume}>
          {titleWithVolume}
        </h3>
        <div className="flex items-center justify-between text-[10px] sm:text-sm pt-2 border-t border-[#0369a1]/5">
          {/* Right side: Author (in RTL) */}
          <div className="text-[#0369a1] font-medium truncate max-w-[60%]">
            {displayAuthor && displayAuthor !== 'Unknown Author' ? displayAuthor : ''}
          </div>

          {/* Left side: Stats & Status (in RTL) */}
          <div className="flex items-center gap-2 sm:gap-3 text-[#64748b] shrink-0 font-medium">
            {book.pipelineStep && book.pipelineStep !== 'ready' && (
              <span className={`px-1.5 py-0.5 rounded-md font-bold uppercase text-[9px] sm:text-[10px] ${getStatusStyles(book.pipelineStep)}`}>
                {t(`bookCard.pipeline.${book.pipelineStep}`) || book.pipelineStep}
              </span>
            )}

            {book.status === 'ready' && (book.readCount ?? 0) > 0 && (
              <span className="flex items-center gap-1 text-[10px] sm:text-xs">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="sm:w-3.5 sm:h-3.5">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                {book.readCount}
              </span>
            )}

            <span className="text-[10px] sm:text-xs">
              {t('book.pagesCount', { count: book.totalPages || (book as any).total_pages || 0 })}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
