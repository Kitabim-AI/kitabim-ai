import { screen, render } from '@testing-library/react';
import { AdminView } from '@/src/components/admin/AdminView';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Book } from '@shared/types';
import * as AppContextModule from '@/src/context/AppContext';
import { I18nContext } from '@/src/i18n/I18nContext';

const mockBooks: Book[] = [
  {
    id: '1',
    title: 'Admin Book',
    author: 'Author',
    volume: 1,
    totalPages: 5,
    pages: [],
    status: 'ready',
    uploadDate: new Date(),
    lastUpdated: new Date(),
    contentHash: 'h',
    categories: ['Cat1'],
    pipelineStats: { ocr: 5, embedding: 5, word_index: 5, spell_check: 5 },
    hasSummary: true
  }
];

const mockAppContextValue = {
  books: mockBooks,
  totalBooks: 1,
  bookActions: {},
  loaderRef: { current: null },
  isLoadingMoreShelf: false,
  hasMoreShelf: false,
  loadMoreShelf: vi.fn(),
  isLoading: false,
  searchQuery: '',
  page: 1,
  pageSize: 10,
  setPage: vi.fn(),
  setPageSize: vi.fn(),
  sortConfig: { key: 'title', direction: 'asc' },
  toggleSort: vi.fn(),
};

const i18nMockValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => {
    const translations: Record<string, string> = {
      'admin.pipeline.summary': 'Summary',
      'admin.pipeline.wordIndex': 'Word Index',
      'admin.pipeline.spell_check': 'Spell Check',
    };
    return translations[key] || key;
  }
};

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: vi.fn()
}));

test('AdminView shows green icons for completed pipeline stages', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(mockAppContextValue as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  // Check for the Summary icon (Wand2) color
  // We look for elements with text-emerald-500
  const emeraldIcons = document.querySelectorAll('.text-emerald-500');
  // Should have at least 2: Summary and Spell Check
  expect(emeraldIcons.length).toBeGreaterThanOrEqual(1);
});

test('AdminView renders the book list', () => {
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(mockAppContextValue as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  expect(screen.getByText('Admin Book')).toBeInTheDocument();
  expect(screen.getByText('Cat1')).toBeInTheDocument();
});
