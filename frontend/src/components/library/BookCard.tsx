import React from 'react';
import { FileText, Trash2, Loader2, CheckCircle2 } from 'lucide-react';
import { Book } from '../../types';

interface BookCardProps {
  book: Book;
  onClick: (book: Book) => void;
  onDelete?: (bookId: string) => void;
}

export const BookCard: React.FC<BookCardProps> = ({ book, onClick, onDelete }) => {
  return (
    <div
      onClick={() => onClick(book)}
      className="flex flex-col gap-3 cursor-pointer group"
    >
      <div className="book-cover aspect-[3/4] bg-slate-100 relative shadow-lg">
        {book.coverUrl ? (
          <img
            src={`${book.coverUrl}?t=${book.lastUpdated ? new Date(book.lastUpdated).getTime() : ''}`}
            alt={book.title}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center bg-indigo-50 border-l-[6px] border-indigo-200 p-4 text-center">
            <FileText className={`w-8 h-8 mb-2 ${book.status === 'ready' ? 'text-slate-300' : 'text-indigo-300'}`} />
            <span className="text-[10px] font-bold text-indigo-300 break-words leading-tight uppercase opacity-50">
              {book.title.substring(0, 20)}
            </span>
          </div>
        )}
        <div className="book-spine-line" />

        {/* Hover Controls */}
        {onDelete && (
          <div className="absolute top-2 left-2 opacity-0 group-hover:opacity-100 transition-all transform -translate-x-2 group-hover:translate-x-0 z-20">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(book.id);
              }}
              className="p-1.5 bg-white/90 hover:bg-red-500 hover:text-white text-slate-500 rounded-lg shadow-xl backdrop-blur-md transition-all"
            >
              <Trash2 size={14} />
            </button>
          </div>
        )}

        <div className="absolute top-2 right-2 flex flex-col gap-1.5 z-20">
          {book.status !== 'ready' ? (
            <div className="p-1.5 bg-white/90 rounded-full shadow-lg backdrop-blur-sm">
              <Loader2 size={12} className="text-indigo-600 animate-spin" />
            </div>
          ) : (
            <div className="p-1.5 bg-green-500/90 text-white rounded-full shadow-lg backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-all scale-75 group-hover:scale-100">
              <CheckCircle2 size={12} />
            </div>
          )}
        </div>

        {/* Quick Info Overlay on Hover */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2 pointer-events-none">
          <span className="text-[9px] text-white font-black uppercase tracking-tighter bg-indigo-600/80 px-1.5 py-0.5 rounded">
            {book.status === 'ready' ? 'OPEN READER' : 'PROCESSING'}
          </span>
        </div>
      </div>

      <div className="px-1 mt-1">
        <h3 className="font-bold text-slate-900 text-sm leading-tight line-clamp-2 text-right transition-colors group-hover:text-indigo-600" dir="rtl">
          {book.title}
        </h3>
        <div className="flex items-center justify-end gap-1.5 mt-1 opacity-70">
          <span className="text-xs font-bold text-slate-500">{book.totalPages} Pages</span>
          <div className="w-1 h-1 rounded-full bg-slate-300" />
          <span className={`text-xs font-bold ${book.status === 'ready' ? 'text-indigo-600' : 'text-amber-600'}`}>
            {book.status.toUpperCase()}
          </span>
        </div>
      </div>
    </div>
  );
};
