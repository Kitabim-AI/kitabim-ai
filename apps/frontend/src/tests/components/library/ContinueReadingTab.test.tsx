import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import { ContinueReadingTab } from '@/src/components/library/ContinueReadingTab';
import { I18nContext } from '@/src/i18n/I18nContext';
import { PersistenceService } from '@/src/services/persistenceService';

vi.mock('@/src/services/persistenceService', () => ({
  PersistenceService: { listReadingProgress: vi.fn() },
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({ isAuthenticated: true })),
}));

import { useAuth } from '@/src/hooks/useAuth';

const i18nValue = { language: 'en' as const, setLanguage: vi.fn(), t: (key: string) => key };

const items = [
  { bookId: 'b1', bookTitle: 'Alpha Book', bookCoverUrl: null, pageNumber: 10, updatedAt: '2026-09-01' },
  { bookId: 'b2', bookTitle: 'Beta Story', bookCoverUrl: null, pageNumber: 3, updatedAt: '2026-09-05' },
];

const renderTab = (onOpenBook = vi.fn()) => render(
  <I18nContext.Provider value={i18nValue}>
    <ContinueReadingTab onOpenBook={onOpenBook} />
  </I18nContext.Provider>
);

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: true } as any);
});

test('renders each book with progress', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(items);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
});

test('filters the list by title as the user types', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(items);
  renderTab();
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());

  fireEvent.change(screen.getByPlaceholderText('library.continueReading.searchPlaceholder'), { target: { value: 'beta' } });

  expect(screen.queryByText('Alpha Book')).not.toBeInTheDocument();
  expect(screen.getByText('Beta Story')).toBeInTheDocument();
});

test('clicking a book calls onOpenBook with its id', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue(items);
  const onOpenBook = vi.fn();
  renderTab(onOpenBook);
  await waitFor(() => expect(screen.getByText('Alpha Book')).toBeInTheDocument());

  fireEvent.click(screen.getByText('Alpha Book'));
  expect(onOpenBook).toHaveBeenCalledWith('b1');
});

test('shows an empty state when there is no reading history', async () => {
  vi.mocked(PersistenceService.listReadingProgress).mockResolvedValue([]);
  renderTab();
  await waitFor(() => expect(screen.getByText('library.continueReading.empty')).toBeInTheDocument());
});

test('shows the guest auth wall instead of fetching for signed-out users', () => {
  vi.mocked(useAuth).mockReturnValue({ isAuthenticated: false } as any);
  renderTab();
  expect(screen.getByTestId('guest-auth-wall')).toBeInTheDocument();
  expect(PersistenceService.listReadingProgress).not.toHaveBeenCalled();
});
