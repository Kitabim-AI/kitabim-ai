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


