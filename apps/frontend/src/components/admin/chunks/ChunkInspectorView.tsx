import {
  ChunkInspectorFilterType,
  ChunkInspectorItem,
  ChunkInspectorResponse,
  ChunkInspectorSearchMode,
} from '@shared/types';
import {
  ArrowRight,
  Check,
  Copy,
  CornerDownLeft,
  CornerDownRight,
  ExternalLink,
  FileText,
  Link2,
  ListTree,
  Loader2,
  RotateCw,
  Search,
  Sparkles,
  Type,
  X,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { REPROCESS_STEP } from '../../../constants/milestones';
import { useAppContext } from '../../../context/AppContext';
import { useI18n } from '../../../i18n/I18nContext';
import { PersistenceService } from '../../../services/persistenceService';

const FOOTNOTE_LINE_RE = /^(?:[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳¹²³⁴⁵⁶⁷⁸⁹]\s+|\[\d{1,3}\]:\s+)/;
const ISOLATED_PAGE_NUM_RE = /^[\(\[\-–—\s]*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}[\)\]\-–—\s]*$/;
const DIVIDER_NOISE_RE = /^(?:[*•·\-—–=~_※✦✧❖◆◇▪▫×xX]\s*){2,}$/;
const DEFAULT_LOAD_ERROR_SENTINEL = '__DEFAULT_CHUNK_LOAD_ERROR__';

interface ParsedSourceLine {
  kind: 'noise' | 'heading' | 'footnote' | 'body';
  text: string;
}

function classifySourcePageLines(rawText: string): ParsedSourceLine[] {
  if (!rawText || !rawText.trim()) return [];
  const paragraphs = rawText.split(/\n\s*\n/);
  const result: ParsedSourceLine[] = [];

  for (const para of paragraphs) {
    const trimmed = para.trim();
    if (!trimmed) continue;

    const subLines = trimmed.split('\n');
    const bodyAccumulator: string[] = [];

    const flushBody = () => {
      if (bodyAccumulator.length > 0) {
        result.push({ kind: 'body', text: bodyAccumulator.join('\n') });
        bodyAccumulator.length = 0;
      }
    };

    for (const rawLine of subLines) {
      const ln = rawLine.trim();
      if (!ln) continue;

      if (
        /^\[(Header|Footer)\]/i.test(ln) ||
        /^<!--.*-->$/.test(ln) ||
        ISOLATED_PAGE_NUM_RE.test(ln) ||
        DIVIDER_NOISE_RE.test(ln)
      ) {
        flushBody();
        result.push({ kind: 'noise', text: ln });
      } else if (/^#{1,6}\s+\S/.test(ln)) {
        flushBody();
        result.push({ kind: 'heading', text: ln });
      } else if (FOOTNOTE_LINE_RE.test(ln)) {
        flushBody();
        result.push({ kind: 'footnote', text: ln });
      } else {
        bodyAccumulator.push(rawLine);
      }
    }
    flushBody();
  }

  return result;
}

function splitChunkBodyAndFootnotes(
  fullText: string,
  overlapPrefix: string | null
): { overlap: string; body: string; footnotes: string[] } {
  let remainder = fullText || '';
  let overlap = '';

  if (overlapPrefix && remainder.startsWith(overlapPrefix)) {
    overlap = overlapPrefix;
    remainder = remainder.slice(overlapPrefix.length).replace(/^\s+/, '');
  }

  const blocks = remainder.split('\n\n');
  const footnotes: string[] = [];
  while (blocks.length > 1 && FOOTNOTE_LINE_RE.test(blocks[blocks.length - 1].trim())) {
    footnotes.unshift(blocks.pop()!.trim());
  }

  return {
    overlap,
    body: blocks.join('\n\n'),
    footnotes,
  };
}

