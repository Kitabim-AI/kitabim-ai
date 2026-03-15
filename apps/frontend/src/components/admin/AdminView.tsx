import React, { useState, useEffect, useRef } from 'react';
import { Database, Book as BookIcon, User, Hash, BookOpen, MoreVertical, Save, X, Edit2, Check, Globe, Shield, Wand2, Search, WholeWord, FileText, ScanText, RefreshCw, BookOpenCheck, Cuboid, Scissors } from 'lucide-react';
import { authFetch } from '../../services/authService';
import { Pagination } from '../common/Pagination';

import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';
import { TagEditor } from './TagEditor';
import { ProgressBar } from './ProgressBar';
import { ActionMenu } from './ActionMenu';
import { ProverbDisplay } from '../common/ProverbDisplay';

const getStatusTextColor = (step: string | null) => {
  if (!step) return 'text-slate-400';
  switch (step.toLowerCase()) {
    case 'ready': return 'text-emerald-600 font-bold';
    case 'embedding': return 'text-orange-600 font-bold';
    case 'chunking': return 'text-indigo-600 font-bold';
    case 'ocr': return 'text-blue-600 font-bold';
    case 'error': return 'text-red-500 font-bold';
    default: return 'text-slate-400';
  }
};

const getStat = (stats: any, key: string): number => {
  if (!stats) return 0;
  if (typeof stats[key] === 'number') return stats[key];
  // Convert snake_case to camelCase (e.g., spell_check_active -> spellCheckActive)
  const camelKey = key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
  if (typeof stats[camelKey] === 'number') return stats[camelKey];
  return 0;
};

const getPipelineIconClass = (
  book: any,
  stepKey: string,
  isCompleteParam: boolean,
  isFailedParam: boolean
) => {
  const doneCount = getStat(book.pipelineStats, stepKey);
  const activeCount = getStat(book.pipelineStats, `${stepKey}_active`);
  const failedCount = getStat(book.pipelineStats, `${stepKey}_failed`);
  const total = book.totalPages || 0;

  // For page-level steps, use the aggregate counts to determine if finished
  const isPageLevel = ['ocr', 'chunking', 'embedding', 'word_index', 'spell_check'].includes(stepKey);

  // Special case: Summary is determined by hasSummary flag
  const isComplete = stepKey === 'summary'
    ? !!book.hasSummary
    : isPageLevel
      ? (total > 0 && doneCount + failedCount === total)
      : isCompleteParam;

  const isFailed = isPageLevel
    ? failedCount > 0
    : isFailedParam;

  // A step is considered "In Progress" (orange/blinking) if:
  // 1. It's not complete AND
  // 2. It has either started (doneCount > 0) or is currently being worked on (activeCount > 0)
  const isInProgress = !isComplete && (
    doneCount > 0 ||
    activeCount > 0
  );

  // Order matters: In Progress (blinking) takes precedence over a partial error
  // so the user sees it's still moving even if some pages failed.
  if (isInProgress) return 'text-[#FF9800] animate-pulse drop-shadow-[0_0_8px_rgba(255,152,0,0.4)]';
  if (isFailed) return 'text-red-500';
  if (isComplete) return 'text-emerald-500';
  return 'text-slate-300';
};

const getMilestoneColor = (book: any, stepKey: string) => {
  // Map step key to milestone field
  const milestoneFieldMap: Record<string, string> = {
    'ocr': 'ocrMilestone',
    'chunking': 'chunkingMilestone',
    'embedding': 'embeddingMilestone',
    'word_index': 'wordIndexMilestone',
    'spell_check': 'spellCheckMilestone',
    'summary': 'hasSummary', // Special case
  };

  const milestoneField = milestoneFieldMap[stepKey];
  if (!milestoneField) return 'text-slate-300';

  // Special case for summary: use boolean flag
  if (stepKey === 'summary') {
    return book.hasSummary ? 'text-emerald-500' : 'text-slate-300';
  }

  const milestone = book[milestoneField];

  switch (milestone) {
    case 'complete':
      return 'text-emerald-500';
    case 'partial_failure':
      return 'text-yellow-500'; // Yellow for partial failures
    case 'failed':
      return 'text-red-500';
    case 'in_progress':
      return 'text-[#FF9800] animate-pulse drop-shadow-[0_0_8px_rgba(255,152,0,0.4)]';
    case 'idle':
    default:
      return 'text-slate-300';
  }
};

