import React from 'react';
import { Database, Zap, Library } from 'lucide-react';
import { Book } from '../../types';
import { BookCard } from './BookCard';

interface LibraryViewProps {
  books: Book[];
  isLoadingMore: boolean;
  hasMore: boolean;
  searchQuery: string;
  onBookClick: (book: Book) => void;
  onDeleteBook: (bookId: string) => void;
  loaderRef: React.RefObject<HTMLDivElement>;
  loadMore: () => void;
}

export const LibraryView: React.FC<LibraryViewProps> = ({
  books,
  isLoadingMore,
  hasMore,
  searchQuery,
  onBookClick,
  onDeleteBook,
  loaderRef,
  loadMore,
}) => {
  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore) {
          loadMore();
        }
      },
      { threshold: 0.1 }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, loadMore, loaderRef]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <header>
          <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <Database className="text-indigo-600 w-6 h-6" />
            Global Knowledge Base
          </h2>
          <p className="text-slate-500">Shared collection of pre-processed Uyghur literature on Kitabim.AI</p>
        </header>
        <div className="flex items-center gap-2 text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">
          <Zap size={14} className="text-amber-500" />
          DEDUPLICATION ACTIVE
        </div>
      </div>

      <div className="book-shelf-row">
        {books.map(book => (
          <BookCard
            key={book.id}
            book={book}
            onClick={onBookClick}
            onDelete={onDeleteBook}
          />
        ))}
        {books.length === 0 && !isLoadingMore && (
          <div className="col-span-full py-20 text-center border-2 border-dashed border-slate-200 rounded-3xl">
            <Library className="w-12 h-12 text-slate-300 mx-auto mb-4" />
            <p className="text-slate-500 font-medium">
              {searchQuery ? 'No books match your search.' : 'No books indexed in the global database yet.'}
            </p>
          </div>
        )}
      </div>

      {/* Infinite Scroll Trigger */}
      <div ref={loaderRef} className="h-32 flex items-center justify-center">
        {isLoadingMore && (
          <div className="flex flex-col items-center gap-3 animate-in fade-in slide-in-from-bottom-2">
            <div className="relative">
              <div className="w-10 h-10 border-4 border-indigo-100 border-t-indigo-600 rounded-full animate-spin"></div>
              <div className="absolute inset-0 flex items-center justify-center">
                <Zap size={14} className="text-amber-500 animate-pulse" />
              </div>
            </div>
            <span className="text-xs font-bold text-indigo-600 uppercase tracking-widest">Loading more treasures...</span>
          </div>
        )}
        {!hasMore && books.length > 0 && (
          <div className="flex flex-col items-center gap-2 opacity-40">
            <Library size={24} className="text-slate-400" />
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">End of the collection</p>
          </div>
        )}
      </div>
    </div>
  );
};
