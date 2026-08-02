import { VirtualScrollReader } from '@/src/components/reader/VirtualScrollReader';
import * as AuthModule from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: {
    getBookPages: vi.fn().mockResolvedValue([]),
  },
}));

vi.mock('@/src/components/reader/PageItem', () => ({
  PageItem: () => <div data-testid="page-item">Page Content</div>,
}));

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderReader = () =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <VirtualScrollReader bookId="book-1" totalPages={5} fontSize={16} scrollParentRef={{ current: document.createElement('div') }} />
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
});

test('disables selection and prevents copy for guest users in reader', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: false,
    user: null,
  } as any);

  renderReader();

  const readerContainer = screen.getByTestId('reader-container');
  expect(readerContainer).toHaveClass('select-none');

  const copyEvent = new Event('copy', { bubbles: true, cancelable: true });
  const preventCopySpy = vi.spyOn(copyEvent, 'preventDefault');
  fireEvent(readerContainer, copyEvent);
  expect(preventCopySpy).toHaveBeenCalled();

  const contextMenuEvent = new Event('contextmenu', { bubbles: true, cancelable: true });
  const preventContextMenuSpy = vi.spyOn(contextMenuEvent, 'preventDefault');
  fireEvent(readerContainer, contextMenuEvent);
  expect(preventContextMenuSpy).toHaveBeenCalled();
});

test('allows selection and copying for registered/authenticated users in reader', () => {
  vi.mocked(AuthModule.useAuth).mockReturnValue({
    isAuthenticated: true,
    user: { id: 'user-1', role: 'reader' },
  } as any);

  renderReader();

  const readerContainer = screen.getByTestId('reader-container');
  expect(readerContainer).not.toHaveClass('select-none');

  const copyEvent = new Event('copy', { bubbles: true, cancelable: true });
  const preventCopySpy = vi.spyOn(copyEvent, 'preventDefault');
  fireEvent(readerContainer, copyEvent);
  expect(preventCopySpy).not.toHaveBeenCalled();

  const contextMenuEvent = new Event('contextmenu', { bubbles: true, cancelable: true });
  const preventContextMenuSpy = vi.spyOn(contextMenuEvent, 'preventDefault');
  fireEvent(readerContainer, contextMenuEvent);
  expect(preventContextMenuSpy).not.toHaveBeenCalled();
});
