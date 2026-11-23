import { ChunkInspectorView } from '@/src/components/admin/chunks/ChunkInspectorView';
import * as AppContextModule from '@/src/context/AppContext';
import { getNestedTranslation, translations } from '@/src/i18n/i18n';
import { PersistenceService } from '@/src/services/persistenceService';
import { Book, ChunkInspectorResponse } from '@shared/types';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: vi.fn(),
}));

const mockBook: Book = {
  id: 'book-kutadgu-01',
  title: 'قۇتادغۇ بىلىك',
  author: 'يۈسۈپ خاس ھاجىپ',
  volume: 1,
  totalPages: 40,
  pages: [],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'hash-kb',
  categories: ['كلاسسىك ئەدەبىيات'],
};

const baseInspectorResponse: ChunkInspectorResponse = {
  bookId: 'book-kutadgu-01',
  bookTitle: 'قۇتادغۇ بىلىك',
  contentPageOffset: 4,
  ragThreshold: 0.35,
  stats: {
    totalChunks: 18,
    embeddedChunks: 18,
    unembeddedChunks: 0,
    crossPageChunks: 3,
    shortChunks: 1,
    oversizedChunks: 0,
    sectionsCount: 1,
  },
  sections: [
    {
      id: 10,
      parentId: null,
      sectionIndex: 0,
      level: 1,
      sectionType: 'chapter',
      source: 'toc_matched',
      title: 'ئەدلىيە ۋە قانۇن بابى',
      startPage: 5,
      endPage: 20,
      chunkCount: 18,
    },
  ],
  totalMatching: 1,
  chunks: [
    {
      id: 501,
      chunkIndex: 1,
      pageNumber: 12,
      endPageNumber: 13,
      contentPageNumber: '8',
      endContentPageNumber: '9',
      sectionId: 10,
      sectionTitle: 'ئەدلىيە ۋە قانۇن بابى',
      text: 'ئالدىنقى بۆلەكتىن تەكرارلانغان جۈملە.\n\nئادالەت بىلەن ئەلنى تۈزەش ھەققىدە بايان قىلىنىدۇ.\n\n① بۇ يەردە كۈنتوغدى ئېلىك تىلغا ئېلىنىدۇ.',
      charCount: 132,
      textHash: 'abcdef1234567890',
      hasEmbedding: true,
      embeddingPrefix: 'قۇتادغۇ بىلىك — ئەدلىيە ۋە قانۇن بابى',
      overlapPrefix: 'ئالدىنقى بۆلەكتىن تەكرارلانغان جۈملە.',
      similarity: null,
    },
  ],
};

