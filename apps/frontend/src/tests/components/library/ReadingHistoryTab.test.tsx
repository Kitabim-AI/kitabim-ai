import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { ReadingHistoryTab } from '@/src/components/library/ReadingHistoryTab';
import { PersistenceService } from '@/src/services/persistenceService';
import { I18nContext } from '@/src/i18n/I18nContext';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: () => ({ isAuthenticated: true }),
}));

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    listReadingProgress: vi.fn(),
  },
}));

const i18nValue = {
  language: 'ug' as const,
  setLanguage: vi.fn(),
  t: (key: string, params?: Record<string, any>) => {
    if (key === 'library.readingHistory.lastReadPage') return `${params?.page}-بەت`;
    return key;
  },
};

const renderTab = (
  onOpenBook = vi.fn(),
  onCountChange = vi.fn(),
  onBrowseBooks = vi.fn()
) =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <ReadingHistoryTab
        onOpenBook={onOpenBook}
        onCountChange={onCountChange}
        onBrowseBooks={onBrowseBooks}
      />
    </I18nContext.Provider>
  );

describe('ReadingHistoryTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    vi.mocked(PersistenceService.listReadingProgress).mockReturnValue(new Promise(() => {}));
    const { container } = renderTab();
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
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

    renderTab(onOpenBook, onCountChange);

    await waitFor(() => {
      expect(screen.getByText('Test Uyghur Book')).toBeInTheDocument();
    });

    expect(screen.getByText('library.readingHistory.lastReadPage')).toBeInTheDocument();
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

    renderTab();

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
    renderTab();

    await waitFor(() => {
      expect(screen.getByText('library.readingHistory.empty')).toBeInTheDocument();
    });
  });
});
