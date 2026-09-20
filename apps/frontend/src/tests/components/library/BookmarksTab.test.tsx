import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { BookmarksTab } from '@/src/components/library/BookmarksTab';
import { I18nContext } from '@/src/i18n/I18nContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
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

const i18nValue = { language: 'en' as const, setLanguage: vi.fn(), t: (key: string) => key };

const bookmarks = [
  { id: 'bm1', bookId: 'b1', bookTitle: 'Alpha Book', pageNumber: 10, name: 'Great chapter', quoteText: null, createdAt: 'now' },
  { id: 'bm2', bookId: 'b2', bookTitle: 'Beta Story', pageNumber: 3, name: 'Nice line', quoteText: 'a quoted passage', createdAt: 'now' },
];

const renderTab = (onOpenBookmark = vi.fn()) => render(
  <I18nContext.Provider value={i18nValue}>
    <BookmarksTab onOpenBookmark={onOpenBookmark} />
  </I18nContext.Provider>
);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('groups bookmarks by book title', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
  expect(screen.getByText('Great chapter')).toBeInTheDocument();
  expect(screen.getByText('Nice line')).toBeInTheDocument();
});

test('filters by bookmark name or book title', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());

  fireEvent.change(screen.getByPlaceholderText('library.bookmarksTab.searchPlaceholder'), { target: { value: 'nice' } });

  expect(screen.queryByText('Alpha Book')).not.toBeInTheDocument();
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
});

test('clicking a bookmark calls onOpenBookmark with book, page, and quote', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  const onOpenBookmark = vi.fn();
  renderTab(onOpenBookmark);
  await waitFor(() => expect(screen.getByText('Nice line')).toBeInTheDocument());

  fireEvent.click(screen.getByText('Nice line'));
  expect(onOpenBookmark).toHaveBeenCalledWith('b2', 3, 'a quoted passage');
});

test('deleting a bookmark removes it from the list', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  vi.mocked(PersistenceService.deleteBookmark).mockResolvedValue(undefined);
  renderTab();
  await waitFor(() => expect(screen.getByText('Great chapter')).toBeInTheDocument());

  fireEvent.click(screen.getAllByTitle('bookmarks.delete')[0]);

  await waitFor(() => expect(screen.queryByText('Great chapter')).not.toBeInTheDocument());
});

test('renaming a bookmark switches it to an input and saves the new name', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(bookmarks);
  vi.mocked(PersistenceService.renameBookmark).mockResolvedValue(undefined);
  renderTab();
  await waitFor(() => expect(screen.getByText('Great chapter')).toBeInTheDocument());

  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);
  const input = screen.getByDisplayValue('Great chapter');
  fireEvent.change(input, { target: { value: 'Even better chapter' } });
  fireEvent.click(screen.getByText('bookmarks.save'));

  await waitFor(() => expect(PersistenceService.renameBookmark).toHaveBeenCalledWith('bm1', 'Even better chapter'));
});

test('shows an empty state with no bookmarks', async () => {
  vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
  renderTab();
  await waitFor(() => expect(screen.getByText('library.bookmarksTab.empty')).toBeInTheDocument());
});

test('shows the guest auth wall for signed-out users', () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);
  renderTab();
  expect(screen.getByTestId('guest-auth-wall')).toBeInTheDocument();
  expect(PersistenceService.listBookmarks).not.toHaveBeenCalled();
});