const isBookReadable = (book: any): boolean => {
  // A book is readable if OCR has started (not idle) or if status is ready
  // This replaces the old check: !book.pipelineStep && book.status === 'pending'
  return book.status === 'ready' ||
         book.ocrMilestone !== 'idle' ||
         (book.status !== 'pending');
};

export const AdminView: React.FC = () => {
  const [spellCheckEnabled, setSpellCheckEnabled] = React.useState(true);
  const {
    books,
    totalBooks,
    bookActions,
    loaderRef,
    isLoadingMoreShelf: isLoadingMore,
    hasMoreShelf: hasMore,
    loadMoreShelf: loadMore,
    isLoading: isInitialLoading,
    searchQuery
  } = useAppContext();
  const { t } = useI18n();

  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [menuAnchorRect, setMenuAnchorRect] = useState<DOMRect | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isInitialLoading && hasMore && !isLoadingMore) {
          loadMore();
        }
      },
      { threshold: 0.1, rootMargin: '1200px' }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, loadMore, loaderRef, isInitialLoading]);

  // Row editing state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<{
    title: string;
    author: string;
    volume: string;
    categories: string[];
    tempCategory: string;
  } | null>(null);

  // Lazy loading stats state (cached on hover for performance)
  // Cache key: `${bookId}:${step}` for per-step caching
  const [detailedStats, setDetailedStats] = useState<Record<string, any>>({});
  const [loadingStats, setLoadingStats] = useState<Record<string, boolean>>({});

  const fetchBookStats = async (bookId: string, step: string) => {
    const cacheKey = `${bookId}:${step}`;

    // Skip if already loaded or currently loading
    if (detailedStats[cacheKey] || loadingStats[cacheKey]) return;

    setLoadingStats(prev => ({ ...prev, [cacheKey]: true }));
    try {
      const res = await authFetch(`/api/books/${bookId}/pipeline-stats?step=${step}`);
      if (res.ok) {
        const data = await res.json();
        setDetailedStats(prev => ({ ...prev, [cacheKey]: data }));
      }
    } catch (err) {
      console.error('Failed to fetch book stats:', err);
    } finally {
      setLoadingStats(prev => ({ ...prev, [cacheKey]: false }));
    }
  };
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setActiveMenuId(null);
        setMenuAnchorRect(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    
    // Fetch system configurations
    const fetchConfigs = async () => {
      try {
        const res = await authFetch('/api/system-configs/spell_check_enabled');
        if (res.ok) {
          const data = await res.json();
          setSpellCheckEnabled(data.value === 'true');
        }
      } catch (err) {
        console.error('Failed to fetch spell check config:', err);
      }
    };
    fetchConfigs();

    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleEditRow = (book: any) => {
    setEditingId(book.id);
    setEditData({
      title: book.title || '',
      author: book.author || '',
      volume: book.volume?.toString() || '',
      categories: book.categories || [],
      tempCategory: ''
    });
  };

  const handleSaveRow = async (id: string | null) => {
    if (!id || !editData) return;

    const volumeValue = editData.volume.toString().trim();
    let volume: number | null = null;
    if (volumeValue.length > 0) {
      volume = parseInt(volumeValue, 10);
      if (isNaN(volume)) volume = null;
    }

    // Capture the latest temp category and existing categories
    const currentTemp = editData.tempCategory.trim();
    const currentCategories = [...editData.categories];

    // Add pending category if there's text in the input and it's not already added
    if (currentTemp && !currentCategories.includes(currentTemp)) {
      currentCategories.push(currentTemp);
    }

    const success = await bookActions.handleSaveBookRow(id, {
      title: editData.title.trim(),
      author: editData.author.trim(),
      volume,
      categories: currentCategories
    });

    if (success) {
      setEditingId(null);
      setEditData(null);
    }
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    setEditData(null);
  };

  return (
    <div className="space-y-8 animate-fade-in" lang="ug">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-3 md:gap-4 group">
          <div className="self-start mt-1 p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 icon-shake">
            <BookIcon size={20} className="md:w-6 md:h-6" />
          </div>
          <div>
            <h2 className="text-xl md:text-2xl lg:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.table.managementSystem')}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-6 md:w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <ProverbDisplay
                keywords={t('proverbs.admin')}
                size="sm"
                className="opacity-70 mt-[-2px]"
                defaultText={t('admin.table.manageBooks')}
              />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 md:gap-3 px-4 md:px-6 py-2 md:py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl border border-[#0369a1]/10 shadow-inner w-fit">
          <BookOpen size={16} strokeWidth={2.5} className="md:w-[18px] md:h-[18px]" />
          <span className="text-xs md:text-sm font-normal uppercase">
            {isInitialLoading ? <RefreshCw size={14} className="animate-spin inline-block" /> : t('chat.libraryBookCount', { count: totalBooks })}
          </span>
        </div>
      </div>



      {(bookActions.isCheckingGlobal || (isInitialLoading && books.length === 0)) && (
        <div className="p-20 flex flex-col items-center justify-center text-center z-50">
          <Database className="w-16 h-16 text-[#0369a1] mb-6 animate-bounce" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
        </div>
      )}

      {(!bookActions.isCheckingGlobal && !isInitialLoading && books.length === 0) && (
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
          <Database className="w-16 h-16 text-[#94a3b8] mb-6" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t(searchQuery ? 'admin.table.noResults' : 'admin.table.noBooks')}</h3>
          <p className="text-slate-500 font-normal">{t(searchQuery ? 'admin.table.tryDifferent' : 'admin.table.uploadFirst')}</p>
        </div>
      )}

      {!bookActions.isCheckingGlobal && books.length > 0 && (
        <div className="glass-panel overflow-hidden rounded-[16px] md:rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-right lg:min-w-[900px]" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] uppercase">
                  <th className="px-3 md:px-6 py-3 md:py-5 text-right font-normal">{t('admin.table.bookName')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 w-20 md:w-28 text-right font-normal">{t('book.volumeLabel') || t('admin.table.pageCount')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 w-40 md:w-52 text-right font-normal">{t('admin.table.author')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 w-40 md:w-52 text-right font-normal">{t('admin.table.category')}</th>
                  <th className="hidden md:table-cell px-3 md:px-6 py-3 md:py-5 text-right font-normal">{t('admin.table.progress')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 text-left font-normal">{t('admin.table.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5">
                {books.map(book => {
                  const isEditing = editingId === book.id;
                  return (
                    <tr key={book.id} className={`hover:bg-[#e8f4f8]/20 transition-colors group/row ${isEditing ? 'bg-[#0369a1]/5' : ''}`}>
                      <td className={`px-3 md:px-6 py-4 md:py-6 font-uyghur ${isEditing ? 'align-top' : ''}`}>
                        <div className="flex items-center gap-2 md:gap-4">
                          <button
                            onClick={() => bookActions.openReader(book)}
                            disabled={!isBookReadable(book) || isEditing}
                            className={`p-2 md:p-3 rounded-xl transition-all shadow-sm active:scale-90 ${!isBookReadable(book) || isEditing
                              ? 'bg-slate-100 text-slate-300 cursor-not-allowed'
                              : 'bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white group-hover/row:scale-110'
                              }`}
                            title={t('admin.table.view')}
                          >
                            <BookOpen size={18} strokeWidth={2.5} className="md:w-5 md:h-5" />
                          </button>
                          {isEditing ? (
                            <div className="flex-1 min-w-[200px]">
                              <input
                                autoFocus
                                type="text"
                                value={editData?.title}
                                onChange={e => setEditData(prev => prev ? { ...prev, title: e.target.value } : null)}
                                onKeyDown={e => e.key === 'Enter' && handleSaveRow(book.id)}
                                className="px-3 md:px-4 py-1.5 md:py-2 text-[14px] md:text-[16px] border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none focus:ring-4 focus:ring-[#0369a1]/10 transition-all font-black"
                                placeholder={t('admin.table.bookName')}
                              />
                            </div>
                          ) : (
                            <button
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                if (!isBookReadable(book) && !isEditing) return;
                                bookActions.openReader(book);
                              }}
                              className={`text-right group/title transition-all duration-300 block ${isBookReadable(book) && !isEditing ? 'cursor-pointer hover:translate-x-[-4px]' : 'cursor-default'}`}
                              disabled={!isBookReadable(book) || isEditing}
                            >
                              <span className={`font-black text-[14px] md:text-[16px] lg:text-[18px] transition-colors block ${isBookReadable(book) && !isEditing ? 'text-[#1a1a1a] group-hover/title:text-[#0369a1]' : 'text-slate-400'}`}>
                                {book.title}
                                {book.volume !== null && (
                                  <span className="lg:hidden text-[#0369a1] mr-2">
                                    {' '}{t('book.volume', { volume: book.volume })}
                                  </span>
                                )}
                              </span>
                              <div className="text-[10px] md:text-[12px] font-bold text-slate-400 mt-0.5">{t('book.pagesCount', { count: book.totalPages || 0 })}</div>
                              
                              {/* Mobile Pipeline Progress */}
                              <div className="flex md:hidden items-center gap-1.5 mt-2 opacity-80">
                                <ScanText size={14} className={getMilestoneColor(book, 'ocr')} />
                                <Scissors size={14} className={getMilestoneColor(book, 'chunking')} />
                                <Cuboid size={14} className={getMilestoneColor(book, 'embedding')} />
                                <Wand2 size={14} className={getMilestoneColor(book, 'summary')} />
                                <WholeWord size={14} className={getMilestoneColor(book, 'word_index')} />
                                <BookOpenCheck size={14} className={getMilestoneColor(book, 'spell_check')} />
                              </div>
                            </button>
                          )}
                        </div>
                      </td>
                      <td className={`hidden lg:table-cell px-3 md:px-6 py-4 md:py-6 text-center ${isEditing ? 'align-top' : ''}`}>
                        {isEditing ? (
                          <input
                            type="number"
                            value={editData?.volume}
                            onChange={e => setEditData(prev => prev ? { ...prev, volume: e.target.value } : null)}
                            onKeyDown={e => e.key === 'Enter' && handleSaveRow(book.id)}
                            className="no-spinner px-2 md:px-3 py-1.5 md:py-2 border-2 border-[#0369a1] rounded-xl bg-white w-16 md:w-20 outline-none text-center font-black text-sm md:text-base"
                          />
                        ) : (
                          <div className="p-1 md:p-2 text-[14px] md:text-[16px] font-black text-[#1a1a1a]">
                            {book.volume !== null ? t('book.volume', { volume: book.volume }) : <Hash size={12} className="mx-auto text-slate-200 md:w-[14px] md:h-[14px]" />}
                          </div>
                        )}
                      </td>
                      <td className={`hidden lg:table-cell px-3 md:px-6 py-4 md:py-6 ${isEditing ? 'align-top' : ''}`}>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editData?.author}
                            onChange={e => setEditData(prev => prev ? { ...prev, author: e.target.value } : null)}
                            onKeyDown={e => e.key === 'Enter' && handleSaveRow(book.id)}
                            className="px-3 md:px-4 py-1.5 md:py-2 text-[14px] md:text-[16px] border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none font-normal"
                            placeholder={t('admin.table.author')}
                          />
                        ) : (
                          <div className="p-1 md:p-2 text-[14px] md:text-[16px] font-normal text-[#1a1a1a]">
                            {book.author || <User size={12} className="text-slate-200 md:w-[14px] md:h-[14px]" />}
                          </div>
                        )}
                      </td>
                      <td className={`hidden lg:table-cell px-3 md:px-6 py-4 md:py-6 ${isEditing ? 'align-top' : ''}`}>
                        <TagEditor
                          isOpen={isEditing}
                          onSave={() => handleSaveRow(book.id)}
                          items={editData?.categories || []}
                          tempValue={editData?.tempCategory || ''}
                          onTempValueChange={(val) => setEditData(prev => prev ? { ...prev, tempCategory: val } : null)}
                          onAddItem={(val) => {
                            if (editData && val && !editData.categories.includes(val)) {
                              setEditData(prev => prev ? { ...prev, categories: [...prev.categories, val], tempCategory: '' } : null);
                            }
                          }}
                          onRemoveItem={(idx) => setEditData(prev => prev ? { ...prev, categories: prev.categories.filter((_, i) => i !== idx) } : null)}
                          onClose={handleCancelEdit}
                          existingItems={book.categories || []}
                          placeholder={t('admin.categories.add')}
                          hideActions={true}
                        />
                      </td>
                      <td className={`hidden md:table-cell px-3 md:px-6 py-4 md:py-6 ${isEditing ? 'align-top' : ''}`}>
                        <div className="flex flex-col gap-1.5 min-w-[120px] md:min-w-[150px]">
                          <div className="flex items-center gap-2.5">
                            {/* Baseline Pipeline Icons with Lazy Loading Tooltips */}
                            {[
                              { key: 'ocr', icon: ScanText, label: 'admin.pipeline.ocr' },
                              { key: 'chunking', icon: Scissors, label: 'admin.pipeline.chunking' },
                              { key: 'embedding', icon: Cuboid, label: 'admin.pipeline.embedding' },
                              { key: 'summary', icon: Wand2, label: 'admin.pipeline.summary' },
                              { key: 'word_index', icon: WholeWord, label: 'admin.pipeline.wordIndex' },
                              { key: 'spell_check', icon: BookOpenCheck, label: 'admin.pipeline.spellCheck' }
                            ].map(({ key, icon: Icon, label }) => {
                              const cacheKey = `${book.id}:${key}`;
                              const stats = detailedStats[cacheKey];
                              const isLoading = loadingStats[cacheKey];
                              const isLoaded = !!stats;

                              const colorClass = isLoaded
                                ? getPipelineIconClass(
                                    { ...book, pipelineStats: stats.pipeline_stats, hasSummary: stats.has_summary, totalPages: stats.total_pages },
                                    key,
                                    false, // handled inside getPipelineIconClass for page levels
                                    false  // handled inside getPipelineIconClass for page levels
                                  )
                                : getMilestoneColor(book, key);

                              return (
                                <div
                                  key={key}
                                  className="group/status relative flex items-center"
                                  onMouseEnter={() => fetchBookStats(book.id, key)}
                                >
                                  <Icon size={18} className={`${colorClass} transition-colors duration-300`} />
                                  <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-2.5 py-1.5 bg-slate-900/95 text-white text-[11px] font-medium rounded-md shadow-lg opacity-0 group-hover/status:opacity-100 transition-all duration-200 whitespace-nowrap pointer-events-none z-10 border border-slate-700">
                                    <div className="flex flex-col gap-0.5">
                                      <span className="font-bold border-b border-slate-700 pb-0.5 mb-0.5">{t(label)}</span>
                                      {isLoading ? (
                                        <span className="text-slate-400 animate-pulse">{t('common.loading')}...</span>
                                      ) : isLoaded ? (
                                        <>
                                          {key === 'summary' ? (
                                            <span>{stats.has_summary ? t('common.done') : t('common.pending')}</span>
                                          ) : (
                                            <span>
                                              {getStat(stats.pipeline_stats, key)}/{stats.total_pages}
                                              {getStat(stats.pipeline_stats, `${key}_failed`) > 0 && (
                                                <span className="text-red-400 ml-1">
                                                  ({getStat(stats.pipeline_stats, `${key}_failed`)} {t('common.error')})
                                                </span>
                                              )}
                                            </span>
                                          )}
                                        </>
                                      ) : null}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </td>
                      <td className={`px-3 md:px-6 py-4 md:py-6 text-left ${isEditing ? 'align-top' : ''}`}>
                        <div className="flex items-center justify-end gap-1 md:gap-2">
                          {isEditing ? (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleSaveRow(book.id)}
                                className="p-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/10"
                                title={t('common.save')}
                              >
                                <Save size={18} />
                              </button>
                              <button
                                onClick={handleCancelEdit}
                                className="p-2 bg-slate-100 text-slate-400 rounded-xl hover:bg-slate-200 active:scale-90 transition-all"
                                title={t('common.cancel')}
                              >
                                <X size={20} />
                              </button>
                            </div>
                          ) : (
                            <div className="hidden md:flex items-center gap-2">
                              <button
                                onClick={() => handleEditRow(book)}
                                className="p-2 bg-[#0369a1]/10 text-[#0369a1] rounded-xl hover:bg-[#0369a1] hover:text-white transition-all"
                                title={t('common.edit')}
                              >
                                <Edit2 size={18} />
                              </button>
                              <button
                                onClick={() => bookActions.handleToggleVisibility(book.id, book.visibility || 'public')}
                                className={`p-2 rounded-xl transition-all ${book.visibility === 'private'
                                  ? 'bg-slate-100 text-slate-400 hover:bg-slate-200'
                                  : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-500 hover:text-white'
                                  }`}
                                title={book.visibility === 'private' ? t('admin.table.makePublic') : t('admin.table.makePrivate')}
                              >
                                {book.visibility === 'private' ? <Shield size={18} /> : <Globe size={18} />}
                              </button>
                            </div>
                          )}
                          <div className="relative">
                            <button
                              onMouseDown={(e) => e.stopPropagation()}
                              onClick={(e) => {
                                if (activeMenuId === book.id) {
                                  setActiveMenuId(null);
                                  setMenuAnchorRect(null);
                                } else {
                                  setActiveMenuId(book.id);
                                  setMenuAnchorRect(e.currentTarget.getBoundingClientRect());
                                }
                              }}
                              className={`p-2 hover:bg-[#0369a1]/10 rounded-xl transition-all ${activeMenuId === book.id ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-slate-400'}`}
                            >
                              <MoreVertical size={20} />
                            </button>
                            {activeMenuId === book.id && menuAnchorRect && (
                              <ActionMenu 
                                book={book} 
                                close={() => { setActiveMenuId(null); setMenuAnchorRect(null); }} 
                                anchorRect={menuAnchorRect} 
                                menuRef={menuRef}
                                spellCheckEnabled={spellCheckEnabled}
                              />
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div ref={loaderRef as any} className="bg-[#0369a1]/5 px-6 py-8 flex flex-col items-center justify-center gap-4">
            {isLoadingMore ? (
              <div className="flex flex-col items-center gap-3 animate-fade-in">
                <div className="w-8 h-8 border-3 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                <span className="text-[10px] font-black text-[#0369a1] uppercase animate-pulse">{t('common.loadingMore')}</span>
              </div>
            ) : !hasMore && books.length > 0 && (
              <div className="flex flex-col items-center gap-3 opacity-30">
                <div className="w-12 h-[1px] bg-[#94a3b8]" />
                <p className="text-[10px] font-black text-[#94a3b8] uppercase">{t('common.endOfList')}</p>
                <div className="w-12 h-[2px] bg-[#94a3b8]" />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
