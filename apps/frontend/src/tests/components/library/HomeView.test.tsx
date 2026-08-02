import React, { useState } from 'react';
import { HomeView } from '@/src/components/library/HomeView';
import * as AppContextModule from '@/src/context/AppContext';
import { SearchTabKey } from '@/src/components/library/searchTabsConfig';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { fireEvent, screen } from '@testing-library/react';
import { expect, test, vi, beforeEach } from 'vitest';

vi.mock('@/src/components/common/ProverbDisplay', () => ({
  ProverbDisplay: () => <div>proverb</div>,
}));

vi.mock('@/src/components/common/QuestionRotator', () => ({
  QuestionRotator: () => <div>question-rotator</div>,
}));

vi.mock('@/src/components/library/BookCard', () => ({
  BookCard: () => <div>book-card</div>,
}));

const baseContext = {
  sortedBooks: [],
  totalBooks: 0,
  isLoading: false,
  isLoadingMoreShelf: false,
  hasMoreShelf: false,
  homeSearchQuery: '',
  setHomeSearchQuery: vi.fn(),
  homeActiveTab: 'ask' as SearchTabKey,
  setHomeActiveTab: vi.fn(),
  homeSearchText: '',
  setHomeSearchText: vi.fn(),
  selectedCategory: '',
  setSelectedCategory: vi.fn(),
  bookActions: {
    openReader: vi.fn(),
  },
  loaderRef: { current: null },
  setView: vi.fn(),
  chat: {
    setChatInput: vi.fn(),
    chatMessages: [],
    chatInput: '',
    handleSendMessage: vi.fn(),
    isChatting: false,
    streamingMessage: '',
    usageStatus: null,
    chatContainerRef: { current: null },
  },
  loadMoreShelf: vi.fn(),
  fontSize: 16,
};

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return {
    ...actual as any,
    useAppContext: vi.fn(),
  };
});

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

// `homeActiveTab` is real state owned by AppContext (so it survives HomeView remounts).
// Tests that click between tabs need that state to actually update across renders, so this
// mock implementation calls useState itself — it runs during HomeView's render (since HomeView
// calls useAppContext() directly), so React tracks it like any other hook in that component.
const mockAppContextWithTabState = (initialTab: SearchTabKey = 'ask') => {
  vi.mocked(AppContextModule.useAppContext).mockImplementation(() => {
    const [homeActiveTab, setHomeActiveTab] = useState<SearchTabKey>(initialTab);
    return { ...baseContext, homeActiveTab, setHomeActiveTab } as any;
  });
};

test('HomeView renders search input and default elements', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  render(<HomeView />);
  
  expect(screen.getByPlaceholderText('home.placeholders.ask')).toBeInTheDocument();
  expect(screen.getByTitle('home.keyboardMapTooltip')).toBeInTheDocument();
});

test('HomeView updates placeholder text and focuses search input when switching search tabs', () => {
  mockAppContextWithTabState();
  render(<HomeView />);

  // Default 'ask' tab
  const askInput = screen.getByPlaceholderText('home.placeholders.ask');
  expect(askInput).toBeInTheDocument();
  expect(askInput).toHaveFocus();

  // Switch to 'books' tab
  fireEvent.click(screen.getByText('home.tabs.books'));
  const booksInput = screen.getByPlaceholderText('home.placeholders.books');
  expect(booksInput).toBeInTheDocument();
  expect(booksInput).toHaveFocus();

  // Switch to 'dictionary' tab
  fireEvent.click(screen.getByText('home.tabs.dictionary'));
  const dictInput = screen.getByPlaceholderText('home.placeholders.dictionary');
  expect(dictInput).toBeInTheDocument();
  expect(dictInput).toHaveFocus();
});

