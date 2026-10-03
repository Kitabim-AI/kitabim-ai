# Separate Reading History and Bookmarks Tabs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate books the user has read (reading history) and user bookmarks into two distinct tabs in the Library view, with the bookmarks tab strictly showing books that have at least one bookmark.

**Architecture:** 
- In `LibraryView.tsx`, provide 3 top-level tabs: `all-books`, `reading` (Reading History), and `bookmarks` (Bookmarks only).
- `ReadingHistoryTab.tsx` loads reading progress via `PersistenceService.listReadingProgress()` and renders a book card grid where clicking a card opens the book at the last-read page.
- `BookmarksTab.tsx` keeps the existing rich bookmarks UX, but strictly filters out books with 0 bookmarks (`book.bookmarks.length > 0`).

**Tech Stack:** React 19, TypeScript, Tailwind CSS, Lucide React, Vitest, Testing Library.

## Global Constraints
- Naming & copy: Uyghur and English translations in `apps/frontend/src/locales/`
- Direct card click: In `ReadingHistoryTab`, clicking the book card calls `onOpenBook(book.bookId, book.pageNumber)` directly. No separate "Continue Reading" button.
- Bookmarks filter: `BookmarksTab` must only render books where `bookmarks.length > 0`.
- All tests must pass: `npm test` in `apps/frontend`.

---

### Task 1: Update Localization Strings for Tabs

**Files:**
- Modify: `apps/frontend/src/locales/ug.json`
- Modify: `apps/frontend/src/locales/en.json`

**Interfaces:**
- Consumes: Existing locale structure under `library.tabs` and `library.readingHistory`
- Produces: `library.tabs.reading`, `library.tabs.bookmarks`, `library.readingHistory.*`

- [ ] **Step 1: Update `apps/frontend/src/locales/ug.json`**

In `apps/frontend/src/locales/ug.json`, update `library.tabs` and add `library.readingHistory`:

```json
    "tabs": {
      "allBooks": "بارلىق كىتابلار",
      "reading": "ئوقۇۋاتقانلىرىم",
      "bookmarks": "خەتكۈشلەر"
    },
    "readingHistory": {
      "searchPlaceholder": "ئوقۇغان كىتابلىرىڭىزدىن ئىزدەڭ...",
      "empty": "سىز تېخى ھېچقانداق كىتابنى ئوقۇمىدىڭىز",
      "emptyHint": "كىتاب ئوقۇشقا باشلىغىنىڭىزدا، ئوقۇش تەرەققىياتىڭىز بۇ يەردە كۆرۈنىدۇ",
      "lastReadPage": "{page}-بەت",
      "browseBooks": "كىتابلارنى كۆرۈش"
    },
```

- [ ] **Step 2: Update `apps/frontend/src/locales/en.json`**

In `apps/frontend/src/locales/en.json`, update `library.tabs` and add `library.readingHistory`:

```json
    "tabs": {
      "allBooks": "All Books",
      "reading": "Reading History",
      "bookmarks": "Bookmarks"
    },
    "readingHistory": {
      "searchPlaceholder": "Search reading history...",
      "empty": "You haven't read any books yet",
      "emptyHint": "When you start reading books, your reading progress will appear here",
      "lastReadPage": "Page {page}",
      "browseBooks": "Browse Books"
    },
```

- [ ] **Step 3: Verify JSON validity**

Run: `node -e "JSON.parse(require('fs').readFileSync('apps/frontend/src/locales/ug.json')); JSON.parse(require('fs').readFileSync('apps/frontend/src/locales/en.json')); console.log('Valid JSON')"`
Expected: "Valid JSON"

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/locales/ug.json apps/frontend/src/locales/en.json
git commit -m "feat(i18n): add localization keys for reading history and bookmarks tabs"
```

---

### Task 2: Implement `ReadingHistoryTab` Component

**Files:**
- Create: `apps/frontend/src/components/library/ReadingHistoryTab.tsx`
- Create: `apps/frontend/src/tests/components/library/ReadingHistoryTab.test.tsx`

**Interfaces:**
- Consumes: `PersistenceService.listReadingProgress()`
- Produces: `ReadingHistoryTabProps { onOpenBook: (bookId: string, pageNumber?: number) => void; onCountChange?: (count: number) => void; onBrowseBooks?: () => void; }`

- [ ] **Step 1: Write test for `ReadingHistoryTab`**

Create `apps/frontend/src/tests/components/library/ReadingHistoryTab.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { ReadingHistoryTab } from '../../../components/library/ReadingHistoryTab';
import { PersistenceService } from '../../../services/persistenceService';

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../../../services/persistenceService', () => ({
  PersistenceService: {
    listReadingProgress: vi.fn(),
  },
}));

