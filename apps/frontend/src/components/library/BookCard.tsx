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
    case 'ocr_done': return 'bg-indigo-50 text-indigo-600';
    case 'chunked': return 'bg-amber-50 text-amber-600';
    case 'indexing': return 'bg-violet-50 text-violet-600';
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
      className="group relative w-full max-w-[300px] bg-white/80 backdrop-blur-xl rounded-3xl p-7 cursor-pointer transition-all duration-300 border border-[#0369a1]/10 hover:border-[#0369a1]/30 hover:-translate-y-2 hover:shadow-[0_20px_40px_rgba(3,105,161,0.15)] shadow-lg"
    >
      {/* Book Cover */}
      <div className="relative w-full aspect-[5/7] mb-6 rounded-2xl overflow-hidden shadow-lg transition-transform duration-500 group-hover:scale-105 group-hover:shadow-2xl">
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
      <div className="text-right space-y-2" dir="rtl">
        <h3 className="font-bold text-[#1a1a1a] text-lg leading-snug line-clamp-2 min-h-[3.5rem]" title={titleWithVolume}>
          {titleWithVolume}
        </h3>

        {displayAuthor && displayAuthor !== 'Unknown Author' && (
          <p className="text-sm text-[#0369a1] font-medium truncate">
            {displayAuthor}
          </p>
        )}

        <div className="flex items-center justify-between text-xs text-[#64748b] pt-2 border-t border-[#0369a1]/5">
          <div className="flex items-center gap-2">
            <span className="bg-[#0369a1]/5 text-[#0369a1] px-2.5 py-1 rounded-lg font-bold">
              {book.category?.[0] || t('common.book')}
            </span>
            {book.status && book.status !== 'ready' && (
              <span className={`px-2 py-1 rounded-lg font-bold uppercase text-[10px] ${getStatusStyles(book.status)}`}>
                {t(`bookCard.${book.status}`) || book.status}
              </span>
            )}
            {book.status === 'ready' && (book.readCount ?? 0) > 0 && (
              <span className="flex items-center gap-1 text-[#64748b] text-[10px] font-semibold">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                  <circle cx="12" cy="12" r="3"/>
                </svg>
                {book.readCount}
              </span>
            )}
          </div>
          <span className="font-semibold">{t('book.pagesCount', { count: book.totalPages || (book as any).total_pages || 0 })}</span>
        </div>
      </div>
    </div>
  );
};
