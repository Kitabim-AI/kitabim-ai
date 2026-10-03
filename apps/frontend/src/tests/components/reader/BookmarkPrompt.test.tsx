import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { BookmarkPrompt } from '@/src/components/reader/BookmarkPrompt';
import { I18nContext } from '@/src/i18n/I18nContext';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ loginWithGoogle: vi.fn(), loginWithFacebook: vi.fn(), isLoading: false })),
}));

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderPrompt = (props: Partial<React.ComponentProps<typeof BookmarkPrompt>> = {}) => {
  const defaultProps: React.ComponentProps<typeof BookmarkPrompt> = {
    top: 0,
    left: 0,
    mode: 'create',
    defaultName: 'Page 1',
    isAuthenticated: true,
    onSave: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
  };
  return render(
    <I18nContext.Provider value={i18nValue}>
      <BookmarkPrompt {...defaultProps} {...props} />
    </I18nContext.Provider>
  );
};

beforeEach(() => vi.clearAllMocks());

test('create mode pre-fills the default name and saves on confirm', async () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  renderPrompt({ mode: 'create', defaultName: 'Page 42', onSave });

  const input = screen.getByRole('textbox') as HTMLInputElement;
  expect(input.value).toBe('Page 42');
  expect(screen.getByText('bookmarks.bookmarkName')).toBeInTheDocument();
  expect(input.placeholder).toBe('bookmarks.namePlaceholder');

  fireEvent.click(screen.getByText('bookmarks.save'));
  expect(onSave).toHaveBeenCalledWith('Page 42');
});

test('create mode blocks save when the name is emptied', () => {
  const onSave = vi.fn();
  renderPrompt({ mode: 'create', defaultName: 'Page 42', onSave });

  const input = screen.getByRole('textbox');
  fireEvent.change(input, { target: { value: '   ' } });
  fireEvent.click(screen.getByText('bookmarks.save'));

  expect(onSave).not.toHaveBeenCalled();
});

test('edit mode shows rename and delete actions', () => {
  const onSave = vi.fn().mockResolvedValue(undefined);
  const onDelete = vi.fn().mockResolvedValue(undefined);
  renderPrompt({ mode: 'edit', defaultName: 'Existing name', onSave, onDelete });

  fireEvent.click(screen.getByText('bookmarks.delete'));
  expect(onDelete).toHaveBeenCalled();
});

test('guests see a sign-in prompt instead of the name form', () => {
  renderPrompt({ isAuthenticated: false });

  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(screen.getByText('bookmarks.signInToSave')).toBeInTheDocument();
});
