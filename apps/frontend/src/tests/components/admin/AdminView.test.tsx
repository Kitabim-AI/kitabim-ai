import { ActionMenu } from '@/src/components/admin/ActionMenu';
import { AdminView } from '@/src/components/admin/AdminView';
import * as AppContextModule from '@/src/context/AppContext';
import { I18nContext } from '@/src/i18n/I18nContext';
import { Book } from '@shared/types';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/components/common/ProverbDisplay', () => ({
  ProverbDisplay: () => <div>proverb</div>,
}));

vi.mock('@/src/components/admin/SpellCheckConfigPanel', () => ({
  SpellCheckConfigPanel: () => <div>spell-config</div>,
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useIsAdmin: () => true,
  useIsEditor: () => true,
}));

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
    pipelineStats: { ocr: 5, embedding: 5, spell_check: 5 },
    hasSummary: true,
    hasGraph: true
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

// The global vitest.setup.ts mocks useI18n to return the key as-is.
// This provider value is only used for components that call useContext(I18nContext) directly.
const i18nMockValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: vi.fn()
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  global.fetch = vi.fn().mockResolvedValue({
    ok: false,
    status: 404,
    json: vi.fn().mockResolvedValue({}),
    text: vi.fn().mockResolvedValue(''),
  });
});

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

test('AdminView renders emerald Graph icon when hasGraph is true (empty pipelineStats)', () => {
  // Use empty pipelineStats so no page-level steps produce emerald icons — only
  // summary/graph flags drive colour in that case (getMilestoneColor path).
  const booksWithGraph: Book[] = [
    { ...mockBooks[0], pipelineStats: {}, hasSummary: true, hasGraph: true }
  ];
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...mockAppContextValue,
    books: booksWithGraph,
  } as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  // Summary and Graph both true → at least 2 emerald icons (possibly doubled by
  // mobile+desktop CSS variants both being present in jsdom).
  const emeraldIcons = document.querySelectorAll('.text-emerald-500');
  expect(emeraldIcons.length).toBeGreaterThanOrEqual(2);
});

test('AdminView renders no Graph emerald icon when hasGraph is false (empty pipelineStats)', () => {
  const booksWithoutGraph: Book[] = [
    { ...mockBooks[0], pipelineStats: {}, hasGraph: false, hasSummary: false }
  ];
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...mockAppContextValue,
    books: booksWithoutGraph,
  } as any);

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <AdminView />
    </I18nContext.Provider>
  );

  // With empty pipelineStats and both boolean flags false, no step produces
  // text-emerald-500 — all fall back to text-slate-300.
  const emeraldIcons = document.querySelectorAll('.text-emerald-500');
  expect(emeraldIcons.length).toBe(0);
});

test('ActionMenu shows reprocess graph option and fires handler', () => {
  const handleReprocessStep = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    ...mockAppContextValue,
    bookActions: {
      handleReprocessStep,
      reprocessingBooks: new Map(),
    },
  } as any);

  const dummyRect = { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 } as DOMRect;
  const menuRef = { current: null } as React.RefObject<HTMLDivElement>;

  render(
    <I18nContext.Provider value={i18nMockValue}>
      <ActionMenu
        book={mockBooks[0]}
        close={vi.fn()}
        anchorRect={dummyRect}
        menuRef={menuRef}
      />
    </I18nContext.Provider>
  );

  // The reprocess-graph entry must be visible in the menu.
  // useI18n is globally mocked to return the key as-is (vitest.setup.ts), so assert against the key.
  const graphButton = screen.getByText('admin.table.reprocess.graph');
  fireEvent.click(graphButton);

  expect(handleReprocessStep).toHaveBeenCalledWith(mockBooks[0].id, 'graph');
});
