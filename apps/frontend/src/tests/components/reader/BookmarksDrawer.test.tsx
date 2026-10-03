import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { BookmarksDrawer } from '@/src/components/reader/BookmarksDrawer';
import { I18nContext } from '@/src/i18n/I18nContext';

const i18nValue = { language: 'en' as const, setLanguage: vi.fn(), t: (key: string) => key };

const bookmarks = [
  { id: 'bm1', bookId: 'b1', bookTitle: 'B', pageNumber: 10, name: 'Chapter 2', quoteText: null, createdAt: 'now' },
  { id: 'bm2', bookId: 'b1', bookTitle: 'B', pageNumber: 3, name: 'Good line', quoteText: 'a nice passage', createdAt: 'now' },
];

const renderDrawer = (props: Partial<React.ComponentProps<typeof BookmarksDrawer>> = {}) => {
  const defaultProps: React.ComponentProps<typeof BookmarksDrawer> = {
    bookmarks,
    onJumpTo: vi.fn(),
    onRename: vi.fn().mockResolvedValue(undefined),
    onDelete: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
  };
  return render(
    <I18nContext.Provider value={i18nValue}>
      <BookmarksDrawer {...defaultProps} {...props} />
    </I18nContext.Provider>
  );
};

beforeEach(() => vi.clearAllMocks());

test('lists bookmarks sorted by page number ascending', () => {
  renderDrawer();
  const names = screen.getAllByTestId('bookmark-drawer-name').map(el => el.textContent);
  expect(names).toEqual(['Good line', 'Chapter 2']);
});

test('shows a quote snippet for passage bookmarks only', () => {
  renderDrawer();
  expect(screen.getByText('a nice passage')).toBeInTheDocument();
});

test('clicking an entry jumps to its page and quote', () => {
  const onJumpTo = vi.fn();
  renderDrawer({ onJumpTo });
  fireEvent.click(screen.getByText('Good line'));
  expect(onJumpTo).toHaveBeenCalledWith(3, 'a nice passage');
});

test('deleting an entry calls onDelete with its id', () => {
  const onDelete = vi.fn().mockResolvedValue(undefined);
  renderDrawer({ onDelete });
  fireEvent.click(screen.getAllByTitle('bookmarks.delete')[0]);
  expect(onDelete).toHaveBeenCalledWith('bm2');
});

test('renaming an entry switches it to an input and calls onRename on save', () => {
  const onRename = vi.fn().mockResolvedValue(undefined);
  renderDrawer({ onRename });

  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);
  const input = screen.getByDisplayValue('Good line');
  fireEvent.change(input, { target: { value: 'Better line' } });
  fireEvent.click(screen.getByText('bookmarks.save'));

  expect(onRename).toHaveBeenCalledWith('bm2', 'Better line');
});

test('clicking an entry while renaming does not jump to its page', () => {
  const onJumpTo = vi.fn();
  renderDrawer({ onJumpTo });

  fireEvent.click(screen.getAllByTitle('bookmarks.rename')[0]);
  fireEvent.click(screen.getByDisplayValue('Good line'));

  expect(onJumpTo).not.toHaveBeenCalled();
});

test('shows an empty state when there are no bookmarks', () => {
  renderDrawer({ bookmarks: [] });
  expect(screen.getByText('bookmarks.emptyForBook')).toBeInTheDocument();
});
