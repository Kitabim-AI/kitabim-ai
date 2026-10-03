import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { BookmarksTab } from '@/src/components/library/BookmarksTab';
import { PersistenceService } from '@/src/services/persistenceService';
import { I18nContext } from '@/src/i18n/I18nContext';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    listReadingProgress: vi.fn(),
    listBookmarks: vi.fn(),
    deleteBookmark: vi.fn(),
    renameBookmark: vi.fn(),
  },
}));

const i18nValue = {
  language: 'ug' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderTab = (
  onOpenBook = vi.fn(),
  onOpenBookmark = vi.fn(),
  onCountChange = vi.fn()
) =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <BookmarksTab
        onOpenBook={onOpenBook}
        onOpenBookmark={onOpenBookmark}
        onCountChange={onCountChange}
      />
    </I18nContext.Provider>
  );

describe('BookmarksTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue([]);
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

    renderTab(vi.fn(), vi.fn(), onCountChange);

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

    renderTab(vi.fn(), onOpenBookmark);

    await waitFor(() => {
      expect(screen.getByText('My Bookmark 1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('My Bookmark 1'));
    expect(onOpenBookmark).toHaveBeenCalledWith('b1', 15, 'Some quote');
  });

  it('shows empty state when no bookmarks exist', async () => {
    vi.mocked(PersistenceService.listBookmarks).mockResolvedValue([]);
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('library.readingBookmarks.empty')).toBeInTheDocument();
    });
  });

  it('allows renaming a bookmark', async () => {
    const mockBookmarks = [
      {
        id: 'bm-1',
        bookId: 'b1',
        bookTitle: 'Book With Bookmarks',
        pageNumber: 15,
        name: 'Original Name',
        quoteText: null,
        createdAt: new Date().toISOString(),
      },
    ];

    vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(mockBookmarks);
    vi.mocked(PersistenceService.renameBookmark).mockResolvedValue(undefined as any);

    renderTab();

    await waitFor(() => {
      expect(screen.getByText('Original Name')).toBeInTheDocument();
    });

    // Click edit button
    const editBtn = screen.getByTitle('bookmarks.rename');
    fireEvent.click(editBtn);

    const input = screen.getByDisplayValue('Original Name');
    fireEvent.change(input, { target: { value: 'Updated Name' } });

    // Click save button
    const saveBtn = screen.getByTitle('common.save');
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(PersistenceService.renameBookmark).toHaveBeenCalledWith('bm-1', 'Updated Name');
      expect(screen.getByText('Updated Name')).toBeInTheDocument();
    });
  });

  it('allows deleting a bookmark and removes book card if no bookmarks remain', async () => {
    const mockBookmarks = [
      {
        id: 'bm-1',
        bookId: 'b1',
        bookTitle: 'Book With Bookmarks',
        pageNumber: 15,
        name: 'To Delete',
        quoteText: null,
        createdAt: new Date().toISOString(),
      },
    ];

    vi.mocked(PersistenceService.listBookmarks).mockResolvedValue(mockBookmarks);
    vi.mocked(PersistenceService.deleteBookmark).mockResolvedValue(undefined as any);

    renderTab();

    await waitFor(() => {
      expect(screen.getByText('To Delete')).toBeInTheDocument();
    });

    const deleteBtn = screen.getByTitle('bookmarks.delete');
    fireEvent.click(deleteBtn);

    await waitFor(() => {
      expect(PersistenceService.deleteBookmark).toHaveBeenCalledWith('bm-1');
      expect(screen.queryByText('Book With Bookmarks')).not.toBeInTheDocument();
    });
  });
});
