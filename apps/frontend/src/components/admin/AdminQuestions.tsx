/**
 * Admin Questions Panel — shows all RAG questions with a home-page visibility toggle.
 */

import { AlertCircle, BookOpen, Globe, Loader, MessageSquare, RefreshCw, Search, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { authFetch } from '../../services/authService';

const PAGE_SIZE = 25;

interface RagQuestion {
  id: number;
  question: string;
  isGlobal: boolean;
  bookId: string | null;
  bookTitle?: string | null;
  userId: string | null;
  userDisplayName: string | null;
  isFirstTurn: boolean;
  showOnHomepage: boolean;
  userFeedback: string | null;
  ts: string;
  evalStatus: string;
  faithfulnessScore: number | null;
  answerRelevanceScore: number | null;
  contextPrecisionScore: number | null;
}

interface QuestionsPage {
  items: RagQuestion[];
  total: number;
  offset: number;
  limit: number;
}

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function AdminQuestions() {
  const { t } = useI18n();
  const [questions, setQuestions] = useState<RagQuestion[]>([]);
  const [total, setTotal] = useState(0);
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  const [searchQuery, setSearchQuery] = useState('');
  const [localSearch, setLocalSearch] = useState('');

  const offsetRef = useRef(0);
  const hasMore = questions.length < total;
  const loaderRef = useRef<HTMLDivElement | null>(null);

  const inputRef = useCallback((node: HTMLInputElement | null) => {
    if (node) {
      node.focus();
    }
  }, []);

  const fetchPage = useCallback(async (offset: number, append: boolean, query: string) => {
    try {
      const queryParam = query ? `&query=${encodeURIComponent(query)}` : '';
      const res = await authFetch(
        `/api/questions/admin/questions?limit=${PAGE_SIZE}&offset=${offset}${queryParam}`
      );
      if (!res.ok) throw new Error('Failed to fetch questions');
      const data: QuestionsPage = await res.json();
      setTotal(data.total);
      setQuestions((prev) => (append ? [...prev, ...data.items] : data.items));
      offsetRef.current = offset + data.items.length;
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.questions.error'));
    }
  }, [t]);

  // Debounce search query changes
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localSearch !== searchQuery) {
        setSearchQuery(localSearch);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [localSearch, searchQuery]);

  // Reload when searchQuery changes
  useEffect(() => {
    setIsInitialLoading(true);
    fetchPage(0, false, searchQuery).finally(() => setIsInitialLoading(false));
  }, [fetchPage, searchQuery]);

  // Infinite scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (
          entries[0].isIntersecting &&
          !isInitialLoading &&
          hasMore &&
          !isLoadingMore
        ) {
          setIsLoadingMore(true);
          fetchPage(offsetRef.current, true, searchQuery).finally(() =>
            setIsLoadingMore(false)
          );
        }
      },
      { threshold: 0.1, rootMargin: '1200px' }
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoadingMore, isInitialLoading, fetchPage, searchQuery]);

  const handleToggle = async (question: RagQuestion) => {
    setTogglingId(question.id);
    try {
      const res = await authFetch(
        `/api/questions/admin/questions/${question.id}/featured`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ showOnHomepage: !question.showOnHomepage }),
        }
      );
      if (!res.ok) throw new Error('Toggle failed');
      const updated = await res.json();
      setQuestions((prev) =>
        prev.map((q) =>
          q.id === question.id
            ? { ...q, showOnHomepage: updated.showOnHomepage ?? updated.show_on_homepage }
            : q
        )
      );
    } catch {
      // silent — the toggle visually snaps back since we didn't optimistically update
    } finally {
      setTogglingId(null);
    }
  };

  if (isInitialLoading && questions.length === 0) {
    return (
      <div className="p-20 flex flex-col items-center justify-center text-center z-50">
        <MessageSquare className="w-16 h-16 text-[#0369a1] dark:text-[#38bdf8] mb-6 animate-bounce" />
        <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('common.loading')}</h3>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-20 flex flex-col items-center justify-center text-center shadow-xl rounded-[24px]">
        <AlertCircle className="w-16 h-16 text-red-500 mb-6" />
        <h3 className="text-xl font-normal text-red-500">{t('admin.questions.error')}</h3>
        <p className="text-slate-500 dark:text-slate-400 font-normal mt-2">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Search and Filters Bar */}
      <div className="flex flex-col-reverse md:flex-row gap-3 md:gap-4">
        {/* Search input box on the right */}
        <div className="relative flex-1 lg:flex-none lg:w-[30%] group">
          <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors">
            {isLoadingMore && localSearch ? (
              <RefreshCw size={18} strokeWidth={3} className="animate-spin" />
            ) : (
              <Search size={18} strokeWidth={3} />
            )}
          </div>
          <input
            type="text"
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            ref={inputRef}
            placeholder={t('admin.questions.searchPlaceholder')}
            className="w-full pr-12 pl-12 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all uyghur-text shadow-sm text-base"
          />
          {localSearch && (
            <button
              onClick={() => { setLocalSearch(''); setSearchQuery(''); }}
              className="absolute inset-y-0 left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors active:scale-95"
            >
              <X size={16} strokeWidth={3} />
            </button>
          )}
        </div>

        {/* Total Questions Count Badge on the left */}
        <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] dark:text-[#38bdf8] bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap mr-auto md:mr-auto self-end md:self-auto">
          <MessageSquare size={14} className="md:w-[15px] md:h-[15px]" />
          {t('admin.questions.total', { count: total })}
        </div>
      </div>

      {/* Empty State */}
      {questions.length === 0 && (
        <div className="glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-20 flex flex-col items-center justify-center text-center shadow-xl rounded-[24px]">
          <MessageSquare className="w-16 h-16 text-[#94a3b8] dark:text-slate-600 mb-6" />
          <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100">
            {t(searchQuery ? 'admin.table.noResults' : 'admin.questions.empty')}
          </h3>
          {searchQuery && (
            <p className="text-slate-500 dark:text-slate-400 font-normal mt-2">
              {t('admin.table.tryDifferent')}
            </p>
          )}
        </div>
      )}

      {/* Table */}
      {questions.length > 0 && (
        <div className="glass-panel dark:bg-slate-900/60 overflow-hidden rounded-[16px] md:rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-right lg:min-w-[900px]" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 border-b border-[#0369a1]/10 dark:border-slate-800 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] dark:text-[#38bdf8] uppercase">
                  <th className="px-3 md:px-6 py-3 md:py-5 text-right font-normal w-[50%] sm:w-[45%] lg:w-[40%]">{t('admin.questions.colQuestion')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[14%]">{t('admin.questions.colUser')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[8%]">{t('admin.questions.colFeedback')}</th>
                  <th className="hidden sm:table-cell px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[30%] sm:w-[35%] lg:w-[16%]">{t('admin.questions.colEvalQuality')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[15%]">{t('admin.questions.colDate')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 text-left font-normal w-[20%] sm:w-[20%] lg:w-[7%]">{t('admin.questions.colShowOnHome')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5 dark:divide-slate-800/30">
                {questions.map((q) => (
                  <tr
                    key={q.id}
                    className={`border-b border-[#0369a1]/5 dark:border-slate-800/30 hover:bg-[#e8f4f8]/20 dark:hover:bg-[#38bdf8]/5 transition-colors group/row ${
                      q.showOnHomepage ? 'bg-[#0369a1]/5 dark:bg-[#38bdf8]/5' : ''
                    }`}
                  >
                    {/* Question text */}
                    <td className="px-3 md:px-6 py-4 md:py-6">
                      <div className="flex items-start gap-2.5">
                        <div
                          title={q.isGlobal ? t('admin.questions.scopeGlobal') : t('admin.questions.scopeBook')}
                          className={`p-1.5 rounded-lg shrink-0 mt-0.5 ${
                            q.isGlobal
                              ? 'bg-violet-50 dark:bg-violet-950/40 text-violet-600 dark:text-violet-400'
                              : 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400'
                          }`}
                        >
                          {q.isGlobal ? <Globe size={14} /> : <BookOpen size={14} />}
                        </div>
                        <div className="flex-1 min-w-0 flex flex-col gap-1 text-right" dir="rtl">
                          <p
                            className="uyghur-text text-[#1a1a1a] dark:text-slate-100 font-semibold text-[14px] md:text-[16px] lg:text-[17px] leading-relaxed line-clamp-2"
                            lang="ug"
                            title={q.question}
                          >
                            {q.question}
                          </p>
                          {(!q.isGlobal || q.bookTitle || q.bookId) && (q.bookTitle || q.bookId) && (
                            <div className="flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400/90 font-medium mt-0.5">
                              <span className="opacity-60">—</span>
                              <span className="truncate uyghur-text" title={q.bookTitle || q.bookId || undefined}>
                                {q.bookTitle || q.bookId}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* User display name */}
                    <td className="hidden lg:table-cell px-3 md:px-6 py-4 md:py-6 text-center text-xs md:text-sm text-slate-700 dark:text-slate-300 font-medium whitespace-nowrap">
                      {q.userDisplayName ? (
                        <span>{q.userDisplayName}</span>
                      ) : (
                        <span className="text-slate-300 dark:text-slate-650">—</span>
                      )}
                    </td>

                    {/* User feedback */}
                    <td className="hidden lg:table-cell px-3 md:px-6 py-4 md:py-6 text-center text-[15px] md:text-[16px]">
                      {q.userFeedback === 'positive' ? (
                        <span title="Positive" className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600 dark:text-emerald-400 border border-emerald-100 dark:border-emerald-900/50 shadow-sm">👍</span>
                      ) : q.userFeedback === 'negative' ? (
                        <span title="Negative" className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-red-50 dark:bg-red-950/30 text-red-650 dark:text-red-400 border border-red-100 dark:border-red-900/50 shadow-sm">👎</span>
                      ) : (
                        <span className="text-slate-300 dark:text-slate-650">—</span>
                      )}
                    </td>

                    {/* Eval quality */}
                    <td className="hidden sm:table-cell px-3 md:px-6 py-4 md:py-6 text-center">
                      {q.evalStatus === 'completed' ? (
                        <div className="flex items-center justify-center gap-1 flex-wrap" dir="ltr">
                          <span
                            title={t('admin.questions.evalFaithfulness')}
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] md:text-[11px] font-medium bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400 border border-emerald-100 dark:border-emerald-900/50"
                          >
                            {Math.round((q.faithfulnessScore ?? 0) * 100)}%
                          </span>
                          <span
                            title={t('admin.questions.evalAnswerRelevance')}
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] md:text-[11px] font-medium bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400 border border-blue-100 dark:border-blue-900/50"
                          >
                            {Math.round((q.answerRelevanceScore ?? 0) * 100)}%
                          </span>
                          <span
                            title={t('admin.questions.evalContextPrecision')}
                            className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] md:text-[11px] font-medium bg-violet-50 dark:bg-violet-950/30 text-violet-700 dark:text-violet-400 border border-violet-100 dark:border-violet-900/50"
                          >
                            {Math.round((q.contextPrecisionScore ?? 0) * 100)}%
                          </span>
                        </div>
                      ) : q.evalStatus === 'queued' ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                          <Loader size={11} className="animate-spin" />
                          {t('admin.questions.evalQueued')}
                        </span>
                      ) : q.evalStatus === 'failed' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-50 dark:bg-red-950/30 text-red-650 dark:text-red-400 border border-red-100 dark:border-red-900/50">
                          {t('admin.questions.evalFailed')}
                        </span>
                      ) : (
                        <span className="text-slate-300 dark:text-slate-650">—</span>
                      )}
                    </td>

                    {/* Date */}
                    <td className="hidden lg:table-cell px-3 md:px-6 py-4 md:py-6 text-center text-xs md:text-sm text-slate-500 dark:text-slate-400 font-normal whitespace-nowrap">
                      {formatDate(q.ts)}
                    </td>

                    {/* Toggle */}
                    <td className="px-3 md:px-6 py-4 md:py-6 text-left">
                      <div className="flex items-center justify-start" dir="ltr">
                        <button
                          onClick={() => handleToggle(q)}
                          disabled={togglingId === q.id}
                          aria-label={
                            q.showOnHomepage
                              ? t('admin.questions.hideFromHome')
                              : t('admin.questions.showOnHome')
                          }
                          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#0369a1]/40 dark:focus:ring-[#38bdf8]/40 disabled:opacity-50 cursor-pointer shadow-inner ${
                            q.showOnHomepage ? 'bg-[#0369a1] dark:bg-[#38bdf8]' : 'bg-[#cbd5e1] dark:bg-slate-700'
                          }`}
                        >
                          <span
                            className={`inline-block h-4 w-4 rounded-full bg-white dark:bg-slate-900 shadow-md transition-transform duration-200 ${
                              q.showOnHomepage ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Infinite scroll sentinel */}
          <div
            ref={loaderRef}
            className="bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 px-6 py-8 flex flex-col items-center justify-center gap-4"
          >
            {isLoadingMore && !isInitialLoading ? (
              <div className="flex flex-col items-center gap-3 animate-fade-in">
                <div className="w-8 h-8 border-3 border-[#0369a1]/10 dark:border-[#38bdf8]/10 border-t-[#0369a1] dark:border-t-[#38bdf8] rounded-full animate-spin" />
                <span className="text-[10px] font-black text-[#0369a1] dark:text-[#38bdf8] uppercase animate-pulse">
                  {t('common.loadingMore')}
                </span>
              </div>
            ) : !hasMore && questions.length > 0 ? (
              <div className="flex flex-col items-center gap-3 opacity-30">
                <div className="w-12 h-[1px] bg-[#94a3b8] dark:bg-slate-700" />
                <p className="text-[10px] font-black text-[#94a3b8] dark:text-slate-400 uppercase">
                  {t('common.endOfList')}
                </p>
                <div className="w-12 h-[2px] bg-[#94a3b8] dark:bg-slate-700" />
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminQuestions;
