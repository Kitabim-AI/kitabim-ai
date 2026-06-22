/**
 * Admin Questions Panel — shows all RAG questions with a home-page visibility toggle.
 */

import { AlertCircle, Globe, Loader, MessageSquare, RefreshCw, Search, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { authFetch } from '../../services/authService';

const PAGE_SIZE = 25;

interface RagQuestion {
  id: number;
  question: string;
  isGlobal: boolean;
  bookId: string | null;
  isFirstTurn: boolean;
  showOnHomepage: boolean;
  userFeedback: string | null;
  ts: string;
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
        <MessageSquare className="w-16 h-16 text-[#0369a1] mb-6 animate-bounce" />
        <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
        <AlertCircle className="w-16 h-16 text-red-500 mb-6" />
        <h3 className="text-xl font-normal text-red-500">{t('admin.questions.error')}</h3>
        <p className="text-slate-500 font-normal mt-2">{error}</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Search and Filters Bar */}
      <div className="flex flex-col-reverse md:flex-row gap-3 md:gap-4">
        {/* Search input box on the right */}
        <div className="relative flex-1 lg:flex-none lg:w-[30%] group">
          <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] transition-colors">
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
            placeholder={t('library.searchPlaceholder')}
            className="w-full pr-12 pl-12 py-2.5 md:py-3 bg-white border-2 border-[#0369a1]/10 rounded-2xl outline-none focus:border-[#0369a1] transition-all uyghur-text shadow-sm text-base"
          />
          {localSearch && (
            <button
              onClick={() => { setLocalSearch(''); setSearchQuery(''); }}
              className="absolute inset-y-0 left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] transition-colors active:scale-95"
            >
              <X size={16} strokeWidth={3} />
            </button>
          )}
        </div>

        {/* Total Questions Count Badge on the left */}
        <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] bg-[#0369a1]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 shadow-sm whitespace-nowrap mr-auto md:mr-auto self-end md:self-auto">
          <MessageSquare size={14} className="md:w-[15px] md:h-[15px]" />
          {t('admin.questions.total', { count: total })}
        </div>
      </div>

      {/* Empty State */}
      {questions.length === 0 && (
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
          <MessageSquare className="w-16 h-16 text-[#94a3b8] mb-6" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">
            {t(searchQuery ? 'admin.table.noResults' : 'admin.questions.empty')}
          </h3>
          {searchQuery && (
            <p className="text-slate-500 font-normal mt-2">
              {t('admin.table.tryDifferent')}
            </p>
          )}
        </div>
      )}

      {/* Table */}
      {questions.length > 0 && (
        <div className="glass-panel overflow-hidden rounded-[16px] md:rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-right lg:min-w-[900px]" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] uppercase">
                  <th className="px-3 md:px-6 py-3 md:py-5 text-right font-normal w-[45%] md:w-[50%]">{t('admin.questions.colQuestion')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[15%]">{t('admin.questions.colScope')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[12%]">{t('admin.questions.colFeedback')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 text-center font-normal w-[18%]">{t('admin.questions.colDate')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 text-left font-normal w-[10%]">{t('admin.questions.colShowOnHome')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5">
                {questions.map((q) => (
                  <tr
                    key={q.id}
                    className={`hover:bg-[#e8f4f8]/20 transition-colors group/row ${
                      q.showOnHomepage ? 'bg-[#0369a1]/5' : ''
                    }`}
                  >
                    {/* Question text */}
                    <td className="px-3 md:px-6 py-4 md:py-6">
                      <p
                        className="uyghur-text text-[#1a1a1a] font-semibold text-[14px] md:text-[16px] lg:text-[17px] leading-relaxed line-clamp-2 text-right"
                        dir="rtl"
                        lang="ug"
                        title={q.question}
                      >
                        {q.question}
                      </p>
                    </td>

                    {/* Scope: global vs book */}
                    <td className="px-3 md:px-6 py-4 md:py-6 text-center">
                      <span
                        className={`inline-flex items-center px-3 py-1 rounded-full text-[11px] md:text-[12px] font-medium border shadow-sm ${
                          q.isGlobal
                            ? 'bg-violet-50 text-violet-700 border-violet-100'
                            : 'bg-amber-50 text-amber-700 border-amber-100'
                        }`}
                      >
                        {q.isGlobal
                          ? t('admin.questions.scopeGlobal')
                          : t('admin.questions.scopeBook')}
                      </span>
                    </td>

                    {/* User feedback */}
                    <td className="px-3 md:px-6 py-4 md:py-6 text-center text-[15px] md:text-[16px]">
                      {q.userFeedback === 'positive' ? (
                        <span title="Positive" className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-100 shadow-sm">👍</span>
                      ) : q.userFeedback === 'negative' ? (
                        <span title="Negative" className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-red-50 text-red-600 border border-red-100 shadow-sm">👎</span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>

                    {/* Date */}
                    <td className="px-3 md:px-6 py-4 md:py-6 text-center text-xs md:text-sm text-slate-500 font-normal whitespace-nowrap">
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
                          className="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#0369a1]/40 disabled:opacity-50 cursor-pointer shadow-inner"
                          style={{
                            backgroundColor: q.showOnHomepage ? '#0369a1' : '#cbd5e1',
                          }}
                        >
                          <span
                            className={`inline-block h-4 w-4 rounded-full bg-white shadow-md transition-transform duration-200 ${
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
            className="bg-[#0369a1]/5 px-6 py-8 flex flex-col items-center justify-center gap-4"
          >
            {isLoadingMore && !isInitialLoading ? (
              <div className="flex flex-col items-center gap-3 animate-fade-in">
                <div className="w-8 h-8 border-3 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin" />
                <span className="text-[10px] font-black text-[#0369a1] uppercase animate-pulse">
                  {t('common.loadingMore')}
                </span>
              </div>
            ) : !hasMore && questions.length > 0 ? (
              <div className="flex flex-col items-center gap-3 opacity-30">
                <div className="w-12 h-[1px] bg-[#94a3b8]" />
                <p className="text-[10px] font-black text-[#94a3b8] uppercase">
                  {t('common.endOfList')}
                </p>
                <div className="w-12 h-[2px] bg-[#94a3b8]" />
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminQuestions;