function highlightQueryMatches(
  text: string,
  query: string,
  mode: ChunkInspectorSearchMode
): React.ReactNode {
  const q = query.trim();
  if (!text || !q) return text;

  const terms =
    mode === 'text'
      ? [q]
      : q
          .replace(/[؟?،,.!«»()\[\]"']/g, ' ')
          .split(/\s+/)
          .filter((w) => w.length >= 3);

  if (terms.length === 0) return text;

  const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  const regex = new RegExp(`(${escaped.join('|')})`, 'gi');
  const parts = text.split(regex);
  if (parts.length <= 1) return text;

  const lowerTerms = new Set(terms.map((term) => term.toLowerCase()));
  return parts.map((part, idx) =>
    lowerTerms.has(part.toLowerCase()) ? (
      <mark
        key={idx}
        className="bg-emerald-500/20 dark:bg-emerald-400/25 text-inherit rounded px-0.5"
      >
        {part}
      </mark>
    ) : (
      <React.Fragment key={idx}>{part}</React.Fragment>
    )
  );
}

function formatSectionSourceBadge(
  source: string | null,
  sectionType: string,
  t: (key: string, params?: Record<string, string | number>) => string
): string {
  if (sectionType === 'front_matter') return t('admin.chunkInspector.sectionSource.frontMatter');
  if (source === 'toc_matched') return t('admin.chunkInspector.sectionSource.tocMatched');
  if (source === 'toc_interpolated') {
    return t('admin.chunkInspector.sectionSource.tocInterpolated');
  }
  if (source === 'header_detected') return t('admin.chunkInspector.sectionSource.headerDetected');
  return t('admin.chunkInspector.sectionSource.auto');
}

export const ChunkInspectorView: React.FC = () => {
  const { t, language } = useI18n();
  const {
    selectedBook,
    currentPage,
    setCurrentPage,
    setView,
    bookActions,
    inspectorInitialPage,
    inspectorOriginView,
  } = useAppContext();

  const [searchMode, setSearchMode] = useState<ChunkInspectorSearchMode>('semantic');
  const [appliedMode, setAppliedMode] = useState<ChunkInspectorSearchMode>('semantic');
  const [queryInput, setQueryInput] = useState('');
  const [appliedQuery, setAppliedQuery] = useState('');
  const [appliedRerank, setAppliedRerank] = useState(false);
  const [searchRunId, setSearchRunId] = useState(0);
  const [pageInput, setPageInput] = useState<string>(() =>
    inspectorInitialPage ? String(inspectorInitialPage) : ''
  );
  const [debouncedPage, setDebouncedPage] = useState<number | null>(() =>
    inspectorInitialPage ?? null
  );
  const pageManuallyEditedRef = useRef(false);
  const [filterType, setFilterType] = useState<ChunkInspectorFilterType>('all');
  const [selectedSectionId, setSelectedSectionId] = useState<number | null>(null);

  const [showOverlap, setShowOverlap] = useState(true);
  const [showPrefix, setShowPrefix] = useState(true);
  const [showSourcePane, setShowSourcePane] = useState(true);

  const [data, setData] = useState<ChunkInspectorResponse | null>(null);
  const [chunks, setChunks] = useState<ChunkInspectorItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedChunkId, setSelectedChunkId] = useState<number | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Cached source pages by physical pageNumber
  const pageCacheRef = useRef<Map<number, { text: string; contentPageNumber: string | null }>>(
    new Map()
  );
  const [sourcePages, setSourcePages] = useState<
    Array<{ pageNumber: number; text: string; contentPageNumber: string | null }>
  >([]);
  const [isLoadingSource, setIsLoadingSource] = useState(false);

  // Reset cache & initial page when book changes
  useEffect(() => {
    pageCacheRef.current.clear();
    if (selectedBook?.pages?.length) {
      for (const p of selectedBook.pages) {
        if (typeof p.pageNumber === 'number' && typeof p.text === 'string') {
          pageCacheRef.current.set(p.pageNumber, {
            text: p.text,
            contentPageNumber:
              p.contentPageNumber !== undefined && p.contentPageNumber !== null
                ? String(p.contentPageNumber)
                : null,
          });
        }
      }
    }
  }, [selectedBook?.id]);

  // Sync inspectorInitialPage when re-entering inspector
  useEffect(() => {
    const nextStr = inspectorInitialPage ? String(inspectorInitialPage) : '';
    pageManuallyEditedRef.current = false;
    setPageInput(nextStr);
    setDebouncedPage(inspectorInitialPage ?? null);
  }, [inspectorInitialPage, selectedBook?.id]);

  // Debounce page number input
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const trimmed = pageInput.trim();
      if (!trimmed) {
        setDebouncedPage(null);
      } else {
        const parsed = parseInt(trimmed, 10);
        setDebouncedPage(Number.isFinite(parsed) && parsed >= 1 ? parsed : null);
      }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [pageInput]);

  const fetchChunks = useCallback(
    async (skipOffset: number, append: boolean) => {
      if (!selectedBook) return;
      if (append) {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
      }
      setError(null);

      try {
        const res = await PersistenceService.getBookChunksInspector(selectedBook.id, {
          page: debouncedPage,
          sectionId: selectedSectionId,
          filterType,
          mode: appliedMode,
          q: appliedQuery,
          rerank: appliedRerank && skipOffset === 0,
          skip: skipOffset,
          limit: 100,
        });
        setData(res);
        setChunks((prev) => (append ? [...prev, ...res.chunks] : res.chunks));
        if (!append) {
          setSelectedChunkId((prevId) =>
            appliedRerank
              ? (res.chunks[0]?.id ?? null)
              : res.chunks.some((c) => c.id === prevId)
                ? prevId
                : (res.chunks[0]?.id ?? null)
          );
        }
      } catch (err) {
        setError(
          err instanceof Error && err.message ? err.message : DEFAULT_LOAD_ERROR_SENTINEL
        );
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [
      selectedBook,
      debouncedPage,
      selectedSectionId,
      filterType,
      appliedMode,
      appliedQuery,
      appliedRerank,
      searchRunId,
    ]
  );

  useEffect(() => {
    fetchChunks(0, false);
  }, [fetchChunks]);

  const selectedChunk = useMemo(
    () => chunks.find((c) => c.id === selectedChunkId) ?? chunks[0] ?? null,
    [chunks, selectedChunkId]
  );

  // Load source pages for the currently selected chunk
  useEffect(() => {
    if (!selectedBook || !selectedChunk || !showSourcePane) {
      setSourcePages([]);
      return;
    }

    let cancelled = false;
    const startP = selectedChunk.pageNumber;
    const endP = Math.max(startP, selectedChunk.endPageNumber || startP);
    const neededPages: number[] = [];
    for (let p = startP; p <= endP; p++) {
      neededPages.push(p);
    }

    const loadPages = async () => {
      const missing = neededPages.filter((p) => !pageCacheRef.current.has(p));
      if (missing.length > 0) {
        setIsLoadingSource(true);
        await Promise.all(
          missing.map(async (pno) => {
            const pg = await PersistenceService.getPage(selectedBook.id, pno);
            if (pg) {
              pageCacheRef.current.set(pno, {
                text: pg.text || '',
                contentPageNumber:
                  pg.contentPageNumber !== undefined && pg.contentPageNumber !== null
                    ? String(pg.contentPageNumber)
                    : null,
              });
            }
          })
        );
        if (!cancelled) setIsLoadingSource(false);
      }

      if (!cancelled) {
        setSourcePages(
          neededPages.map((pno) => {
            const cached = pageCacheRef.current.get(pno);
            return {
              pageNumber: pno,
              text: cached?.text ?? '',
              contentPageNumber: cached?.contentPageNumber ?? null,
            };
          })
        );
      }
    };

    loadPages();
    return () => {
      cancelled = true;
    };
  }, [selectedBook?.id, selectedChunk?.id, showSourcePane]);

  if (!selectedBook) return null;

  const handleBack = () => {
    if (inspectorOriginView === 'reader') {
      setView('reader');
    } else {
      setView('admin');
    }
  };

  const handleOpenPageInReader = (pageNum: number) => {
    if (selectedBook.pages && selectedBook.pages.length > 0) {
      setCurrentPage(pageNum);
      setView('reader');
    } else {
      bookActions.openReader(selectedBook, pageNum);
    }
  };

  const handleCopy = async (key: string, textToCopy: string) => {
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedId(key);
      window.setTimeout(() => setCopiedId((cur) => (cur === key ? null : cur)), 1500);
    } catch {
      // Clipboard unavailable
    }
  };

  const stats = data?.stats;
  const ragThreshold = data?.ragThreshold ?? 0.35;
  const reprocessingStep = bookActions.reprocessingBooks?.get(selectedBook.id);

  const pills: Array<{ id: ChunkInspectorFilterType; label: string; count: number }> = [
    { id: 'all', label: t('admin.chunkInspector.filters.all'), count: stats?.totalChunks ?? 0 },
    {
      id: 'cross_page',
      label: t('admin.chunkInspector.filters.crossPage'),
      count: stats?.crossPageChunks ?? 0,
    },
    {
      id: 'unembedded',
      label: t('admin.chunkInspector.filters.unembedded'),
      count: stats?.unembeddedChunks ?? 0,
    },
    {
      id: 'short',
      label: t('admin.chunkInspector.filters.short'),
      count: stats?.shortChunks ?? 0,
    },
    ...(stats && stats.oversizedChunks > 0
      ? [
          {
            id: 'oversized' as const,
            label: t('admin.chunkInspector.filters.oversized'),
            count: stats.oversizedChunks,
          },
        ]
      : []),
  ];

  const embeddedPct =
    stats && stats.totalChunks > 0
      ? Math.round((stats.embeddedChunks / stats.totalChunks) * 100)
      : 0;

  return (
    <div
      className="w-full max-w-[1540px] mx-auto px-3 sm:px-4 md:px-0 pb-8 space-y-4"
      dir="rtl"
      lang="ug"
    >
      <style>{`
        .chunk-inspector-grid {
          display: grid;
          grid-template-columns: 260px minmax(0, 1fr) 350px;
          grid-template-areas: "sections stream source";
          gap: 1rem;
          align-items: start;
        }
        .chunk-inspector-grid[data-source-open="false"] {
          grid-template-columns: 260px minmax(0, 1fr);
          grid-template-areas: "sections stream";
        }
        @media (max-width: 1120px) {
          .chunk-inspector-grid,
          .chunk-inspector-grid[data-source-open="false"] {
            grid-template-columns: minmax(0, 1fr);
            grid-template-areas:
              "sections"
              "stream"
              "source";
          }
        }
        .ci-area-sections { grid-area: sections; min-inline-size: 0; }
        .ci-area-stream   { grid-area: stream; min-inline-size: 0; }
        .ci-area-source   { grid-area: source; min-inline-size: 0; }
        .ci-pane-scroll {
          max-block-size: calc(100dvh - 300px);
          min-block-size: 360px;
          overflow-y: auto;
          scrollbar-gutter: stable;
          overscroll-behavior: contain;
        }
        .ci-pill-row {
          display: flex;
          flex-wrap: wrap;
          flex-wrap: balance;
          align-items: safe center;
          gap: 0.5rem;
        }
      `}</style>

      {/* Book-Scoped Header */}
      <header className="glass-panel bg-white/85 dark:bg-slate-900/85 border border-[#0369a1]/15 dark:border-[#38bdf8]/15 rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={handleBack}
            className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 hover:border-[#0369a1] dark:hover:border-[#38bdf8] text-xs font-semibold text-slate-700 dark:text-slate-200 transition flex items-center gap-1.5 cursor-pointer"
          >
            <ArrowRight size={15} />
            <span>
              {inspectorOriginView === 'reader'
                ? currentPage
                  ? t('admin.chunkInspector.backToReaderPage', { page: currentPage })
                  : t('admin.chunkInspector.backToReader')
                : t('admin.chunkInspector.backToAdmin')}
            </span>
          </button>

          <div className="min-w-0 flex flex-wrap items-center gap-2">
            <h1 className="text-sm sm:text-base font-bold text-slate-900 dark:text-slate-100 truncate">
              {selectedBook.title}
            </h1>
            {selectedBook.author && (
              <span className="text-xs text-slate-500 dark:text-slate-400">
                — {selectedBook.author}
              </span>
            )}
            <button
              type="button"
              onClick={() => handleCopy('book-id', selectedBook.id)}
              title={t('admin.chunkInspector.copyBookIdTitle')}
              className="px-2 py-0.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 inline-flex items-center gap-1 cursor-pointer"
            >
              <span>{selectedBook.id.slice(0, 10)}</span>
              {copiedId === 'book-id' ? (
                <Check size={12} className="text-emerald-500" />
              ) : (
                <Copy size={11} />
              )}
            </button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2" style={{ marginInlineStart: 'auto' }}>
          <button
            type="button"
            onClick={() => bookActions.handleReprocessStep(selectedBook.id, REPROCESS_STEP.CHUNKING)}
            disabled={reprocessingStep === REPROCESS_STEP.CHUNKING}
            className="px-3 py-1.5 rounded-xl border border-[#0369a1]/25 dark:border-[#38bdf8]/25 bg-[#0369a1]/5 dark:bg-[#38bdf8]/10 hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] text-xs font-semibold transition flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
          >
            {reprocessingStep === REPROCESS_STEP.CHUNKING ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <RotateCw size={14} />
            )}
            <span>{t('admin.chunkInspector.reprocessChunking')}</span>
          </button>
        </div>
      </header>

      {/* Search + Filters + Telemetry Card */}
      <section className="glass-panel bg-white/85 dark:bg-slate-900/85 border border-[#0369a1]/15 dark:border-[#38bdf8]/15 rounded-2xl p-3.5 space-y-3 shadow-sm">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search Mode Switch: Semantic Question vs Exact Text */}
          <div className="inline-flex rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 p-0.5 text-xs shrink-0">
            <button
              type="button"
              onClick={() => setSearchMode('semantic')}
              className={`px-2.5 py-1.5 rounded-lg transition flex items-center gap-1.5 cursor-pointer font-medium ${
                searchMode === 'semantic'
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              <Sparkles size={13} />
              <span>{t('admin.chunkInspector.modeSemantic')}</span>
            </button>
            <button
              type="button"
              onClick={() => setSearchMode('text')}
              className={`px-2.5 py-1.5 rounded-lg transition flex items-center gap-1.5 cursor-pointer font-medium ${
                searchMode === 'text'
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              <Type size={13} />
              <span>{t('admin.chunkInspector.modeText')}</span>
            </button>
          </div>

          {/* Question / Search Input (explicit button / Enter submit — no auto-trigger) */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = queryInput.trim();
              if (trimmed && !pageManuallyEditedRef.current && pageInput) {
                setPageInput('');
                setDebouncedPage(null);
              }
              setAppliedMode(searchMode);
              setAppliedQuery(trimmed);
              setAppliedRerank(false);
              setSearchRunId((n) => n + 1);
            }}
            className="relative flex-1 min-w-[230px] flex items-center gap-1.5"
          >
            <div className="relative flex-1">
              <input
                type="search"
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                placeholder={
                  searchMode === 'semantic'
                    ? t('admin.chunkInspector.placeholderSemantic')
                    : t('admin.chunkInspector.placeholderText')
                }
                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950/70 text-slate-900 dark:text-slate-100 ps-3 pe-8 py-1.5 text-xs focus:outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
              />
              <Search
                size={14}
                className="absolute top-1/2 -translate-y-1/2 end-2.5 text-slate-400 pointer-events-none"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading || (!queryInput.trim() && !appliedQuery)}
              className="px-3 py-1.5 rounded-xl bg-[#0369a1] dark:bg-[#38bdf8] hover:bg-[#0284c7] dark:hover:bg-[#7dd3fc] text-white dark:text-slate-950 text-xs font-semibold transition inline-flex items-center gap-1.5 disabled:opacity-45 cursor-pointer shrink-0"
            >
              {isLoading && Boolean(appliedQuery) && !appliedRerank ? (
                <Loader2 size={13} className="animate-spin" />
              ) : (
                <Search size={13} />
              )}
              <span>{t('admin.chunkInspector.searchButton')}</span>
            </button>

            {searchMode === 'semantic' && (
              <button
                type="button"
                title={t('admin.chunkInspector.rerankButtonTitle')}
                disabled={isLoading || !queryInput.trim()}
                onClick={() => {
                  const trimmed = queryInput.trim();
                  if (!trimmed) return;
                  if (!pageManuallyEditedRef.current && pageInput) {
                    setPageInput('');
                    setDebouncedPage(null);
                  }
                  setAppliedMode('semantic');
                  setAppliedQuery(trimmed);
                  setAppliedRerank(true);
                  setSearchRunId((n) => n + 1);
                }}
                className="px-3 py-1.5 rounded-xl border border-indigo-500/40 dark:border-indigo-400/40 bg-indigo-500/10 dark:bg-indigo-400/15 hover:bg-indigo-500/20 dark:hover:bg-indigo-400/25 text-indigo-700 dark:text-indigo-300 text-xs font-semibold transition inline-flex items-center gap-1.5 disabled:opacity-45 cursor-pointer shrink-0"
              >
                {isLoading && appliedRerank ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <Sparkles size={13} />
                )}
                <span>{t('admin.chunkInspector.rerankButton')}</span>
              </button>
            )}

            {(queryInput.trim() || appliedQuery) && (
              <button
                type="button"
                onClick={() => {
                  setQueryInput('');
                  setAppliedQuery('');
                  setAppliedRerank(false);
                }}
                className="px-2.5 py-1.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 inline-flex items-center gap-1 cursor-pointer shrink-0"
              >
                <X size={13} />
                <span>{t('admin.chunkInspector.clear')}</span>
              </button>
            )}
          </form>

          {/* Page # Filter */}
          <label className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              {t('admin.chunkInspector.pageLabel')}
            </span>
            <input
              type="number"
              min={1}
              value={pageInput}
              onChange={(e) => {
                pageManuallyEditedRef.current = e.target.value.trim().length > 0;
                setPageInput(e.target.value);
              }}
              placeholder={t('admin.chunkInspector.allPagesPlaceholder')}
              className="w-20 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950/70 text-slate-900 dark:text-slate-100 px-2.5 py-1.5 text-xs tabular-nums focus:outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8]"
            />
          </label>
        </div>

        {/* Diagnostic Pills + Display Toggles */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-200/70 dark:border-slate-800">
          <div className="ci-pill-row">
            {pills.map((p) => {
              const active = filterType === p.id && !debouncedPage;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    setFilterType(p.id);
                    setPageInput('');
                    setDebouncedPage(null);
                  }}
                  className={`px-2.5 py-1 rounded-full text-xs border transition flex items-center gap-1.5 cursor-pointer ${
                    active
                      ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 border-[#0369a1] dark:border-[#38bdf8] font-medium'
                      : 'bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:text-slate-900 dark:hover:text-slate-200'
                  }`}
                >
                  <span>{p.label}</span>
                  <span className="font-mono text-xs opacity-85">({p.count})</span>
                </button>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs">
            <label className="inline-flex items-center gap-1.5 cursor-pointer select-none text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
              <input
                type="checkbox"
                checked={showOverlap}
                onChange={(e) => setShowOverlap(e.target.checked)}
                className="accent-[#0369a1] dark:accent-[#38bdf8]"
              />
              <span>{t('admin.chunkInspector.toggles.overlap')}</span>
            </label>
            <label className="inline-flex items-center gap-1.5 cursor-pointer select-none text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
              <input
                type="checkbox"
                checked={showPrefix}
                onChange={(e) => setShowPrefix(e.target.checked)}
                className="accent-[#0369a1] dark:accent-[#38bdf8]"
              />
              <span>{t('admin.chunkInspector.toggles.prefix')}</span>
            </label>
            <label className="inline-flex items-center gap-1.5 cursor-pointer select-none text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
              <input
                type="checkbox"
                checked={showSourcePane}
                onChange={(e) => setShowSourcePane(e.target.checked)}
                className="accent-[#0369a1] dark:accent-[#38bdf8]"
              />
              <span>{t('admin.chunkInspector.toggles.sourcePane')}</span>
            </label>
          </div>
        </div>

        {/* Telemetry Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 pt-2 border-t border-slate-200/70 dark:border-slate-800 text-xs">
          <div className="rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-slate-200/70 dark:border-slate-800 px-2.5 py-1.5">
            <div className="text-slate-500 dark:text-slate-400">
              {t('admin.chunkInspector.stats.totalChunks')}
            </div>
            <div className="font-semibold font-mono tabular-nums mt-0.5 text-slate-900 dark:text-slate-100">
              {stats?.totalChunks ?? '—'}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-slate-200/70 dark:border-slate-800 px-2.5 py-1.5">
            <div className="text-slate-500 dark:text-slate-400">
              {t('admin.chunkInspector.stats.embedded')}
            </div>
            <div className="font-semibold font-mono tabular-nums mt-0.5 text-slate-900 dark:text-slate-100">
              {stats ? `${stats.embeddedChunks}/${stats.totalChunks} (${embeddedPct}%)` : '—'}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-slate-200/70 dark:border-slate-800 px-2.5 py-1.5">
            <div className="text-slate-500 dark:text-slate-400">
              {t('admin.chunkInspector.stats.crossPage')}
            </div>
            <div className="font-semibold font-mono tabular-nums mt-0.5 text-slate-900 dark:text-slate-100">
              {stats?.crossPageChunks ?? '—'}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-slate-200/70 dark:border-slate-800 px-2.5 py-1.5">
            <div className="text-slate-500 dark:text-slate-400">
              {t('admin.chunkInspector.stats.sections')}
            </div>
            <div className="font-semibold font-mono tabular-nums mt-0.5 text-slate-900 dark:text-slate-100">
              {stats?.sectionsCount ?? '—'}
            </div>
          </div>
          <div className="rounded-xl bg-slate-50/80 dark:bg-slate-950/50 border border-slate-200/70 dark:border-slate-800 px-2.5 py-1.5">
            <div className="text-slate-500 dark:text-slate-400">
              {t('admin.chunkInspector.stats.pageOffset')}
            </div>
            <div className="font-semibold font-mono tabular-nums mt-0.5 text-slate-900 dark:text-slate-100">
              {data ? `+${data.contentPageOffset}` : '—'}
            </div>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-xl border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-4 py-2.5 text-xs text-red-700 dark:text-red-300">
          {error === DEFAULT_LOAD_ERROR_SENTINEL ? t('admin.chunkInspector.loadError') : error}
        </div>
      )}

      {/* 3-Pane Workbench */}
      <div className="chunk-inspector-grid" data-source-open={String(showSourcePane)}>
        {/* PANE 1: Book Sections Tree */}
        <aside className="ci-area-sections glass-panel bg-white/85 dark:bg-slate-900/85 border border-[#0369a1]/15 dark:border-[#38bdf8]/15 rounded-2xl overflow-clip shadow-sm">
          <div className="px-3.5 py-2.5 border-b border-slate-200/70 dark:border-slate-800 flex items-center justify-between">
            <h2 className="text-xs font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
              <ListTree size={14} className="text-[#0369a1] dark:text-[#38bdf8]" />
              <span>{t('admin.chunkInspector.structure.title')}</span>
            </h2>
            {selectedSectionId !== null && (
              <button
                type="button"
                onClick={() => setSelectedSectionId(null)}
                className="text-xs text-[#0369a1] dark:text-[#38bdf8] hover:underline cursor-pointer"
              >
                {t('admin.chunkInspector.structure.all')}
              </button>
            )}
          </div>

          <div className="ci-pane-scroll p-2 space-y-1">
            {!data?.sections?.length ? (
              <div className="p-4 text-center text-xs text-slate-400">
                {t('admin.chunkInspector.structure.empty')}
              </div>
            ) : (
              data.sections.map((sec) => {
                const isSelected = selectedSectionId === sec.id;
                return (
                  <button
                    key={sec.id}
                    type="button"
                    onClick={() => {
                      setSelectedSectionId((cur) => (cur === sec.id ? null : sec.id));
                      setPageInput('');
                      setDebouncedPage(null);
                    }}
                    style={{
                      paddingInlineStart: sec.level === 2 ? '1.5rem' : '0.625rem',
                    }}
                    className={`w-full text-start py-2 pe-2.5 rounded-xl border transition flex items-start justify-between gap-2 cursor-pointer ${
                      isSelected
                        ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/15 text-[#0369a1] dark:text-[#38bdf8] border-[#0369a1]/40 dark:border-[#38bdf8]/40 font-semibold'
                        : 'border-transparent hover:bg-slate-100/80 dark:hover:bg-slate-800/60 text-slate-800 dark:text-slate-200'
                    }`}
                  >
                    <div className="min-w-0 space-y-0.5">
                      <div className="text-xs leading-snug break-words flex items-start gap-1.5">
                        {sec.level === 2 &&
                          (language === 'ug' ? (
                            <CornerDownLeft
                              size={13}
                              aria-hidden="true"
                              className="shrink-0 mt-0.5 text-slate-400 dark:text-slate-500"
                            />
                          ) : (
                            <CornerDownRight
                              size={13}
                              aria-hidden="true"
                              className="shrink-0 mt-0.5 text-slate-400 dark:text-slate-500"
                            />
                          ))}
                        <span className="min-w-0">{sec.title}</span>
                      </div>
                      <div className="text-xs text-slate-400 font-mono">
                        {t('admin.chunkInspector.structure.meta', {
                          start: sec.startPage,
                          end: sec.endPage,
                          count: sec.chunkCount,
                        })}
                      </div>
                    </div>
                    <span className="text-xs px-1.5 py-0.5 rounded-md border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 shrink-0">
                      {formatSectionSourceBadge(sec.source, sec.sectionType, t)}
                    </span>
                  </button>
                );
              })
            )}
          </div>
        </aside>

        {/* PANE 2: Chunk Stream */}
        <section className="ci-area-stream space-y-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-xs text-slate-500 dark:text-slate-400">
            <span className="flex items-center gap-2">
              {isLoading && (
                <Loader2 size={13} className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" />
              )}
              <span>
                {data
                  ? debouncedPage
                    ? t('admin.chunkInspector.stream.countPage', {
                        shown: chunks.length,
                        total: data.totalMatching,
                        page: debouncedPage,
                      })
                    : t('admin.chunkInspector.stream.count', {
                        shown: chunks.length,
                        total: data.totalMatching,
                      })
                  : t('admin.chunkInspector.stream.loading')}
                {data?.reranked && (
                  <span className="ms-1.5 font-semibold text-indigo-600 dark:text-indigo-300">
                    {t('admin.chunkInspector.stream.rerankedSummary', {
                      count: data.rerankSelectedCount ?? 0,
                    })}
                  </span>
                )}
              </span>
            </span>
            <span className="font-mono">
              {t('admin.chunkInspector.stream.ragParams', { threshold: ragThreshold })}
            </span>
          </div>

          <div className="ci-pane-scroll space-y-3 pe-1">
            {!isLoading && chunks.length === 0 ? (
              <div className="glass-panel bg-white/85 dark:bg-slate-900/85 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 text-center text-xs text-slate-500 dark:text-slate-400">
                {t('admin.chunkInspector.stream.empty')}
              </div>
            ) : (
              chunks.map((ch) => {
                const isSelected = ch.id === selectedChunk?.id;
                const isCross = ch.endPageNumber > ch.pageNumber;
                const pageLabel = isCross
                  ? t('admin.chunkInspector.stream.pdfPageRange', {
                      start: ch.pageNumber,
                      end: ch.endPageNumber,
                    })
                  : t('admin.chunkInspector.stream.pdfPageSingle', {
                      page: ch.pageNumber,
                    });
                const printedLabel = ch.contentPageNumber
                  ? ch.endContentPageNumber && ch.endContentPageNumber !== ch.contentPageNumber
                    ? t('admin.chunkInspector.stream.printedPageRange', {
                        start: ch.contentPageNumber,
                        end: ch.endContentPageNumber,
                      })
                    : t('admin.chunkInspector.stream.printedPageSingle', {
                        page: ch.contentPageNumber,
                      })
                  : null;

                const hasSim = ch.similarity !== null && ch.similarity !== undefined;
                const passesRag = hasSim && (ch.similarity ?? 0) >= ragThreshold;
                const { overlap, body, footnotes } = splitChunkBodyAndFootnotes(
                  ch.text,
                  ch.overlapPrefix
                );

                return (
                  <article
                    key={ch.id}
                    onClick={() => setSelectedChunkId(ch.id)}
                    className={`glass-panel bg-white/90 dark:bg-slate-900/90 border rounded-2xl p-4 space-y-2.5 transition cursor-pointer ${
                      isSelected
                        ? 'border-[#0369a1] dark:border-[#38bdf8] ring-1 ring-[#0369a1] dark:ring-[#38bdf8]'
                        : 'border-slate-200 dark:border-slate-800 hover:border-slate-400 dark:hover:border-slate-600'
                    } ${hasSim && !passesRag ? 'opacity-75' : ''}`}
                  >
                    {/* Card Header */}
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono font-semibold px-2 py-0.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200">
                          #{ch.chunkIndex}
                        </span>
                        <span
                          className={`px-2 py-0.5 rounded-lg border font-mono ${
                            isCross
                              ? 'border-[#0369a1] dark:border-[#38bdf8] text-[#0369a1] dark:text-[#38bdf8] font-semibold'
                              : 'border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200'
                          }`}
                        >
                          {pageLabel}
                        </span>
                        {printedLabel && (
                          <span className="text-slate-500 dark:text-slate-400 font-mono">
                            ({printedLabel})
                          </span>
                        )}
                        {isCross && (
                          <span className="px-2 py-0.5 rounded-full bg-[#0369a1]/10 dark:bg-[#38bdf8]/15 text-[#0369a1] dark:text-[#38bdf8] inline-flex items-center gap-1">
                            <Link2 size={11} />
                            <span>{t('admin.chunkInspector.stream.crossPageBadge')}</span>
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        {ch.rerankRank !== null && ch.rerankRank !== undefined && (
                          <span className="px-2 py-0.5 rounded-lg font-mono font-semibold border border-indigo-500/50 text-indigo-700 dark:text-indigo-300 bg-indigo-500/10">
                            {t('admin.chunkInspector.stream.rerankRankBadge', {
                              rank: ch.rerankRank,
                            })}
                          </span>
                        )}
                        {ch.rerankDropped && (
                          <span className="px-2 py-0.5 rounded-lg font-mono border border-slate-300 dark:border-slate-700 text-slate-500 dark:text-slate-400 bg-slate-100/70 dark:bg-slate-800/70">
                            {t('admin.chunkInspector.stream.rerankDroppedBadge')}
                          </span>
                        )}
                        {hasSim && (
                          <span
                            className={`px-2 py-0.5 rounded-lg font-mono font-semibold border ${
                              passesRag
                                ? 'border-emerald-500/50 text-emerald-600 dark:text-emerald-400 bg-emerald-500/5'
                                : 'border-amber-500/50 text-amber-600 dark:text-amber-400 bg-amber-500/5'
                            }`}
                          >
                            {(ch.similarity ?? 0).toFixed(2)} ·{' '}
                            {passesRag
                              ? t('admin.chunkInspector.stream.ragPass')
                              : t('admin.chunkInspector.stream.ragBelowThreshold')}
                          </span>
                        )}
                        <span
                          className={`px-2 py-0.5 rounded-lg border font-mono tabular-nums ${
                            ch.charCount < 350 || ch.charCount > 2500
                              ? 'text-amber-600 dark:text-amber-400 border-amber-400/50'
                              : 'text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700'
                          }`}
                        >
                          {t('admin.chunkInspector.stream.charCount', { count: ch.charCount })}
                        </span>
                        <span
                          className={`inline-flex items-center gap-1 ${
                            ch.hasEmbedding
                              ? 'text-emerald-600 dark:text-emerald-400'
                              : 'text-amber-600 dark:text-amber-400'
                          }`}
                        >
                          ●{' '}
                          {ch.hasEmbedding
                            ? t('admin.chunkInspector.stream.hasEmbedding')
                            : t('admin.chunkInspector.stream.missingEmbedding')}
                        </span>
                      </div>
                    </div>

                    {/* Contextual Embedding Prefix */}
                    {showPrefix && ch.embeddingPrefix && (
                      <div className="rounded-xl bg-slate-50 dark:bg-slate-950/60 border border-dashed border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs">
                        <span className="text-slate-500 dark:text-slate-400">
                          {t('admin.chunkInspector.stream.embeddingPrefixHint')}
                        </span>
                        <div className="font-semibold text-[#0369a1] dark:text-[#38bdf8] mt-0.5">
                          {ch.embeddingPrefix}
                        </div>
                      </div>
                    )}

                    {/* Stored Chunk.text */}
                    <div className="text-sm leading-8 whitespace-pre-line break-words text-slate-900 dark:text-slate-100 pt-0.5">
                      {overlap &&
                        (showOverlap ? (
                          <>
                            <span
                              title={t('admin.chunkInspector.stream.overlapTooltip')}
                              className="bg-amber-500/15 dark:bg-amber-400/15 border-b border-dashed border-amber-500 rounded px-1"
                            >
                              {highlightQueryMatches(overlap, appliedQuery, appliedMode)}
                            </span>
                            {body ? '\n\n' : ''}
                          </>
                        ) : (
                          <>
                            {highlightQueryMatches(overlap, appliedQuery, appliedMode)}
                            {body ? '\n\n' : ''}
                          </>
                        ))}
                      {highlightQueryMatches(body, appliedQuery, appliedMode)}
                      {footnotes.map((fn, idx) => (
                        <span
                          key={idx}
                          className="block mt-2 text-xs leading-6 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 border-s-2 border-[#0369a1] dark:border-[#38bdf8] rounded-md px-2.5 py-1.5 text-slate-700 dark:text-slate-300"
                        >
                          {highlightQueryMatches(fn, appliedQuery, appliedMode)}
                        </span>
                      ))}
                    </div>

                    {/* Card Footer */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 dark:border-slate-800 text-xs text-slate-400">
                      <span className="font-mono truncate min-w-0">
                        chunk_id={ch.id}
                        {ch.textHash ? ` · hash=${ch.textHash.slice(0, 8)}…` : ''}
                      </span>

                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCopy(`chunk-${ch.id}`, ch.text);
                          }}
                          className="inline-flex items-center gap-1 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer"
                        >
                          {copiedId === `chunk-${ch.id}` ? (
                            <Check size={12} className="text-emerald-500" />
                          ) : (
                            <Copy size={12} />
                          )}
                          <span>{t('admin.chunkInspector.stream.copy')}</span>
                        </button>

                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenPageInReader(ch.pageNumber);
                          }}
                          className="inline-flex items-center gap-1 text-[#0369a1] dark:text-[#38bdf8] hover:underline cursor-pointer font-medium"
                        >
                          <span>
                            {t('admin.chunkInspector.stream.openInReader', {
                              page: ch.pageNumber,
                            })}
                          </span>
                          <ExternalLink size={12} />
                        </button>
                      </div>
                    </div>
                  </article>
                );
              })
            )}

            {data && chunks.length < data.totalMatching && (
              <div className="pt-2 flex justify-center">
                <button
                  type="button"
                  disabled={isLoadingMore}
                  onClick={() => fetchChunks(chunks.length, true)}
                  className="px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-[#0369a1] dark:hover:border-[#38bdf8] text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-2 cursor-pointer disabled:opacity-50"
                >
                  {isLoadingMore && <Loader2 size={14} className="animate-spin" />}
                  <span>
                    {t('admin.chunkInspector.stream.loadMore', {
                      shown: chunks.length,
                      total: data.totalMatching,
                    })}
                  </span>
                </button>
              </div>
            )}
          </div>
        </section>

        {/* PANE 3: Source pages.text Compare */}
        {showSourcePane && (
          <aside className="ci-area-source glass-panel bg-white/85 dark:bg-slate-900/85 border border-[#0369a1]/15 dark:border-[#38bdf8]/15 rounded-2xl overflow-clip shadow-sm">
            <div className="px-3.5 py-2.5 border-b border-slate-200/70 dark:border-slate-800 flex items-center justify-between gap-2">
              <h2 className="text-xs font-bold text-slate-800 dark:text-slate-100 flex items-center gap-1.5">
                <FileText size={14} className="text-[#0369a1] dark:text-[#38bdf8]" />
                <span>{t('admin.chunkInspector.source.title')}</span>
              </h2>
              <span className="text-xs font-mono text-slate-500 dark:text-slate-400">
                {selectedChunk
                  ? selectedChunk.endPageNumber > selectedChunk.pageNumber
                    ? t('admin.chunkInspector.source.pageRange', {
                        start: selectedChunk.pageNumber,
                        end: selectedChunk.endPageNumber,
                      })
                    : t('admin.chunkInspector.source.pageSingle', {
                        page: selectedChunk.pageNumber,
                      })
                  : ''}
              </span>
            </div>

            <div className="ci-pane-scroll p-3.5 space-y-3 text-xs leading-relaxed">
              {isLoadingSource ? (
                <div className="py-8 flex items-center justify-center gap-2 text-slate-400">
                  <Loader2 size={15} className="animate-spin" />
                  <span>{t('admin.chunkInspector.source.loading')}</span>
                </div>
              ) : !selectedChunk ? (
                <div className="py-8 text-center text-slate-400">
                  {t('admin.chunkInspector.source.selectPrompt')}
                </div>
              ) : (
                sourcePages.map((pg, idx) => {
                  const parsedLines = classifySourcePageLines(pg.text);
                  return (
                    <React.Fragment key={pg.pageNumber}>
                      {idx > 0 && (
                        <div className="text-center text-xs text-[#0369a1] dark:text-[#38bdf8] py-1 border-y border-dashed border-slate-200 dark:border-slate-700">
                          {t('admin.chunkInspector.source.stitchBoundary', {
                            prev: pg.pageNumber - 1,
                            next: pg.pageNumber,
                          })}
                        </div>
                      )}
                      <div className="space-y-2">
                        <div className="flex items-center justify-between text-xs font-mono text-slate-500 dark:text-slate-400">
                          <span>
                            {t('admin.chunkInspector.stream.pdfPageSingle', {
                              page: pg.pageNumber,
                            })}
                          </span>
                          <span>
                            {pg.contentPageNumber
                              ? t('admin.chunkInspector.stream.printedPageSingle', {
                                  page: pg.contentPageNumber,
                                })
                              : t('admin.chunkInspector.source.frontMatter')}
                          </span>
                        </div>
                        <div className="rounded-xl bg-slate-50/90 dark:bg-slate-950/60 border border-slate-200/80 dark:border-slate-800 p-3 space-y-2 text-slate-800 dark:text-slate-200">
                          {parsedLines.length === 0 ? (
                            <div className="text-slate-400 italic">
                              {t('admin.chunkInspector.source.emptyPage')}
                            </div>
                          ) : (
                            parsedLines.map((ln, lIdx) => {
                              if (ln.kind === 'noise') {
                                return (
                                  <div
                                    key={lIdx}
                                    className="font-mono text-xs text-slate-400 flex items-center justify-between gap-2"
                                  >
                                    <span className="line-through opacity-65 truncate">
                                      {ln.text}
                                    </span>
                                    <span className="shrink-0 opacity-75">
                                      {t('admin.chunkInspector.source.cleanedNoiseTag')}
                                    </span>
                                  </div>
                                );
                              }
                              if (ln.kind === 'heading') {
                                return (
                                  <div
                                    key={lIdx}
                                    className="font-bold text-[#0369a1] dark:text-[#38bdf8]"
                                  >
                                    {ln.text}
                                  </div>
                                );
                              }
                              if (ln.kind === 'footnote') {
                                return (
                                  <div
                                    key={lIdx}
                                    className="bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 border-s-2 border-[#0369a1] dark:border-[#38bdf8] rounded px-2 py-1 text-xs"
                                  >
                                    {ln.text}
                                  </div>
                                );
                              }
                              return (
                                <div key={lIdx} className="whitespace-pre-line leading-7">
                                  {ln.text}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>
                    </React.Fragment>
                  );
                })
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};

export default ChunkInspectorView;
