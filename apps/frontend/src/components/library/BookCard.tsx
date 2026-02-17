import React from 'react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';

interface BookCardProps {
  book: Book;
  onClick: (book: Book) => void;
  onDelete?: (bookId: string) => void;
}

export const BookCard: React.FC<BookCardProps> = ({ book, onClick }) => {
  const { t } = useI18n();
  const titleWithVolume = book.volume !== null && book.volume !== undefined && book.volume !== ""
    ? `${book.title} (${t('book.volume', { volume: book.volume })})`
    : book.title;
  const displayAuthor = book.author?.trim();

  return (
    <div
      onClick={() => onClick(book)}
      className="group relative w-full max-w-[200px] bg-white/80 backdrop-blur-[20px] rounded-3xl p-7 cursor-pointer transition-all duration-400 border border-[rgba(255,193,7,0.15)] hover:border-[rgba(255,193,7,0.3)]"
      style={{
        backdropFilter: 'blur(20px) saturate(180%)',
        WebkitBackdropFilter: 'blur(20px) saturate(180%)',
        boxShadow: '0 8px 32px rgba(255, 193, 7, 0.08), 0 2px 8px rgba(156, 39, 176, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
        transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-16px) scale(1.03)';
        e.currentTarget.style.boxShadow = '0 12px 40px rgba(255, 193, 7, 0.15), 0 8px 20px rgba(156, 39, 176, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.9)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = '';
        e.currentTarget.style.boxShadow = '0 8px 32px rgba(255, 193, 7, 0.08), 0 2px 8px rgba(156, 39, 176, 0.05), inset 0 1px 0 rgba(255, 255, 255, 0.8)';
      }}
    >
      {/* Book Cover - Matching Prototype */}
      <div className="relative w-full aspect-[5/7] mb-4 rounded-2xl overflow-hidden transition-all duration-400 group-hover:scale-105"
        style={{
          background: book.coverUrl ? `url(${book.coverUrl}) center/cover` : 'linear-gradient(135deg, #FFD54F 0%, #FF9800 50%, #F06292 100%)',
          boxShadow: '0 8px 24px rgba(255, 152, 0, 0.3), inset 0 2px 0 rgba(255, 255, 255, 0.3)'
        }}
      >
        {!book.coverUrl && (
          <>
            <div className="absolute inset-0 flex items-center justify-center text-white text-5xl font-bold">
              📖
            </div>
            <div className="absolute inset-0"
              style={{
                background: 'repeating-linear-gradient(45deg, transparent, transparent 20px, rgba(255, 255, 255, 0.05) 20px, rgba(255, 255, 255, 0.05) 40px)'
              }} />
          </>
        )}
      </div>

      {/* Book Info - Matching Prototype */}
      <div className="text-right" dir="rtl">
        <h3 className="font-bold text-[#1a1a1a] text-[1.125rem] leading-snug mb-2 line-clamp-2">
          {titleWithVolume}
        </h3>
        {displayAuthor && displayAuthor !== 'Unknown Author' && (
          <p className="text-[0.875rem] text-[#0369a1] mb-3">
            {displayAuthor}
          </p>
        )}
        <div className="flex items-center justify-between text-[0.875rem] text-[#94a3b8]">
          <span className="bg-[#0369a1]/10 text-[#0369a1] px-3 py-1 rounded-lg font-semibold">
            {book.category?.[0] || t('common.book')}
          </span>
          <span>{t('book.pagesCount', { count: book.pages?.length || 0 })}</span>
        </div>
      </div>
    </div>
  );
};