describe('ChunkInspectorView', () => {
  const setView = vi.fn();
  const setCurrentPage = vi.fn();
  const openReader = vi.fn();
  const handleReprocessStep = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    vi.mocked(AppContextModule.useAppContext).mockReturnValue({
      selectedBook: mockBook,
      currentPage: 12,
      setCurrentPage,
      setView,
      inspectorInitialPage: 12,
      inspectorOriginView: 'reader',
      bookActions: {
        openReader,
        handleReprocessStep,
        reprocessingBooks: new Map(),
      },
    } as any);

    vi.spyOn(PersistenceService, 'getBookChunksInspector').mockResolvedValue(
      baseInspectorResponse
    );
    vi.spyOn(PersistenceService, 'getPage').mockImplementation(
      async (_bookId: string, pageNum: number) => ({
        pageNumber: pageNum,
        contentPageNumber: String(pageNum - 4),
        text:
          pageNum === 12
            ? '[Header] قۇتادغۇ بىلىك\n\nئادالەت بىلەن ئەلنى تۈزەش ھەققىدە'
            : 'بايان قىلىنىدۇ.\n\n① بۇ يەردە كۈنتوغدى ئېلىك تىلغا ئېلىنىدۇ.',
        status: 'indexed',
      })
    );
  });

  it('loads page-scoped chunks, source pages comparison, and toggles v2 embedding prefix', async () => {
    render(<ChunkInspectorView />);

    await waitFor(() => {
      expect(PersistenceService.getBookChunksInspector).toHaveBeenCalledWith(
        'book-kutadgu-01',
        expect.objectContaining({
          page: 12,
          filterType: 'all',
          mode: 'semantic',
        })
      );
    });

    // Cross-page badge & section title
    expect(await screen.findByText('admin.chunkInspector.stream.pdfPageRange')).toBeInTheDocument();
    expect(screen.getByText('ئەدلىيە ۋە قانۇن بابى')).toBeInTheDocument();

    // Source pages 12 and 13 loaded and [Header] marked cleaned
    await waitFor(() => {
      expect(PersistenceService.getPage).toHaveBeenCalledWith('book-kutadgu-01', 12);
      expect(PersistenceService.getPage).toHaveBeenCalledWith('book-kutadgu-01', 13);
    });
    expect(await screen.findByText('admin.chunkInspector.source.cleanedNoiseTag')).toBeInTheDocument();

    // Contextual v2 embedding prefix is visible by default and can be toggled off/on
    expect(
      screen.getByText('قۇتادغۇ بىلىك — ئەدلىيە ۋە قانۇن بابى')
    ).toBeInTheDocument();
    const prefixCheckbox = screen.getByLabelText('admin.chunkInspector.toggles.prefix');
    fireEvent.click(prefixCheckbox);
    expect(
      screen.queryByText('قۇتادغۇ بىلىك — ئەدلىيە ۋە قانۇن بابى')
    ).not.toBeInTheDocument();
    fireEvent.click(prefixCheckbox);
    expect(
      screen.getByText('قۇتادغۇ بىلىك — ئەدلىيە ۋە قانۇن بابى')
    ).toBeInTheDocument();
  });

  it('does not auto-trigger search while typing and submits only when clicking the search button', async () => {
    const inspectorSpy = vi
      .spyOn(PersistenceService, 'getBookChunksInspector')
      .mockResolvedValueOnce(baseInspectorResponse)
      .mockResolvedValueOnce({
        ...baseInspectorResponse,
        totalMatching: 2,
        chunks: [
          {
            ...baseInspectorResponse.chunks[0],
            similarity: 0.82,
          },
          {
            ...baseInspectorResponse.chunks[0],
            id: 502,
            chunkIndex: 2,
            pageNumber: 15,
            endPageNumber: 15,
            similarity: 0.21,
          },
        ],
      });

    render(<ChunkInspectorView />);
    await screen.findByText('admin.chunkInspector.stream.pdfPageRange');
    expect(inspectorSpy).toHaveBeenCalledTimes(1);

    const input = screen.getByPlaceholderText('admin.chunkInspector.placeholderSemantic');
    fireEvent.change(input, { target: { value: 'ئادالەت دېگەن نېمە؟' } });

    // Wait longer than any previous debounce window — still no search API call
    await new Promise((r) => setTimeout(r, 620));
    expect(inspectorSpy).toHaveBeenCalledTimes(1);

    // Explicitly click the Search button
    const searchBtn = screen.getByRole('button', {
      name: /admin\.chunkInspector\.searchButton/,
    });
    fireEvent.click(searchBtn);

    await waitFor(() => {
      expect(inspectorSpy).toHaveBeenCalledTimes(2);
      expect(inspectorSpy).toHaveBeenLastCalledWith(
        'book-kutadgu-01',
        expect.objectContaining({
          page: null,
          q: 'ئادالەت دېگەن نېمە؟',
          mode: 'semantic',
        })
      );
    });

    expect(
      await screen.findByText(/0\.82 · admin\.chunkInspector\.stream\.ragPass/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/0\.21 · admin\.chunkInspector\.stream\.ragBelowThreshold/)
    ).toBeInTheDocument();

    fireEvent.click(screen.getByText('admin.chunkInspector.backToReaderPage'));
    expect(setView).toHaveBeenCalledWith('reader');
  });

  it('triggers Stage-2 RAG rerank when clicking the rerank button and renders rerank badges', async () => {
    const inspectorSpy = vi
      .spyOn(PersistenceService, 'getBookChunksInspector')
      .mockResolvedValueOnce(baseInspectorResponse)
      .mockResolvedValueOnce({
        ...baseInspectorResponse,
        reranked: true,
        rerankSelectedCount: 1,
        totalMatching: 2,
        chunks: [
          {
            ...baseInspectorResponse.chunks[0],
            id: 602,
            pageNumber: 452,
            endPageNumber: 453,
            similarity: 0.69,
            rerankRank: 1,
            rerankDropped: false,
          },
          {
            ...baseInspectorResponse.chunks[0],
            id: 601,
            pageNumber: 367,
            endPageNumber: 367,
            similarity: 0.75,
            rerankRank: null,
            rerankDropped: true,
          },
        ],
      });

    render(<ChunkInspectorView />);
    await screen.findByText('admin.chunkInspector.stream.pdfPageRange');

    const input = screen.getByPlaceholderText('admin.chunkInspector.placeholderSemantic');
    fireEvent.change(input, { target: { value: 'ئۇۋەيسخان قانداق ۋاپات بولىدۇ؟' } });

    const rerankBtn = screen.getByRole('button', {
      name: /admin\.chunkInspector\.rerankButton/,
    });
    fireEvent.click(rerankBtn);

    await waitFor(() => {
      expect(inspectorSpy).toHaveBeenLastCalledWith(
        'book-kutadgu-01',
        expect.objectContaining({
          page: null,
          q: 'ئۇۋەيسخان قانداق ۋاپات بولىدۇ؟',
          mode: 'semantic',
          rerank: true,
        })
      );
    });

    expect(
      await screen.findByText('admin.chunkInspector.stream.rerankRankBadge')
    ).toBeInTheDocument();
    expect(
      screen.getByText('admin.chunkInspector.stream.rerankDroppedBadge')
    ).toBeInTheDocument();
    expect(
      screen.getByText('admin.chunkInspector.stream.rerankedSummary')
    ).toBeInTheDocument();
  });

  it('defines all chunk inspector localization keys in both ug.json and en.json', () => {
    const requiredKeys = [
      'reader.inspectChunks',
      'reader.inspectChunksTitle',
      'admin.table.inspectChunks',
      'admin.chunkInspector.backToReader',
      'admin.chunkInspector.backToReaderPage',
      'admin.chunkInspector.backToAdmin',
      'admin.chunkInspector.copyBookIdTitle',
      'admin.chunkInspector.reprocessChunking',
      'admin.chunkInspector.loadError',
      'admin.chunkInspector.modeSemantic',
      'admin.chunkInspector.modeText',
      'admin.chunkInspector.placeholderSemantic',
      'admin.chunkInspector.placeholderText',
      'admin.chunkInspector.searchButton',
      'admin.chunkInspector.rerankButton',
      'admin.chunkInspector.rerankButtonTitle',
      'admin.chunkInspector.clear',
      'admin.chunkInspector.pageLabel',
      'admin.chunkInspector.allPagesPlaceholder',
      'admin.chunkInspector.filters.all',
      'admin.chunkInspector.filters.crossPage',
      'admin.chunkInspector.filters.unembedded',
      'admin.chunkInspector.filters.short',
      'admin.chunkInspector.filters.oversized',
      'admin.chunkInspector.toggles.overlap',
      'admin.chunkInspector.toggles.prefix',
      'admin.chunkInspector.toggles.sourcePane',
      'admin.chunkInspector.stats.totalChunks',
      'admin.chunkInspector.stats.embedded',
      'admin.chunkInspector.stats.crossPage',
      'admin.chunkInspector.stats.sections',
      'admin.chunkInspector.stats.pageOffset',
      'admin.chunkInspector.sectionSource.frontMatter',
      'admin.chunkInspector.sectionSource.tocMatched',
      'admin.chunkInspector.sectionSource.tocInterpolated',
      'admin.chunkInspector.sectionSource.headerDetected',
      'admin.chunkInspector.sectionSource.auto',
      'admin.chunkInspector.structure.title',
      'admin.chunkInspector.structure.all',
      'admin.chunkInspector.structure.empty',
      'admin.chunkInspector.structure.meta',
      'admin.chunkInspector.stream.count',
      'admin.chunkInspector.stream.countPage',
      'admin.chunkInspector.stream.loading',
      'admin.chunkInspector.stream.ragParams',
      'admin.chunkInspector.stream.empty',
      'admin.chunkInspector.stream.pdfPageSingle',
      'admin.chunkInspector.stream.pdfPageRange',
      'admin.chunkInspector.stream.printedPageSingle',
      'admin.chunkInspector.stream.printedPageRange',
      'admin.chunkInspector.stream.crossPageBadge',
      'admin.chunkInspector.stream.ragPass',
      'admin.chunkInspector.stream.ragBelowThreshold',
      'admin.chunkInspector.stream.rerankedSummary',
      'admin.chunkInspector.stream.rerankRankBadge',
      'admin.chunkInspector.stream.rerankDroppedBadge',
      'admin.chunkInspector.stream.charCount',
      'admin.chunkInspector.stream.hasEmbedding',
      'admin.chunkInspector.stream.missingEmbedding',
      'admin.chunkInspector.stream.embeddingPrefixHint',
      'admin.chunkInspector.stream.overlapTooltip',
      'admin.chunkInspector.stream.copy',
      'admin.chunkInspector.stream.openInReader',
      'admin.chunkInspector.stream.loadMore',
      'admin.chunkInspector.source.title',
      'admin.chunkInspector.source.pageSingle',
      'admin.chunkInspector.source.pageRange',
      'admin.chunkInspector.source.loading',
      'admin.chunkInspector.source.selectPrompt',
      'admin.chunkInspector.source.stitchBoundary',
      'admin.chunkInspector.source.frontMatter',
      'admin.chunkInspector.source.emptyPage',
      'admin.chunkInspector.source.cleanedNoiseTag',
    ];

    for (const key of requiredKeys) {
      const ugVal = getNestedTranslation(translations.ug, key);
      const enVal = getNestedTranslation(translations.en, key);
      expect(ugVal, `Missing ug translation for ${key}`).not.toBe(key);
      expect(enVal, `Missing en translation for ${key}`).not.toBe(key);
      expect(typeof ugVal).toBe('string');
      expect(typeof enVal).toBe('string');
    }
  });
});
