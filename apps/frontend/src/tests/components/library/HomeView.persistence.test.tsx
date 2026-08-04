import React from 'react';
import { HomeView } from '@/src/components/library/HomeView';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import * as searchTabsService from '@/src/services/searchTabsService';
import { PersistenceService } from '@/src/services/persistenceService';
import { fireEvent, screen, act } from '@testing-library/react';
import { expect, test, vi, beforeEach } from 'vitest';

vi.mock('@/src/components/common/ProverbDisplay', () => ({ ProverbDisplay: () => <div>proverb</div> }));
vi.mock('@/src/components/common/QuestionRotator', () => ({ QuestionRotator: () => <div>question-rotator</div> }));
vi.mock('@/src/components/library/BookCard', () => ({ BookCard: () => <div>book-card</div> }));

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(searchTabsService.SearchTabsService, 'searchBookContent').mockResolvedValue({
    hits: [{ id: 'h1', bookId: 'b1', pageNumber: 3, snippet: 'kitab snippet' } as any],
    total: 1,
  } as any);
  vi.spyOn(PersistenceService, 'getGlobalLibrary').mockResolvedValue({
    books: [],
    total: 0,
    page: 1,
    pageSize: 10,
    totalReady: 0,
  } as any);
});

// AppProvider stays mounted for the whole SPA session — only HomeView unmounts when the
// reader opens and remounts when it closes. This wrapper simulates exactly that: HomeView
// unmounts/remounts under a single, persistent AppProvider (via `renderWithProviders`).
const HomeOrReaderStandIn: React.FC<{ showHome: boolean }> = ({ showHome }) =>
  showHome ? <HomeView /> : <div>reader-stand-in</div>;

test('content-tab query and results survive closing the reader', async () => {
  const { rerender } = render(<HomeOrReaderStandIn showHome={true} />);

  fireEvent.click(screen.getByText('home.tabs.content'));
  const input = screen.getByPlaceholderText('home.placeholders.content') as HTMLInputElement;
  fireEvent.change(input, { target: { value: 'kitab' } });

  // Let both the context-persist debounce and useContentSearch's own debounce fire
  // (advancing in two steps flushes the resolved-promise microtask in between).
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  expect(screen.getByText('snippet', { exact: false })).toBeInTheDocument();

  // Simulate opening the reader (HomeView unmounts) and closing it (HomeView remounts).
  rerender(<HomeOrReaderStandIn showHome={false} />);
  rerender(<HomeOrReaderStandIn showHome={true} />);

  const restoredInput = screen.getByPlaceholderText('home.placeholders.content') as HTMLInputElement;
  expect(restoredInput.value).toBe('kitab');

  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  expect(screen.getByText('snippet', { exact: false })).toBeInTheDocument();
});

test('keyword typed on a non-book tab is kept when switching to the Books tab', async () => {
  render(<HomeView />);

  fireEvent.click(screen.getByText('home.tabs.content'));
  const contentInput = screen.getByPlaceholderText('home.placeholders.content') as HTMLInputElement;
  fireEvent.change(contentInput, { target: { value: 'kitab' } });

  await act(async () => {
    vi.advanceTimersByTime(300);
  });

  fireEvent.click(screen.getByText('home.tabs.books'));
  const booksInput = screen.getByPlaceholderText('home.placeholders.books') as HTMLInputElement;
  expect(booksInput.value).toBe('kitab');

  // Switching in also has to commit the query so the book search actually runs.
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  expect(PersistenceService.getGlobalLibrary).toHaveBeenCalledWith(
    expect.anything(),
    expect.anything(),
    'kitab',
    expect.anything(),
    expect.anything(),
    expect.anything(),
    expect.anything(),
    expect.anything(),
  );
});

test('keyword typed on the Books tab is kept when switching to a non-book tab', async () => {
  render(<HomeView />);

  fireEvent.click(screen.getByText('home.tabs.books'));
  const booksInput = screen.getByPlaceholderText('home.placeholders.books') as HTMLInputElement;
  fireEvent.change(booksInput, { target: { value: 'kitab' } });

  await act(async () => {
    vi.advanceTimersByTime(300);
  });

  fireEvent.click(screen.getByText('home.tabs.content'));
  const contentInput = screen.getByPlaceholderText('home.placeholders.content') as HTMLInputElement;
  expect(contentInput.value).toBe('kitab');
});