vi.mock('../../../i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, any>) => {
      if (key === 'library.readingHistory.lastReadPage') return `${params?.page}-بەت`;
      return key;
    },
    language: 'ug',
  }),
}));

describe('ReadingHistoryTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    vi.mocked(PersistenceService.listReadingProgress).mockReturnValue(new Promise(() => {}));
    render(<ReadingHistoryTab onOpenBook={vi.fn()} />);
    expect(document.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders read books and opens book on card click', async () => {
    const mockProgress = [
      {
        bookId: 'b1',
        bookTitle: 'Test Uyghur Book',
        bookCoverUrl: '/covers/b1.jpg',
        pageNumber: 42,
        updatedAt: new Date().toISOString(),
      },
    ];
    vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(mockProgress);
    const onOpenBook = vi.fn();
    const onCountChange = vi.fn();

    render(<ReadingHistoryTab onOpenBook={onOpenBook} onCountChange={onCountChange} />);

    await waitFor(() => {
      expect(screen.getByText('Test Uyghur Book')).toBeInTheDocument();
    });

    expect(screen.getByText('42-بەت')).toBeInTheDocument();
    expect(onCountChange).toHaveBeenCalledWith(1);

    // Clicking the card opens the book at page 42
    const card = screen.getByText('Test Uyghur Book').closest('div[role="button"]') || screen.getByText('Test Uyghur Book');
    fireEvent.click(card);
    expect(onOpenBook).toHaveBeenCalledWith('b1', 42);

    // Ensure there is NO "Continue Reading" button
    expect(screen.queryByText('library.readingBookmarks.continueReading')).not.toBeInTheDocument();
  });

  it('filters books by search query', async () => {
    const mockProgress = [
      { bookId: 'b1', bookTitle: 'Tarix Kitabi', bookCoverUrl: null, pageNumber: 5, updatedAt: new Date().toISOString() },
      { bookId: 'b2', bookTitle: 'Ana Tilim', bookCoverUrl: null, pageNumber: 10, updatedAt: new Date().toISOString() },
    ];
    vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(mockProgress);

    render(<ReadingHistoryTab onOpenBook={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Tarix Kitabi')).toBeInTheDocument();
      expect(screen.getByText('Ana Tilim')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('library.readingHistory.searchPlaceholder');
    fireEvent.change(searchInput, { target: { value: 'Tarix' } });

    expect(screen.getByText('Tarix Kitabi')).toBeInTheDocument();
    expect(screen.queryByText('Ana Tilim')).not.toBeInTheDocument();
  });

  it('renders empty state when no reading progress exists', async () => {
    vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue([]);
    render(<ReadingHistoryTab onOpenBook={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('library.readingHistory.empty')).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- apps/frontend/src/tests/components/library/ReadingHistoryTab.test.tsx`
Expected: FAIL (Cannot find module)

- [ ] **Step 3: Implement `ReadingHistoryTab.tsx`**

Create `apps/frontend/src/components/library/ReadingHistoryTab.tsx`:

```tsx
import React, { useState, useEffect, useMemo } from 'react';
import { Search, X, BookOpen, Clock } from 'lucide-react';
import { ReadingProgress } from '@shared/types';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { GuestAuthWall } from '../reader/GuestAuthWall';

interface ReadingHistoryTabProps {
  onOpenBook: (bookId: string, pageNumber?: number) => void;
  onCountChange?: (count: number) => void;
  onBrowseBooks?: () => void;
}

export const ReadingHistoryTab: React.FC<ReadingHistoryTabProps> = ({
  onOpenBook,
  onCountChange,
  onBrowseBooks,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();

  const [items, setItems] = useState<ReadingProgress[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [query, setQuery] = useState<string>('');

  useEffect(() => {
    if (!isAuthenticated) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    const fetchProgress = async () => {
      setIsLoading(true);
      try {
        const progressList = await PersistenceService.listReadingProgress();
        if (!isMounted) return;
        setItems(progressList);
      } catch (err) {
        console.error('Failed to load reading progress', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchProgress();
    return () => {
      isMounted = false;
    };
  }, [isAuthenticated]);

  useEffect(() => {
    onCountChange?.(items.length);
  }, [items.length, onCountChange]);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => (item.bookTitle || '').toLowerCase().includes(q));
  }, [items, query]);

  if (!isAuthenticated) {
    return <GuestAuthWall />;
  }

  const formatRelativeDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString();
    } catch {
      return '';
    }
  };

  return (
    <div className="space-y-6 sm:space-y-8 animate-fade-in" dir="rtl">
      {/* Search Header */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
            <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('library.readingHistory.searchPlaceholder')}
            className="w-full pr-12 md:pr-14 pl-10 md:pl-12 py-3 md:py-3.5 bg-white/80 dark:bg-slate-900/60 backdrop-blur-md border border-slate-200/80 dark:border-slate-800 rounded-2xl md:rounded-[22px] text-sm md:text-base text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-[#0369a1]/10 dark:focus:ring-[#38bdf8]/10 focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all duration-300 shadow-sm uyghur-text"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6">
          {Array.from({ length: 6 }).map((_, idx) => (
            <div
              key={idx}
              className="h-72 bg-white/40 dark:bg-slate-900/40 rounded-2xl animate-pulse border border-slate-200/40 dark:border-slate-800/40"
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && filteredItems.length === 0 && (
        <div className="text-center py-16 px-4 bg-white/60 dark:bg-slate-900/40 backdrop-blur-md rounded-3xl border border-slate-200/80 dark:border-slate-800 max-w-lg mx-auto shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 flex items-center justify-center mx-auto mb-4 text-[#0369a1] dark:text-[#38bdf8]">
            <BookOpen size={32} strokeWidth={1.75} />
          </div>
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 uyghur-text mb-2">
            {t('library.readingHistory.empty')}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 uyghur-text mb-6">
            {t('library.readingHistory.emptyHint')}
          </p>
          {onBrowseBooks && (
            <button
              onClick={onBrowseBooks}
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 font-semibold text-sm shadow-sm hover:opacity-95 transition-all"
            >
              <span className="uyghur-text">{t('library.readingHistory.browseBooks')}</span>
            </button>
          )}
        </div>
      )}

      {/* Books Grid */}
      {!isLoading && filteredItems.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-4 sm:gap-6">
          {filteredItems.map((item) => (
            <div
              key={item.bookId}
              role="button"
              tabIndex={0}
              onClick={() => onOpenBook(item.bookId, item.pageNumber)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenBook(item.bookId, item.pageNumber);
                }
              }}
              className="group cursor-pointer flex flex-col bg-white dark:bg-slate-900/80 rounded-2xl border border-slate-200/80 dark:border-slate-800 overflow-hidden shadow-sm hover:shadow-md hover:border-[#0369a1]/40 dark:hover:border-[#38bdf8]/40 transition-all duration-300 transform hover:-translate-y-1"
            >
              {/* Cover Container */}
              <div className="relative aspect-[3/4] w-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                {item.bookCoverUrl ? (
                  <img
                    src={item.bookCoverUrl}
                    alt={item.bookTitle}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    loading="lazy"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center p-4 text-center text-slate-400">
                    <BookOpen size={36} strokeWidth={1.5} className="mb-2 opacity-50" />
                    <span className="text-xs line-clamp-3 uyghur-text">{item.bookTitle}</span>
                  </div>
                )}

                {/* Last Page Pill Overlay */}
                {item.pageNumber && (
                  <div className="absolute top-2 right-2 bg-slate-950/80 backdrop-blur-md text-white px-2.5 py-1 rounded-lg text-xs font-semibold uyghur-text shadow-sm border border-white/10">
                    {t('library.readingHistory.lastReadPage', { page: item.pageNumber })}
                  </div>
                )}
              </div>

              {/* Title & Metadata */}
              <div className="p-3.5 flex flex-col justify-between flex-1 gap-2">
                <h4 className="text-sm font-bold text-slate-800 dark:text-slate-100 line-clamp-2 uyghur-text group-hover:text-[#0369a1] dark:group-hover:text-[#38bdf8] transition-colors leading-snug">
                  {item.bookTitle}
                </h4>
                <div className="flex items-center gap-1.5 text-[11px] text-slate-400 dark:text-slate-500">
                  <Clock size={12} />
                  <span>{formatRelativeDate(item.updatedAt)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- apps/frontend/src/tests/components/library/ReadingHistoryTab.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/library/ReadingHistoryTab.tsx apps/frontend/src/tests/components/library/ReadingHistoryTab.test.tsx
git commit -m "feat(library): add ReadingHistoryTab component with direct card click navigation"
```

---

### Task 3: Refactor / Adapt `BookmarksTab` (Only Books with Bookmarks > 0)

**Files:**
- Create: `apps/frontend/src/components/library/BookmarksTab.tsx`
- Create: `apps/frontend/src/tests/components/library/BookmarksTab.test.tsx`
- Remove / Deprecate: `apps/frontend/src/components/library/ReadingBookmarksTab.tsx`

**Interfaces:**
- Consumes: `PersistenceService.listBookmarks()`
- Produces: `BookmarksTabProps { onOpenBook: (bookId: string, pageNumber?: number) => void; onOpenBookmark: (bookId: string, pageNumber: number, quoteText?: string | null) => void; onCountChange?: (count: number) => void; }`

- [ ] **Step 1: Write test for `BookmarksTab`**

Create `apps/frontend/src/tests/components/library/BookmarksTab.test.tsx`:

```tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { BookmarksTab } from '../../../components/library/BookmarksTab';
import { PersistenceService } from '../../../services/persistenceService';

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('../../../services/persistenceService', () => ({
  PersistenceService: {
    listBookmarks: vi.fn(),
    deleteBookmark: vi.fn(),
    renameBookmark: vi.fn(),
  },
}));

vi.mock('../../../i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
    language: 'ug',
  }),
}));

describe('BookmarksTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders only books that have at least 1 bookmark', async () => {
    const mockBookmarks = [
      {
        id: 'bm-1',
        bookId: 'b1',
        bookTitle: 'Book With Bookmarks',
        pageNumber: 15,
        name: 'My Bookmark 1',
        quoteText: null,
        createdAt: new Date().toISOString(),
      },
    ];

    vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(mockBookmarks);
    const onCountChange = vi.fn();

    render(<BookmarksTab onOpenBook={vi.fn()} onOpenBookmark={vi.fn()} onCountChange={onCountChange} />);

    await waitFor(() => {
      expect(screen.getByText('Book With Bookmarks')).toBeInTheDocument();
      expect(screen.getByText('My Bookmark 1')).toBeInTheDocument();
    });

    expect(onCountChange).toHaveBeenCalledWith(1);
  });

  it('clicking a bookmark triggers onOpenBookmark', async () => {
    const mockBookmarks = [
      {
        id: 'bm-1',
        bookId: 'b1',
        bookTitle: 'Book With Bookmarks',
        pageNumber: 15,
        name: 'My Bookmark 1',
        quoteText: 'Some quote',
        createdAt: new Date().toISOString(),
      },
    ];

    vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(mockBookmarks);
    const onOpenBookmark = vi.fn();

    render(<BookmarksTab onOpenBook={vi.fn()} onOpenBookmark={onOpenBookmark} />);

    await waitFor(() => {
      expect(screen.getByText('My Bookmark 1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('My Bookmark 1'));
    expect(onOpenBookmark).toHaveBeenCalledWith('b1', 15, 'Some quote');
  });

  it('shows empty state when no bookmarks exist', async () => {
    vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
    render(<BookmarksTab onOpenBook={vi.fn()} onOpenBookmark={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('library.readingBookmarks.empty')).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Implement `BookmarksTab.tsx` preserving UX and filtering `bookmarks.length > 0`**

Create `apps/frontend/src/components/library/BookmarksTab.tsx` adapting the current UX of `ReadingBookmarksTab.tsx`, but querying `listBookmarks()` and only including books where `bookmarks.length > 0`:

```tsx
import React, { useState, useEffect, useMemo } from 'react';
import {
  Search,
  X,
  BookOpen,
  BookMarked,
  Pencil,
  Trash2,
  Check,
  Quote,
} from 'lucide-react';
import { Bookmark } from '@shared/types';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { GuestAuthWall } from '../reader/GuestAuthWall';

export interface BookWithBookmarks {
  bookId: string;
  bookTitle: string;
  bookCoverUrl: string | null;
  updatedAt: string;
  bookmarks: Bookmark[];
}

interface BookmarksTabProps {
  onOpenBook: (bookId: string, pageNumber?: number) => void;
  onOpenBookmark: (bookId: string, pageNumber: number, quoteText?: string | null) => void;
  onCountChange?: (count: number) => void;
}

export const BookmarksTab: React.FC<BookmarksTabProps> = ({
  onOpenBook,
  onOpenBookmark,
  onCountChange,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();

  const [books, setBooks] = useState<BookWithBookmarks[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [query, setQuery] = useState<string>('');

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState<string>('');

  useEffect(() => {
    if (!isAuthenticated) {
      setIsLoading(false);
      return;
    }

    let isMounted = true;
    const fetchBookmarks = async () => {
      setIsLoading(true);
      try {
        const bookmarksList = await PersistenceService.listBookmarks();

        if (!isMounted) return;

        const bookMap = new Map<string, BookWithBookmarks>();

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
              updatedAt: bm.createdAt,
              bookmarks: [bm],
            });
          }
        }

        // Only books with at least 1 bookmark, sorted by most recent
        const filtered = Array.from(bookMap.values())
          .filter((b) => b.bookmarks.length > 0)
          .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

        for (const b of filtered) {
          b.bookmarks.sort((b1, b2) => b1.pageNumber - b2.pageNumber);
        }

        setBooks(filtered);
      } catch (err) {
        console.error('Failed to load bookmarks', err);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    fetchBookmarks();
    return () => {
      isMounted = false;
    };
  }, [isAuthenticated]);

  // Total bookmarks count across all books
  const totalBookmarksCount = useMemo(
    () => books.reduce((acc, b) => acc + b.bookmarks.length, 0),
    [books]
  );

  useEffect(() => {
    onCountChange?.(totalBookmarksCount);
  }, [totalBookmarksCount, onCountChange]);

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
      .filter((b): b is BookWithBookmarks => b !== null && b.bookmarks.length > 0);
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
          .filter((b) => b.bookmarks.length > 0)
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
      {/* Search Header */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4">
        <div className="relative flex-1 lg:flex-none lg:w-[40%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
            <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('library.readingBookmarks.searchPlaceholder')}
            className="w-full pr-12 md:pr-14 pl-10 md:pl-12 py-3 md:py-3.5 bg-white/80 dark:bg-slate-900/60 backdrop-blur-md border border-slate-200/80 dark:border-slate-800 rounded-2xl md:rounded-[22px] text-sm md:text-base text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-400 focus:outline-none focus:ring-4 focus:ring-[#0369a1]/10 dark:focus:ring-[#38bdf8]/10 focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all duration-300 shadow-sm uyghur-text"
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="space-y-6">
          {Array.from({ length: 3 }).map((_, idx) => (
            <div
              key={idx}
              className="h-44 bg-white/40 dark:bg-slate-900/40 rounded-3xl animate-pulse border border-slate-200/40 dark:border-slate-800/40"
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!isLoading && filteredBooks.length === 0 && (
        <div className="text-center py-16 px-4 bg-white/60 dark:bg-slate-900/40 backdrop-blur-md rounded-3xl border border-slate-200/80 dark:border-slate-800 max-w-lg mx-auto shadow-sm">
          <div className="w-16 h-16 rounded-2xl bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 flex items-center justify-center mx-auto mb-4 text-[#0369a1] dark:text-[#38bdf8]">
            <BookMarked size={32} strokeWidth={1.75} />
          </div>
          <h3 className="text-lg font-bold text-slate-800 dark:text-slate-100 uyghur-text mb-2">
            {t('library.readingBookmarks.empty')}
          </h3>
          <p className="text-sm text-slate-500 dark:text-slate-400 uyghur-text">
            {t('library.readingBookmarks.noBookmarksHint')}
          </p>
        </div>
      )}

      {/* Book List with Bookmarks */}
      {!isLoading && filteredBooks.length > 0 && (
        <div className="space-y-6">
          {filteredBooks.map((book) => (
            <div
              key={book.bookId}
              className="bg-white/80 dark:bg-slate-900/70 backdrop-blur-md rounded-3xl border border-slate-200/80 dark:border-slate-800/80 p-5 sm:p-6 shadow-sm hover:shadow-md transition-all duration-300"
            >
              {/* Book Header */}
              <div className="flex items-center justify-between gap-4 pb-4 border-b border-slate-100 dark:border-slate-800/60 mb-5">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => onOpenBook(book.bookId)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      onOpenBook(book.bookId);
                    }
                  }}
                  className="flex items-center gap-3.5 group cursor-pointer"
                >
                  <div className="w-10 h-13 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200/60 dark:border-slate-700/60 flex items-center justify-center text-[#0369a1] dark:text-[#38bdf8] shrink-0 group-hover:scale-105 transition-transform overflow-hidden shadow-xs">
                    {book.bookCoverUrl ? (
                      <img src={book.bookCoverUrl} alt={book.bookTitle} className="w-full h-full object-cover" />
                    ) : (
                      <BookOpen size={20} strokeWidth={2} />
                    )}
                  </div>
                  <div>
                    <h3 className="text-base sm:text-lg font-bold text-slate-800 dark:text-slate-100 uyghur-text group-hover:text-[#0369a1] dark:group-hover:text-[#38bdf8] transition-colors">
                      {book.bookTitle}
                    </h3>
                  </div>
                </div>

                <div className="shrink-0 flex items-center gap-2">
                  <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] uyghur-text">
                    {book.bookmarks.length} {t('library.readingBookmarks.bookmarksCount')}
                  </span>
                </div>
              </div>

              {/* Bookmarks Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5">
                {book.bookmarks.map((bm) => {
                  const isEditing = editingId === bm.id;
                  const isQuote = !!bm.quoteText;

                  return (
                    <div
                      key={bm.id}
                      className={`group relative rounded-2xl border p-4 transition-all duration-200 flex flex-col justify-between gap-3 ${
                        isQuote
                          ? 'bg-amber-50/40 dark:bg-amber-950/10 border-amber-200/60 dark:border-amber-900/30 hover:border-amber-300 dark:hover:border-amber-800/60'
                          : 'bg-slate-50/60 dark:bg-slate-800/40 border-slate-200/60 dark:border-slate-800 hover:border-[#0369a1]/40 dark:hover:border-[#38bdf8]/40'
                      }`}
                    >
                      {/* Top Row: Icon & Page Pill */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {isQuote ? (
                            <div className="w-6 h-6 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
                              <Quote size={12} strokeWidth={2.5} />
                            </div>
                          ) : (
                            <div className="w-6 h-6 rounded-lg bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] flex items-center justify-center shrink-0">
                              <BookMarked size={12} strokeWidth={2.5} />
                            </div>
                          )}
                          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 font-mono">
                            {bm.pageNumber}-بەت
                          </span>
                        </div>

                        {/* Actions (Rename, Delete) */}
                        <div className="flex items-center gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
                          {!isEditing ? (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleStartRename(bm);
                                }}
                                className="p-1 rounded-md text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-700/50 transition-colors cursor-pointer"
                                title="تەھرىرلەش"
                              >
                                <Pencil size={13} />
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteBookmark(bm.id, book.bookId);
                                }}
                                className="p-1 rounded-md text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 transition-colors cursor-pointer"
                                title="ئۆچۈرۈش"
                              >
                                <Trash2 size={13} />
                              </button>
                            </>
                          ) : (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleSaveRename(bm.id, book.bookId);
                              }}
                              className="p-1 rounded-md text-emerald-600 dark:text-emerald-400 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors cursor-pointer"
                              title="ساقلاش"
                            >
                              <Check size={14} strokeWidth={2.5} />
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Content Row: Bookmark Name or Quote */}
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => onOpenBookmark(book.bookId, bm.pageNumber, bm.quoteText)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onOpenBookmark(book.bookId, bm.pageNumber, bm.quoteText);
                          }
                        }}
                        className="cursor-pointer space-y-1.5 flex-1"
                      >
                        {isEditing ? (
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onClick={(e) => e.stopPropagation()}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                handleSaveRename(bm.id, book.bookId);
                              } else if (e.key === 'Escape') {
                                setEditingId(null);
                              }
                            }}
                            autoFocus
                            className="w-full text-xs font-semibold px-2 py-1 bg-white dark:bg-slate-900 border border-[#0369a1] rounded-lg text-slate-800 dark:text-slate-100 uyghur-text focus:outline-none"
                          />
                        ) : (
                          <div className="text-xs sm:text-sm font-bold text-slate-800 dark:text-slate-200 line-clamp-1 uyghur-text group-hover:text-[#0369a1] dark:group-hover:text-[#38bdf8] transition-colors">
                            {bm.name}
                          </div>
                        )}

                        {isQuote && bm.quoteText && (
                          <p className="text-xs text-slate-600 dark:text-slate-400 italic line-clamp-3 uyghur-text leading-relaxed border-r-2 border-amber-400/80 pr-2">
                            "{bm.quoteText}"
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 3: Run test to verify `BookmarksTab.test.tsx` passes**

Run: `npm test -- apps/frontend/src/tests/components/library/BookmarksTab.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/components/library/BookmarksTab.tsx apps/frontend/src/tests/components/library/BookmarksTab.test.tsx
git commit -m "feat(library): add BookmarksTab filtering books with at least 1 bookmark"
```

---

### Task 4: Integrate the 3 Tabs in `LibraryView.tsx`

**Files:**
- Modify: `apps/frontend/src/components/library/LibraryView.tsx`
- Modify: `apps/frontend/src/tests/components/library/LibraryView.test.tsx`

**Interfaces:**
- Consumes: `ReadingHistoryTab`, `BookmarksTab`, `activeTab`
- Produces: Updated navigation with `all-books`, `reading`, and `bookmarks`

- [ ] **Step 1: Update `LibraryView.test.tsx`**

Modify `apps/frontend/src/tests/components/library/LibraryView.test.tsx` to test that authenticated users see 3 tabs: All Books, Reading History, and Bookmarks.

```tsx
it('renders 3 tabs when user is authenticated', () => {
  // Verify tabs 'all-books', 'reading', and 'bookmarks' appear in the document
});
```

- [ ] **Step 2: Update `LibraryView.tsx`**

In `LibraryView.tsx`:
1. Import `ReadingHistoryTab` and `BookmarksTab`.
2. Define tab states:
```tsx
const isReadingActive = isAuthenticated && activeTab === 'reading';
const isBookmarksActive = isAuthenticated && activeTab === 'bookmarks';
```
3. Update tabs list:
```tsx
  const libraryTabs = [
    { key: 'all-books' as const, label: t('library.tabs.allBooks'), icon: LibraryBig },
    ...(isAuthenticated
      ? [
          {
            key: 'reading' as const,
            label: t('library.tabs.reading'),
            icon: History,
          },
          {
            key: 'bookmarks' as const,
            label: t('library.tabs.bookmarks'),
            icon: BookMarked,
          },
        ]
      : []),
  ];
```
4. Render `ReadingHistoryTab` when `activeTab === 'reading'` and `BookmarksTab` when `activeTab === 'bookmarks'`.
5. Update count badge for each tab.

- [ ] **Step 3: Run test to verify `LibraryView.test.tsx` passes**

Run: `npm test -- apps/frontend/src/tests/components/library/LibraryView.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/components/library/LibraryView.tsx apps/frontend/src/tests/components/library/LibraryView.test.tsx
git commit -m "feat(library): wire up 3 separate tabs for All Books, Reading History, and Bookmarks"
```

---

### Task 5: Clean Up Deprecated Components & Run Full Verification

**Files:**
- Remove: `apps/frontend/src/components/library/ReadingBookmarksTab.tsx` (if no longer used)
- Remove/Update references: `apps/frontend/src/tests/components/library/ReadingBookmarksTab.test.tsx`

- [ ] **Step 1: Check for any dangling references to `ReadingBookmarksTab`**

Run: `git grep -n "ReadingBookmarksTab" apps/frontend/src`
Expected: Clean or update to `BookmarksTab` / `ReadingHistoryTab`.

- [ ] **Step 2: Run full frontend test suite**

Run: `npm test` in `apps/frontend`
Expected: All tests PASS.

- [ ] **Step 3: Run production build**

Run: `npm run build --workspace apps/frontend`
Expected: Build succeeds with 0 errors.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(library): complete separation of reading history and bookmarks tabs"
```