test('HomeView sets LTR direction and data-latin mode for search input on en-ug tab', () => {
  mockAppContextWithTabState();
  render(<HomeView />);

  // Default tab ('ask') has dir="rtl" and lang="ug"
  const askInput = screen.getByPlaceholderText('home.placeholders.ask');
  expect(askInput).toHaveAttribute('dir', 'rtl');
  expect(askInput).toHaveAttribute('lang', 'ug');
  expect(askInput).not.toHaveAttribute('data-latin');

  // Switch to 'en-ug' tab directly (all tabs are on page 1)
  fireEvent.click(screen.getByText('home.tabs.enUg'));
  const enUgInput = screen.getByPlaceholderText('home.placeholders.enUg');
  expect(enUgInput).toHaveAttribute('dir', 'ltr');
  expect(enUgInput).toHaveAttribute('lang', 'en');
  expect(enUgInput).toHaveAttribute('data-latin', 'true');
  expect(enUgInput).toHaveFocus();

  // Software keyboard button should not be displayed on en-ug tab
  expect(screen.queryByTitle('home.keyboardMapTooltip')).not.toBeInTheDocument();
});

test('HomeView toggles keyboard map when clicking the toggle button', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  render(<HomeView />);
  
  // Initially, keyboard map is not shown
  expect(screen.queryByText('home.keyboardMapTitle')).not.toBeInTheDocument();
  
  // Click toggle button
  const toggleBtn = screen.getByTitle('home.keyboardMapTooltip');
  fireEvent.click(toggleBtn);
  
  // Keyboard map should be visible
  expect(screen.getByText('home.keyboardMapTitle')).toBeInTheDocument();
  
  // Click toggle button again
  fireEvent.click(toggleBtn);
  expect(screen.queryByText('home.keyboardMapTitle')).not.toBeInTheDocument();
});

test('HomeView types characters when visual keyboard keys are clicked', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  render(<HomeView />);
  
  // Open keyboard
  fireEvent.click(screen.getByTitle('home.keyboardMapTooltip'));
  
  // Get input
  const input = screen.getByPlaceholderText('home.placeholders.ask') as HTMLInputElement;
  expect(input.value).toBe('');
  
  // Click virtual 'q' key which maps to 'چ'
  const qKey = screen.getByText('چ');
  fireEvent.click(qKey);
  
  expect(input.value).toBe('چ');
  
  // Click virtual 'w' key which maps to 'ۋ'
  const wKey = screen.getByText('ۋ');
  fireEvent.click(wKey);
  
  expect(input.value).toBe('چۋ');
});

test('HomeView inputs space when Space key is clicked', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  render(<HomeView />);
  
  // Open keyboard
  fireEvent.click(screen.getByTitle('home.keyboardMapTooltip'));
  
  const input = screen.getByPlaceholderText('home.placeholders.ask') as HTMLInputElement;
  
  // Click virtual 'q' (چ)
  fireEvent.click(screen.getByText('چ'));
  
  // Click Space
  const spaceKey = screen.getByText('home.spaceKey');
  fireEvent.click(spaceKey);
  
  // Click virtual 'w' (ۋ)
  fireEvent.click(screen.getByText('ۋ'));
  
  expect(input.value).toBe('چ ۋ');
});

test('HomeView backspaces characters when Backspace key is clicked', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  render(<HomeView />);
  
  // Open keyboard
  fireEvent.click(screen.getByTitle('home.keyboardMapTooltip'));
  
  const input = screen.getByPlaceholderText('home.placeholders.ask') as HTMLInputElement;
  
  // Type 'چۋ'
  fireEvent.click(screen.getByText('چ'));
  fireEvent.click(screen.getByText('ۋ'));
  expect(input.value).toBe('چۋ');
  
  // Backspace once
  const backspaceBtn = screen.getByTitle('Backspace');
  fireEvent.click(backspaceBtn);
  expect(input.value).toBe('چ');
  
  // Backspace twice
  fireEvent.click(backspaceBtn);
  expect(input.value).toBe('');
});

test('HomeView closes keyboard map on Escape key press', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(baseContext as any);
  render(<HomeView />);
  
  // Open keyboard
  fireEvent.click(screen.getByTitle('home.keyboardMapTooltip'));
  expect(screen.getByText('home.keyboardMapTitle')).toBeInTheDocument();
  
  // Press Escape
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByText('home.keyboardMapTitle')).not.toBeInTheDocument();
});
