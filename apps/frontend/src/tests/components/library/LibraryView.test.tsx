import { LibraryView } from '@/src/components/library/LibraryView';
import * as AppContextModule from '@/src/context/AppContext';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { Book } from '@shared/types';
import { fireEvent, screen } from '@testing-library/react';
import { useAuth } from '@/src/hooks/useAuth';
import { expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/src/hooks/useAuth')>();
  return {
    ...actual,
    useAuth: vi.fn(() => ({ isAuthenticated: true })),
    useIsEditor: vi.fn(() => true),
    useIsAdmin: vi.fn(() => false),
  };
});

vi.mock('@/src/components/common/ProverbDisplay', () => ({
  ProverbDisplay: () => <div>proverb</div>,
}));

const mockBooks: Book[] = [
  { id: '1', title: 'Book 1', author: 'Author 1', totalPages: 10, pages: [], status: 'ready', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h1', readCount: 0, hasSummary: false, hasGraph: false, hasHistory: false } as Book,
  { id: '2', title: 'Book 2', author: 'Author 2', totalPages: 20, pages: [], status: 'ocr_processing', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h2', readCount: 0, hasSummary: false, hasGraph: false, hasHistory: false } as Book
];

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return {
    ...actual as any,
    useAppContext: vi.fn(),
  };
});

test('LibraryView renders books and header', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab: vi.fn(),
  } as any);

  render(<LibraryView />);

  expect(screen.getByText(/home\.totalBooks/i)).toBeInTheDocument();
  expect(screen.getAllByText('Book 1').length).toBeGreaterThan(0);
});

test('LibraryView shows empty state', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: [],
    totalReady: 0,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab: vi.fn(),
  } as any);

  render(<LibraryView />);

  expect(screen.getByText('library.empty.title')).toBeInTheDocument();
});

test('renders the 3 library tabs and defaults to All Books', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab: vi.fn(),
  } as any);

  render(<LibraryView />);

  const allBooksSpan = screen.getByText('library.tabs.allBooks');
  const readingSpan = screen.getByText('library.tabs.reading');
  const bookmarksSpan = screen.getByText('library.tabs.bookmarks');

  expect(allBooksSpan).toBeInTheDocument();
  expect(allBooksSpan).toHaveClass('inline');
  expect(readingSpan).toBeInTheDocument();
  expect(readingSpan).toHaveClass('hidden');
  expect(readingSpan).toHaveClass('sm:inline');
  expect(bookmarksSpan).toBeInTheDocument();
  expect(bookmarksSpan).toHaveClass('hidden');
  expect(bookmarksSpan).toHaveClass('sm:inline');
});

test('clicking the Reading History tab calls setActiveTab', () => {
  const setActiveTab = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab,
  } as any);

  render(<LibraryView />);
  fireEvent.click(screen.getByText('library.tabs.reading'));

  expect(setActiveTab).toHaveBeenCalledWith('reading');
});

test('clicking the Bookmarks tab calls setActiveTab', () => {
  const setActiveTab = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab,
  } as any);

  render(<LibraryView />);
  fireEvent.click(screen.getByText('library.tabs.bookmarks'));

  expect(setActiveTab).toHaveBeenCalledWith('bookmarks');
});

test('renders bookmarks tab when on bookmarks tab', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    totalBooks: 633,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'bookmarks',
    setActiveTab: vi.fn(),
  } as any);

  render(<LibraryView />);
  expect(screen.getByText('library.tabs.bookmarks')).toBeInTheDocument();
});

test('hides reading and bookmarks tabs for guest users and only renders all books', () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    sortedBooks: mockBooks,
    totalReady: 2,
    isLoading: false,
    isLoadingMoreShelf: false,
    hasMoreShelf: false,
    loaderRef: { current: null },
    bookActions: {},
    activeTab: 'all-books',
    setActiveTab: vi.fn(),
  } as any);

  render(<LibraryView />);

  expect(screen.getByText('library.tabs.allBooks')).toBeInTheDocument();
  expect(screen.queryByText('library.tabs.reading')).not.toBeInTheDocument();
  expect(screen.queryByText('library.tabs.bookmarks')).not.toBeInTheDocument();
});


