import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { PageItem } from '@/src/components/reader/PageItem';
import { I18nContext } from '@/src/i18n/I18nContext';
import * as AuthModule from '@/src/hooks/useAuth';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
  useIsEditor: vi.fn(),
}));

const mockPage = {
  pageNumber: 1,
  text: 'Sample page content for test',
  status: 'ocr_done',
};

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string, _params?: Record<string, string | number>) => key,
};

const renderPageItem = (props: Partial<React.ComponentProps<typeof PageItem>> = {}) => {
  const defaultProps = {
    page: mockPage,
    isActive: true,
    isEditing: false,
    fontSize: 18,
    onSetActive: vi.fn(),
    onEdit: vi.fn(),
    onReprocess: vi.fn(),
    tempText: 'Sample page content for test',
    onTempTextChange: vi.fn(),
    onSave: vi.fn(),
    onCancel: vi.fn(),
    isLoading: false,
    isSaving: false,
  };

  return render(
    <I18nContext.Provider value={i18nValue}>
      <PageItem {...defaultProps} {...props} />
    </I18nContext.Provider>
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
  HTMLElement.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal('open', vi.fn());
  Object.assign(navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
  // jsdom doesn't implement Range.prototype.getBoundingClientRect (unlike
  // Element.prototype.getBoundingClientRect, which is stubbed to an all-zero rect).
  Range.prototype.getBoundingClientRect = function (this: Range) {
    return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON() {} } as DOMRect;
  };
});

test('PageItem renders page content when not editing', () => {
  renderPageItem({ isEditing: false });
  expect(screen.getByText('Sample page content for test')).toBeInTheDocument();
  expect(screen.getByText('reader.editPage')).toBeInTheDocument();
});

test('PageItem renders full-height textarea filling container when editing', () => {
  renderPageItem({ isEditing: true, tempText: 'Editing text' });
  const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
  expect(textarea).toBeInTheDocument();
  expect(textarea.value).toBe('Editing text');
  expect(textarea.className).toContain('h-full');
  expect(textarea.className).toContain('flex-1');
});

test('PageItem calls onSave and onCancel when buttons are clicked', () => {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  renderPageItem({ isEditing: true, onSave, onCancel });

  fireEvent.click(screen.getByText('common.save'));
  expect(onSave).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByText('common.cancel'));
  expect(onCancel).toHaveBeenCalledTimes(1);
});

test('PageItem renders display page number and PDF page number with spacing when displayPageNumber differs', () => {
  renderPageItem({
    page: {
      pageNumber: 204,
      displayPageNumber: '196',
      text: 'Content with offset',
      status: 'ocr_done',
    },
  });
  expect(screen.getByText('chat.pageNumber')).toBeInTheDocument();
  expect(screen.getByText('(PDF 204)')).toBeInTheDocument();
});

test('PageItem shows Mark as Page 1 and Mark as ToC buttons for editor/admin users', () => {
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
  const onSetStartPage = vi.fn();
  const onToggleToc = vi.fn();
  renderPageItem({ page: { ...mockPage, isToc: false }, onSetStartPage, onToggleToc });

  expect(screen.getByText('reader.setPageOne')).toBeInTheDocument();
  expect(screen.getByText('reader.markAsToc')).toBeInTheDocument();

  fireEvent.click(screen.getByText('reader.setPageOne'));
  expect(onSetStartPage).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByText('reader.markAsToc'));
  expect(onToggleToc).toHaveBeenCalledWith(true);
});

test('PageItem shows Unmark as ToC button when page is already marked as ToC', () => {
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
  const onToggleToc = vi.fn();
  renderPageItem({ page: { ...mockPage, isToc: true }, onToggleToc });

  const button = screen.getByText('reader.unmarkAsToc');
  fireEvent.click(button);
  expect(onToggleToc).toHaveBeenCalledWith(false);
});

test('PageItem hides both Mark as Page 1 and ToC toggle buttons for non-editors (readers/guests)', () => {
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(false);
  renderPageItem({ page: { ...mockPage, isToc: false }, onSetStartPage: vi.fn(), onToggleToc: vi.fn() });

  expect(screen.queryByText('reader.setPageOne')).not.toBeInTheDocument();
  expect(screen.queryByText('reader.markAsToc')).not.toBeInTheDocument();
  expect(screen.queryByText('reader.unmarkAsToc')).not.toBeInTheDocument();
});

test('PageItem renders a page-share button that opens the share modal with cleaned page text', () => {
  renderPageItem({
    page: { ...mockPage, text: 'Answer text [link](ref:427a5621d325:summary) (BookID: abc-123)' },
    bookId: 'book-1',
    bookTitle: 'My Book',
    bookAuthor: 'An Author',
  });

  fireEvent.click(screen.getByTitle('share.sharePage'));

  expect(screen.getByText('share.sharePage')).toBeInTheDocument();
  expect(screen.getByText(/Answer text link/)).toBeInTheDocument();
});

test('PageItem shows a floating share button near a text selection and opens the quote modal', () => {
  renderPageItem({
    page: { ...mockPage, text: 'Hello world example text' },
    bookId: 'book-1',
    bookTitle: 'My Book',
  });

  const contentParagraph = screen.getByText(/Hello world example text/);
  const textNode = contentParagraph.firstChild!;
  const range = document.createRange();
  range.setStart(textNode, 6);
  range.setEnd(textNode, 11); // "world"
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
  fireEvent(document, new Event('selectionchange'));

  fireEvent.click(screen.getByTitle('share.shareQuote'));

  expect(screen.getByText('share.shareQuote')).toBeInTheDocument();
});

test('PageItem calls onHighlightApplied once a highlightQuote match is applied', () => {
  const onHighlightApplied = vi.fn();
  renderPageItem({
    page: { ...mockPage, text: 'Hello highlighted world' },
    highlightQuote: 'highlighted',
    onHighlightApplied,
  });

  expect(onHighlightApplied).toHaveBeenCalledTimes(1);
  expect(document.querySelector('mark')).not.toBeNull();
});

