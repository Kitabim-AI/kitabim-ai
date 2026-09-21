import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { ReadingBookmarksTab } from '@/src/components/library/ReadingBookmarksTab';
import { I18nContext } from '@/src/i18n/I18nContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    listReadingProgress: vi.fn(),
    listBookmarks: vi.fn(),
    createBookmark: vi.fn(),
    renameBookmark: vi.fn(),
    deleteBookmark: vi.fn(),
  },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ isAuthenticated: true })),
}));

import { useAuth } from '@/src/hooks/useAuth';

const i18nValue = { language: 'ug' as const, setLanguage: vi.fn(), t: (key: string) => key };

const progressItems = [
  { bookId: 'b1', bookTitle: 'Book One', bookCoverUrl: null, pageNumber: 15, updatedAt: '2026-09-10T10:00:00Z' },
  { bookId: 'b2', bookTitle: 'Book Two', bookCoverUrl: null, pageNumber: 42, updatedAt: '2026-09-08T10:00:00Z' },
];

const bookmarksList = [
  { id: 'bm1', bookId: 'b1', bookTitle: 'Book One', pageNumber: 10, name: 'Important note', quoteText: null, createdAt: '2026-09-11T12:00:00Z' },
  { id: 'bm2', bookId: 'b1', bookTitle: 'Book One', pageNumber: 15, name: 'Favorite quote', quoteText: 'A wise sentence', createdAt: '2026-09-11T12:05:00Z' },
  { id: 'bm3', bookId: 'b3', bookTitle: 'Book Three Only Bookmarks', pageNumber: 5, name: 'Bookmark only book', quoteText: null, createdAt: '2026-09-05T12:00:00Z' },
];

const renderTab = (
  onOpenBook = vi.fn(),
  onOpenBookmark = vi.fn(),
  onCountChange = vi.fn()
) =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <ReadingBookmarksTab
        onOpenBook={onOpenBook}
        onOpenBookmark={onOpenBookmark}
        onCountChange={onCountChange}
      />
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('renders reading books and their bookmarks side-by-side', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(progressItems);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarksList);

  renderTab();

  await waitFor(() => expect(screen.getByText('Book One')).toBeInTheDocument());
  expect(screen.getByText('Book Two')).toBeInTheDocument();
  expect(screen.getByText('Book Three Only Bookmarks')).toBeInTheDocument();

  // Bookmarks for Book One
  expect(screen.getByText('Important note')).toBeInTheDocument();
  expect(screen.getByText('Favorite quote')).toBeInTheDocument();
  expect(screen.getByText('"A wise sentence"')).toBeInTheDocument();

  // Book Two has no bookmarks -> empty hint
  expect(screen.getByText('library.readingBookmarks.noBookmarks')).toBeInTheDocument();
});

test('clicking book cover or continue reading button calls onOpenBook', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(progressItems);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
  const onOpenBook = vi.fn();

  renderTab(onOpenBook);

  await waitFor(() => expect(screen.getByText('Book One')).toBeInTheDocument());
  fireEvent.click(screen.getByText('Book One'));

  expect(onOpenBook).toHaveBeenCalledWith('b1', 15);
});

test('clicking a bookmark calls onOpenBookmark with bookId, page, and quote', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(progressItems);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarksList);
  const onOpenBookmark = vi.fn();

  renderTab(undefined, onOpenBookmark);

  await waitFor(() => expect(screen.getByText('Favorite quote')).toBeInTheDocument());
  fireEvent.click(screen.getByText('Favorite quote'));

  expect(onOpenBookmark).toHaveBeenCalledWith('b1', 15, 'A wise sentence');
});

test('renaming a bookmark switches to input and saves new name', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(progressItems);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarksList);
  vi.mocked(PersistenceService.renameBookmark).mockResolvedValue(undefined);

  renderTab();

  await waitFor(() => expect(screen.getByText('Important note')).toBeInTheDocument());
  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);

  const input = screen.getByDisplayValue('Important note');
  fireEvent.change(input, { target: { value: 'Updated note' } });
  fireEvent.click(screen.getByTitle('common.save'));

  await waitFor(() =>
    expect(PersistenceService.renameBookmark).toHaveBeenCalledWith('bm1', 'Updated note')
  );
  expect(screen.getByText('Updated note')).toBeInTheDocument();
});

test('deleting a bookmark calls PersistenceService.deleteBookmark and removes it from UI', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(progressItems);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarksList);
  vi.mocked(PersistenceService.deleteBookmark).mockResolvedValue(undefined);

  renderTab();

  await waitFor(() => expect(screen.getByText('Important note')).toBeInTheDocument());
  fireEvent.click(screen.getAllByTitle('bookmarks.delete')[0]);

  await waitFor(() =>
    expect(PersistenceService.deleteBookmark).toHaveBeenCalledWith('bm1')
  );
  expect(screen.queryByText('Important note')).not.toBeInTheDocument();
});

test('search query filters books by title and by bookmark quote/name', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(progressItems);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarksList);

  renderTab();

  await waitFor(() => expect(screen.getByText('Book One')).toBeInTheDocument());

  // Filter by bookmark name
  const searchInput = screen.getByPlaceholderText('library.readingBookmarks.searchPlaceholder');
  fireEvent.change(searchInput, { target: { value: 'wise sentence' } });

  expect(screen.getByText('Book One')).toBeInTheDocument();
  expect(screen.queryByText('Book Two')).not.toBeInTheDocument();
  expect(screen.queryByText('Book Three Only Bookmarks')).not.toBeInTheDocument();
});

test('shows empty state when user has no reading books and no bookmarks', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue([]);
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);

  renderTab();

  await waitFor(() =>
    expect(screen.getByText('library.readingBookmarks.empty')).toBeInTheDocument()
  );
});

test('shows guest auth wall when unauthenticated', () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);

  renderTab();

  expect(screen.getByTestId('guest-auth-wall')).toBeInTheDocument();
  expect(PersistenceService.listReadingProgress).not.toHaveBeenCalled();
});
