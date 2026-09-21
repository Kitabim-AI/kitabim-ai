import React, { useState, useEffect, useMemo } from 'react';
import {
  Search,
  X,
  BookOpen,
  BookMarked,
  History,
  Pencil,
  Trash2,
  Check,
  Quote,
  BookmarkPlus,
  RefreshCw,
} from 'lucide-react';
import { Bookmark } from '@shared/types';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { GuestAuthWall } from '../reader/GuestAuthWall';

export interface UnifiedReadingBook {
  bookId: string;
  bookTitle: string;
  bookCoverUrl: string | null;
  pageNumber?: number;
  updatedAt: string;
  bookmarks: Bookmark[];
}

interface ReadingBookmarksTabProps {
  onOpenBook: (bookId: string, pageNumber?: number) => void;
  onOpenBookmark: (bookId: string, pageNumber: number, quoteText?: string | null) => void;
  onCountChange?: (count: number) => void;
}

export const ReadingBookmarksTab: React.FC<ReadingBookmarksTabProps> = ({
  onOpenBook,
  onOpenBookmark,
  onCountChange,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();

  const [books, setBooks] = useState<UnifiedReadingBook[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [query, setQuery] = useState<string>('');

  // Editing state for bookmark rename
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState<string>('');

  useEffect(() => {
    if (!isAuthenticated) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    const fetchData = async () => {
      setIsLoading(true);
      try {
        const [progressList, bookmarksList] = await Promise.all([
          PersistenceService.listReadingProgress(),
          PersistenceService.listBookmarks(),
        ]);

        if (!isMounted) return;

        const bookMap = new Map<string, UnifiedReadingBook>();

        // Incorporate reading progress items
        for (const item of progressList) {
          bookMap.set(item.bookId, {
            bookId: item.bookId,
            bookTitle: item.bookTitle || '',
            bookCoverUrl: item.bookCoverUrl,
            pageNumber: item.pageNumber,
            updatedAt: item.updatedAt,
            bookmarks: [],
          });
        }

        // Incorporate bookmarks
        for (const bm of bookmarksList) {
          const existing = bookMap.get(bm.bookId);
          if (existing) {
            existing.bookmarks.push(bm);
            if (!existing.bookTitle && bm.bookTitle) {
              existing.bookTitle = bm.bookTitle;
            }
            if (bm.createdAt > existing.updatedAt) {
              existing.updatedAt = bm.createdAt;
            }
          } else {
            bookMap.set(bm.bookId, {
              bookId: bm.bookId,
              bookTitle: bm.bookTitle || '',
              bookCoverUrl: null,
              pageNumber: undefined,
              updatedAt: bm.createdAt,
              bookmarks: [bm],
            });
          }
        }

        // Sort books by most recent activity
        const combined = Array.from(bookMap.values()).sort((a, b) =>
          b.updatedAt.localeCompare(a.updatedAt)
        );

        // Sort bookmarks inside each book by page number
        for (const b of combined) {
          b.bookmarks.sort((b1, b2) => b1.pageNumber - b2.pageNumber);
        }

        setBooks(combined);
      } catch (err) {
        console.error('Failed to load reading & bookmarks', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchData();
    return () => {
      isMounted = false;
    };
  }, [isAuthenticated]);

  // Report count of books to parent
  useEffect(() => {
    onCountChange?.(books.length);
  }, [books.length, onCountChange]);

  const filteredBooks = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return books;

    return books
      .map((book) => {
        const titleMatches = book.bookTitle.toLowerCase().includes(q);
        const matchingBookmarks = book.bookmarks.filter(
          (bm) =>
            bm.name.toLowerCase().includes(q) ||
            (bm.quoteText && bm.quoteText.toLowerCase().includes(q))
        );

        if (titleMatches) {
          return book;
        }
        if (matchingBookmarks.length > 0) {
          return {
            ...book,
            bookmarks: matchingBookmarks,
          };
        }
        return null;
      })
      .filter((b): b is UnifiedReadingBook => b !== null);
  }, [books, query]);

  const handleDeleteBookmark = async (id: string, bookId: string) => {
    try {
      await PersistenceService.deleteBookmark(id);
      setBooks((prev) =>
        prev
          .map((b) => {
            if (b.bookId !== bookId) return b;
            return {
              ...b,
              bookmarks: b.bookmarks.filter((bm) => bm.id !== id),
            };
          })
          // If a book only had bookmarks and no reading progress, remove if 0 bookmarks left
          .filter((b) => b.pageNumber !== undefined || b.bookmarks.length > 0)
      );
    } catch (err) {
      console.error('Failed to delete bookmark', err);
    }
  };

  const handleStartRename = (bm: Bookmark) => {
    setEditingId(bm.id);
    setEditName(bm.name);
  };

  const handleSaveRename = async (id: string, bookId: string) => {
    const trimmed = editName.trim();
    if (trimmed) {
      try {
        await PersistenceService.renameBookmark(id, trimmed);
        setBooks((prev) =>
          prev.map((b) => {
            if (b.bookId !== bookId) return b;
            return {
              ...b,
              bookmarks: b.bookmarks.map((bm) =>
                bm.id === id ? { ...bm, name: trimmed } : bm
              ),
            };
          })
        );
      } catch (err) {
        console.error('Failed to rename bookmark', err);
      }
    }
    setEditingId(null);
  };

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  return (
    <div className="space-y-8 animate-fade-in" dir="rtl">
      {/* Search Header (Aligned with Dictionary Panels) */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
            <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={
              t('library.readingBookmarks.searchPlaceholder') ||
              'كىتاب ۋە خەتكۈشلەردىن ئىزدەڭ...'
            }
            className={`w-full pr-11 md:pr-14 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl uyghur-text outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] text-slate-800 dark:text-slate-100 transition-all shadow-sm placeholder:text-slate-400 dark:placeholder:text-slate-500 text-base md:pl-14 ${
              query ? 'pl-11' : 'pl-4'
            }`}
            dir="rtl"
          />
          {query && (
            <div className="absolute inset-y-0 left-3 md:left-4 flex items-center gap-1 md:gap-2 z-10">
              <button
                onClick={() => setQuery('')}
                className="p-1.5 md:p-2 text-slate-300 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 transition-colors cursor-pointer"
                title={t('common.clear')}
              >
                <X strokeWidth={2.5} className="w-4 h-4 md:w-5 md:h-5" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      {isLoading ? (
        <div className="py-32 w-full flex flex-col items-center justify-center">
          <RefreshCw className="w-10 h-10 text-[#0369a1] dark:text-[#38bdf8] animate-spin mb-4" />
          <p className="text-sm font-semibold text-slate-500 dark:text-slate-400 uyghur-text">
            {t('common.loading')}
          </p>
        </div>
      ) : books.length === 0 ? (
        /* Empty State: No Books Read or Bookmarked */
        <div className="col-span-full py-28 sm:py-36 w-full flex flex-col items-center justify-center glass-panel rounded-[48px] border border-slate-200/80 dark:border-slate-800">
          <div className="p-8 sm:p-10 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 rounded-[40px] mb-6 sm:mb-8 relative">
            <BookMarked
              className="w-16 h-16 sm:w-20 sm:h-20 text-[#0369a1] dark:text-[#38bdf8]"
              strokeWidth={1.5}
            />
          </div>
          <h4 className="text-xl sm:text-2xl font-black text-[#1a1a1a] dark:text-slate-100 mb-3 text-center uyghur-text">
            {t('library.tabs.readingAndBookmarks') || 'ئوقۇۋاتقانلىرىم ۋە خەتكۈشلەر'}
          </h4>
          <p className="text-[#94a3b8] dark:text-slate-400 font-medium text-sm sm:text-base max-w-md text-center uyghur-text px-4">
            {t('library.readingBookmarks.empty') ||
              'سىز تېخى ھېچقانداق كىتاب ئوقۇمىدىڭىز ياكى خەتكۈش قويمىدىڭىز'}
          </p>
        </div>
      ) : filteredBooks.length === 0 && query ? (
        /* Empty Search Results */
        <div className="py-24 text-center space-y-3 glass-panel rounded-3xl border border-slate-200/80 dark:border-slate-800">
          <p className="text-slate-500 dark:text-slate-400 font-medium text-base uyghur-text">
            {t('common.noResults') || 'ھېچقانداق نەتىجە تېپىلمىدى'}
          </p>
          <button
            onClick={() => setQuery('')}
            className="text-xs font-bold text-[#0369a1] dark:text-[#38bdf8] hover:underline cursor-pointer uyghur-text"
          >
            {t('common.clearFilter') || 'ئىزدەشنى تازىلاش'}
          </button>
        </div>
      ) : (
        /* Books List with Side-by-Side Cover (Right) & Bookmarks (Left) */
        <div className="space-y-6 sm:space-y-8">
          {filteredBooks.map((book) => {
            const rawUrl = book.bookCoverUrl;
            const coverSrc = !rawUrl
              ? `/api/covers/${book.bookId}.jpg`
              : rawUrl.startsWith('covers/')
              ? `/api/${rawUrl}`
              : rawUrl;

            return (
              <div
                key={book.bookId}
                className="bg-white/80 dark:bg-slate-900/60 backdrop-blur-xl rounded-3xl p-5 sm:p-7 border border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-sm flex flex-col md:flex-row items-stretch gap-6 lg:gap-8 transition-all hover:border-[#0369a1]/25 dark:hover:border-[#38bdf8]/25"
              >
                {/* Right Side (RTL Start): Book Cover Card & Reading Progress */}
                <div className="w-full md:w-56 lg:w-64 shrink-0 flex flex-col items-center sm:items-start">
                  <div
                    onClick={() => onOpenBook(book.bookId, book.pageNumber)}
                    className="group relative w-40 sm:w-48 md:w-full aspect-[5/7] rounded-2xl overflow-hidden shadow-md hover:shadow-xl transition-all duration-300 cursor-pointer bg-slate-100 dark:bg-slate-800"
                  >
                    <img
                      src={coverSrc}
                      alt={book.bookTitle}
                      className="absolute inset-0 w-full h-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
                      onError={(e) => {
                        e.currentTarget.style.display = 'none';
                        const fallback = e.currentTarget
                          .nextElementSibling as HTMLElement | null;
                        if (fallback) fallback.style.display = 'flex';
                      }}
                    />
                    <div
                      style={{ display: 'none' }}
                      className="absolute inset-0 bg-gradient-to-br from-[#FFD54F] via-[#FF9800] to-[#F06292] items-center justify-center"
                    >
                      <div
                        className="absolute inset-0 opacity-20"
                        style={{
                          backgroundImage:
                            'repeating-linear-gradient(45deg, transparent, transparent 20px, rgba(255,255,255,0.1) 20px, rgba(255,255,255,0.1) 40px)',
                        }}
                      />
                      <span className="text-5xl drop-shadow-lg">📖</span>
                    </div>

                    {/* Progress Pill on Top */}
                    {book.pageNumber !== undefined && (
                      <div className="absolute top-2.5 start-2.5 px-2.5 py-1 bg-slate-950/75 dark:bg-slate-900/85 backdrop-blur-md text-white rounded-xl text-[11px] font-bold flex items-center gap-1.5 shadow-md border border-white/10">
                        <History size={12} className="text-[#38bdf8]" />
                        <span className="uyghur-text">{book.pageNumber}-بەت</span>
                      </div>
                    )}
                  </div>

                  {/* Book Title */}
                  <h3
                    onClick={() => onOpenBook(book.bookId, book.pageNumber)}
                    className="font-bold text-base sm:text-lg text-slate-800 dark:text-slate-100 uyghur-text line-clamp-2 mt-3 cursor-pointer hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors text-center sm:text-start w-full"
                    title={book.bookTitle}
                  >
                    {book.bookTitle || t('common.untitled') || 'نامسىز كىتاب'}
                  </h3>

                  {/* Continue Reading Action Button */}
                  <button
                    onClick={() => onOpenBook(book.bookId, book.pageNumber)}
                    className="w-full mt-3 py-2 px-3 flex items-center justify-center gap-2 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 text-xs sm:text-sm font-bold rounded-xl hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all shadow-md shadow-[#0369a1]/15 active:scale-95 cursor-pointer"
                  >
                    <BookOpen size={14} strokeWidth={2.5} />
                    <span className="uyghur-text">
                      {t('library.readingBookmarks.continueReading') || 'داۋاملىق ئوقۇش'}
                    </span>
                  </button>
                </div>

                {/* Left Side (RTL End): Bookmarks List for This Book */}
                <div className="flex-1 flex flex-col justify-start border-t md:border-t-0 md:border-r border-slate-200/80 dark:border-slate-800/80 pt-4 md:pt-0 md:pr-6 lg:pr-8 min-w-0">
                  {/* Bookmarks Section Header */}
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800/60 mb-3">
                    <div className="flex items-center gap-2">
                      <BookMarked size={16} className="text-[#0369a1] dark:text-[#38bdf8]" />
                      <span className="text-xs sm:text-sm font-bold text-slate-700 dark:text-slate-300 uyghur-text">
                        {t('common.bookmarks') || 'خەتكۈشلەر'}
                      </span>
                      <span className="px-2 py-0.5 text-[11px] font-semibold bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-full">
                        {book.bookmarks.length}
                      </span>
                    </div>
                  </div>

                  {/* Bookmarks Items or Empty State */}
                  {book.bookmarks.length > 0 ? (
                    <div className="space-y-3 overflow-y-auto max-h-[380px] pe-1 [scrollbar-width:thin]">
                      {book.bookmarks.map((bm) => (
                        <div
                          key={bm.id}
                          className="group/bm relative p-3 sm:p-4 rounded-2xl bg-white/70 dark:bg-slate-800/40 border border-[#0369a1]/10 dark:border-[#38bdf8]/10 hover:border-[#0369a1]/30 dark:hover:border-[#38bdf8]/30 transition-all shadow-sm hover:shadow-md"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2.5 min-w-0 flex-1">
                              {/* Page Badge */}
                              <span className="px-2 py-0.5 text-[11px] font-bold rounded-lg bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] shrink-0 uyghur-text">
                                {bm.pageNumber}-بەت
                              </span>

                              {/* Title / Inline Rename Input */}
                              {editingId === bm.id ? (
                                <div className="flex items-center gap-1.5 flex-1 min-w-0">
                                  <input
                                    type="text"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === 'Enter')
                                        handleSaveRename(bm.id, book.bookId);
                                      if (e.key === 'Escape') setEditingId(null);
                                    }}
                                    autoFocus
                                    className="px-2 py-1 text-xs sm:text-sm rounded-lg border border-[#0369a1] dark:border-[#38bdf8] bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 outline-none flex-1 uyghur-text"
                                  />
                                  <button
                                    onClick={() => handleSaveRename(bm.id, book.bookId)}
                                    className="p-1 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/40 rounded-lg cursor-pointer"
                                    title={t('common.save') || 'Save'}
                                  >
                                    <Check size={14} />
                                  </button>
                                  <button
                                    onClick={() => setEditingId(null)}
                                    className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg cursor-pointer"
                                    title={t('common.cancel') || 'Cancel'}
                                  >
                                    <X size={14} />
                                  </button>
                                </div>
                              ) : (
                                <span
                                  onClick={() =>
                                    onOpenBookmark(
                                      book.bookId,
                                      bm.pageNumber,
                                      bm.quoteText
                                    )
                                  }
                                  className="text-xs sm:text-sm font-medium text-slate-700 dark:text-slate-200 truncate cursor-pointer hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors uyghur-text flex-1"
                                >
                                  {bm.name}
                                </span>
                              )}
                            </div>

                            {/* Action Buttons */}
                            {editingId !== bm.id && (
                              <div className="flex items-center gap-1 shrink-0 opacity-80 group-hover/bm:opacity-100 transition-opacity">
                                <button
                                  onClick={() => handleStartRename(bm)}
                                  className="p-1 text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors rounded-lg cursor-pointer"
                                  title={t('bookmarks.rename') || 'Rename'}
                                >
                                  <Pencil size={13} />
                                </button>
                                <button
                                  onClick={() =>
                                    handleDeleteBookmark(bm.id, book.bookId)
                                  }
                                  className="p-1 text-slate-400 hover:text-red-500 dark:hover:text-red-400 transition-colors rounded-lg cursor-pointer"
                                  title={t('bookmarks.delete') || 'Delete'}
                                >
                                  <Trash2 size={13} />
                                </button>
                              </div>
                            )}
                          </div>

                          {/* Passage Quote (if any) */}
                          {bm.quoteText && (
                            <div
                              onClick={() =>
                                onOpenBookmark(
                                  book.bookId,
                                  bm.pageNumber,
                                  bm.quoteText
                                )
                              }
                              className="mt-2.5 p-2.5 rounded-xl bg-slate-50/80 dark:bg-slate-900/50 border-r-2 border-[#0369a1] dark:border-[#38bdf8] flex items-start gap-2 cursor-pointer hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/5 transition-colors"
                            >
                              <Quote
                                size={12}
                                className="text-[#0369a1] dark:text-[#38bdf8] shrink-0 mt-0.5 rotate-180"
                              />
                              <p className="text-xs text-slate-600 dark:text-slate-300 font-serif italic line-clamp-2 leading-relaxed uyghur-text">
                                "{bm.quoteText}"
                              </p>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    /* Book Has No Bookmarks Yet */
                    <div className="h-full min-h-[140px] flex flex-col items-center justify-center text-center p-6 rounded-2xl border border-dashed border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30">
                      <BookmarkPlus
                        size={28}
                        className="text-slate-300 dark:text-slate-600 mb-2"
                      />
                      <p className="text-xs sm:text-sm font-semibold text-slate-500 dark:text-slate-400 uyghur-text">
                        {t('library.readingBookmarks.noBookmarks') ||
                          'بۇ كىتابتا تېخى خەتكۈش يوق'}
                      </p>
                      <p className="text-[11px] text-slate-400 dark:text-slate-500 max-w-xs mt-1 uyghur-text">
                        {t('library.readingBookmarks.noBookmarksHint') ||
                          'كىتابنى ئوقۇۋاتقاندا بېتىگە ياكى مەزمۇنىغا خەتكۈش قوشالايسىز'}
                      </p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
export default ReadingBookmarksTab;
