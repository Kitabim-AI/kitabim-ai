import { Book } from '@shared/types';
import { BookOpen, Clock, HardDrive, Loader2, Share2, Sparkles, Wand2, X } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { ShareModal } from '../share/ShareModal';

interface BookCardProps {
  book: Book;
  onClick: (book: Book) => void;
  onDelete?: (bookId: string) => void;
}

const getStatusStyles = (status: string) => {
  switch (status.toLowerCase()) {
    case 'ready': return 'bg-emerald-50 text-emerald-600';
    case 'ocr_done': return 'bg-blue-50 text-blue-600';
    case 'chunking': return 'bg-indigo-50 text-indigo-600';
    case 'indexing': return 'bg-orange-50 text-orange-600';
    case 'ocr': return 'bg-blue-50 text-blue-600';
    case 'embedding': return 'bg-orange-50 text-orange-600';
    case 'spell_check': return 'bg-purple-50 text-purple-600';
    case 'ocr_processing': return 'bg-blue-50 text-blue-600';
    case 'error': return 'bg-red-50 text-red-500';
    case 'pending': return 'bg-amber-50 text-amber-600';
    default: return 'bg-slate-50 text-slate-500';
  }
};

const parseBold = (str: string): React.ReactNode[] =>
  str.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <strong key={i} className="font-bold text-[#1a1a1a] dark:text-slate-100">{part.slice(2, -2)}</strong>
      : part
  );

const renderSummary = (text: string): React.ReactNode =>
  text.split('\n').filter(l => l.trim()).map((line, i) => {
    const trimmedLine = line.trim();

    // 1. Check for headers (hashes)
    const headingMatch = trimmedLine.match(/^(#{1,6})\s+(.*)/);
    const content = headingMatch ? headingMatch[2] : trimmedLine;

    // 2. Check for numbered sections (likely the major summary headers)
    const listMatch = content.match(/^(\d+)\.\s+(.*)/);
    if (listMatch) {
      const parts = listMatch[2].split(':');
      if (parts.length > 1) {
        return (
          <div key={i} className="mb-6 last:mb-0">
            <h4 className="text-[#0369a1] dark:text-[#38bdf8] font-bold text-base sm:text-lg mb-2 flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 flex items-center justify-center text-xs shrink-0">{listMatch[1]}</span>
              {parseBold(parts[0])}
            </h4>
            <div className="text-slate-700 dark:text-slate-300 leading-relaxed pr-1 sm:pr-2">
              {parseBold(parts.slice(1).join(':').trim())}
            </div>
          </div>
        );
      }
      return (
        <div key={i} className="flex gap-3 mb-4">
          <span className="text-[#0369a1] dark:text-[#38bdf8] font-bold shrink-0 mt-0.5">{listMatch[1]}.</span>
          <span className="text-slate-700 dark:text-slate-300">{parseBold(listMatch[2])}</span>
        </div>
      );
    }

    // 3. If it was a heading but not a numbered list, render as heading
    if (headingMatch) {
      const level = headingMatch[1].length;
      const Tag: any = `h${Math.min(6, level + 1)}`;
      return (
        <Tag key={i} className="font-bold text-[#1a1a1a] dark:text-slate-100 text-lg mb-4 mt-6 first:mt-0">
          {parseBold(content)}
        </Tag>
      );
    }

    // 4. Check for bullet points (often used in themes or keywords)
    const bulletMatch = trimmedLine.match(/^([-*•])\s+(.*)/);
    if (bulletMatch) {
      return (
        <div key={i} className="flex gap-3 mb-2 pr-2 sm:pr-4">
          <span className="text-[#0369a1] dark:text-[#38bdf8] font-bold shrink-0 mt-2.5 w-1.5 h-1.5 rounded-full bg-[#0369a1]/30 dark:bg-[#38bdf8]/30" />
          <span className="text-slate-600 dark:text-slate-300">{parseBold(bulletMatch[2])}</span>
        </div>
      );
    }

    // 5. Default paragraph
    return <p key={i} className="mb-4 last:mb-0 text-slate-700 dark:text-slate-300 leading-relaxed">{parseBold(trimmedLine)}</p>;
  });

export const BookCard: React.FC<BookCardProps> = ({ book, onClick }) => {
  const { t } = useI18n();
  const [showSummary, setShowSummary] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [summaryText, setSummaryText] = useState<string | null>(null);
  const [summaryGeneratedAt, setSummaryGeneratedAt] = useState<string | null>(null);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);

  const titleWithVolume = book.volume !== null && book.volume !== undefined
    ? `${book.title} (${t('book.volume', { volume: book.volume })})`
    : book.title;
  const displayAuthor = book.author?.trim();

  useEffect(() => {
    if (showSummary) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => { document.body.style.overflow = ''; };
  }, [showSummary]);

  const handleSummaryClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setShowSummary(true);
    if (summaryText === null && !isLoadingSummary) {
      setIsLoadingSummary(true);
      const result = await PersistenceService.getBookSummary(book.id);
      setSummaryText(result?.summary ?? null);
      setSummaryGeneratedAt(result?.generatedAt ?? null);
      setIsLoadingSummary(false);
    }
  };

  return (
    <>
      <div
        onClick={() => onClick(book)}
        className="group relative w-full max-w-[300px] bg-white/80 dark:bg-slate-900/60 backdrop-blur-xl rounded-2xl sm:rounded-3xl p-3 sm:p-5 cursor-pointer transition-all duration-300 border border-[#0369a1]/10 dark:border-[#38bdf8]/10 hover:border-[#0369a1]/30 dark:hover:border-[#38bdf8]/30 hover:-translate-y-1 hover:shadow-[0_12px_24px_rgba(3,105,161,0.1)] dark:hover:shadow-[0_12px_24px_rgba(56,189,248,0.15)] active:-translate-y-3 shadow-md"
      >
        {/* Book Cover */}
        <div className="relative w-full aspect-[5/7] mb-3 sm:mb-5 rounded-xl sm:rounded-2xl overflow-hidden shadow-lg transition-transform duration-300 group-hover:scale-[1.03] group-hover:shadow-xl">
          {book.coverUrl ? (
            <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${book.coverUrl})` }} />
          ) : (
            <div className="absolute inset-0 bg-gradient-to-br from-[#FFD54F] via-[#FF9800] to-[#F06292] flex items-center justify-center">
              <div className="absolute inset-0 opacity-20" style={{ backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 20px, rgba(255,255,255,0.1) 20px, rgba(255,255,255,0.1) 40px)' }} />
              <span className="text-5xl drop-shadow-lg">📖</span>
            </div>
          )}

          {/* Action icons — only for ready books */}
          {book.status === 'ready' && (
            <div className="absolute top-2 left-2 flex flex-col gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
              <button
                onClick={handleSummaryClick}
                title={t('bookCard.summary.title')}
                className="p-1.5 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm rounded-full text-[#0369a1] dark:text-[#38bdf8] hover:bg-white dark:hover:bg-slate-800 shadow-sm"
              >
                <Wand2 size={14} strokeWidth={2.5} />
              </button>
              <button
                onClick={e => { e.stopPropagation(); setShowShare(true); }}
                title={t('share.shareBook')}
                className="p-1.5 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm rounded-full text-[#1877F2] dark:text-[#38bdf8] hover:bg-white dark:hover:bg-slate-800 shadow-sm"
              >
                <Share2 size={14} strokeWidth={2.5} />
              </button>
            </div>
          )}
        </div>

        {/* Book Info */}
        <div className="text-right space-y-1 sm:space-y-4" dir="rtl">
          <h3 className="font-bold text-[#1a1a1a] dark:text-slate-100 text-sm sm:text-lg leading-snug line-clamp-2 min-h-[2.5rem] sm:min-h-[3.5rem]" title={titleWithVolume}>
            {titleWithVolume}
          </h3>
          <div className="flex items-center justify-between text-[10px] sm:text-sm pt-2 border-t border-[#0369a1]/5 dark:border-[#38bdf8]/10">
            {/* Right side: Author (in RTL) */}
            <div className="text-[#0369a1] dark:text-[#38bdf8] font-medium truncate max-w-[60%]">
              {displayAuthor && displayAuthor !== 'Unknown Author' ? displayAuthor : ''}
            </div>

            {/* Left side: Stats & Status (in RTL) */}
            <div className="flex items-center gap-2 sm:gap-3 text-[#64748b] dark:text-slate-400 shrink-0 font-medium">


              {book.status === 'ready' && (book.readCount ?? 0) > 0 && (
                <span className="flex items-center gap-1 text-[10px] sm:text-xs">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="sm:w-3.5 sm:h-3.5">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                  {book.readCount}
                </span>
              )}

              <span className="text-[10px] sm:text-xs">
                {t('book.pagesCount', { count: book.totalPages || (book as any).total_pages || 0 })}
              </span>
            </div>
          </div>
        </div>
      </div>

      {showShare && <ShareModal book={book} onClose={() => setShowShare(false)} />}

      {/* Summary modal */}
      {showSummary && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-4 md:p-6 pt-[max(0.5rem,env(safe-area-inset-top))] pb-[max(0.5rem,env(safe-area-inset-bottom))]" dir="rtl" lang="ug">
          <div
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in transition-all duration-500"
            onClick={() => setShowSummary(false)}
          />
          <div
            className="bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] shadow-2xl w-full max-w-4xl max-h-[calc(100dvh-2rem)] sm:max-h-[85vh] relative z-10 overflow-hidden animate-scale-up border border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Header Ribbon */}
            <div className="px-3 sm:px-6 py-2 sm:py-4 border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex items-center justify-between gap-2 sm:gap-4 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm shrink-0">
              <div className="flex items-center gap-2 sm:gap-4 min-w-0 flex-shrink">
                <div className="flex items-center justify-center min-w-[40px] min-h-[40px] w-10 h-10 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shrink-0">
                  <BookOpen size={20} />
                </div>
                <div className="min-w-0 flex flex-col justify-center">
                  <h2 className="font-bold text-[#1a1a1a] dark:text-slate-100 truncate text-base sm:text-lg leading-tight flex items-center flex-wrap gap-2 text-right">
                    <span className="truncate">{titleWithVolume}</span>
                    {displayAuthor && (
                      <span className="text-xs sm:text-sm text-[#64748b] dark:text-slate-400 font-normal">
                        ({displayAuthor})
                      </span>
                    )}
                  </h2>
                  <div className="flex items-center gap-2 text-[#94a3b8] text-xs mt-0.5">
                    <span className="flex items-center gap-1.5 px-2.5 py-0.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-full text-[11px] font-medium">
                      {t('bookCard.summary.title')}
                    </span>
                    <span className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-full text-[10px] font-bold">
                      <Sparkles size={11} strokeWidth={2.5} />
                      {t('bookCard.summary.aiBadge')}
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setShowSummary(false)}
                className="p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-red-200 dark:border-red-900/30 text-red-400 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 hover:text-red-500 dark:hover:text-red-400 flex items-center justify-center shrink-0"
                title={t('common.close')}
              >
                <X size={18} className="sm:w-5 sm:h-5" />
              </button>
            </div>

            {/* Reading Canvas */}
            <div className="flex-1 min-h-0 overflow-y-auto p-4 sm:p-6 custom-scrollbar paper-background">
              {isLoadingSummary ? (
                <div className="h-64 flex flex-col items-center justify-center gap-6 opacity-40">
                  <Loader2 size={48} className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" />
                  <p className="text-sm text-slate-400 dark:text-slate-500 font-normal uppercase tracking-widest">{t('bookCard.summary.loading')}</p>
                </div>
              ) : summaryText ? (
                <div className="w-full max-w-4xl mx-auto">
                  <div className="bg-white dark:bg-slate-900/60 p-6 rounded-[24px] shadow-xl border border-[#0369a1]/10 dark:border-[#38bdf8]/10 relative">
                    <div className="text-[#1e293b] dark:text-slate-200 leading-[2] uyghur-text text-base sm:text-lg relative z-10">
                      {renderSummary(summaryText)}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="h-64 flex flex-col items-center justify-center text-center gap-4 opacity-40">
                  <HardDrive size={48} className="text-slate-300 dark:text-slate-600" />
                  <p className="text-sm sm:text-base text-slate-400 dark:text-slate-500 font-normal">{t('bookCard.summary.noSummary')}</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-3 sm:px-6 py-2 sm:py-4 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm border-t border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3 sm:gap-6 text-xs text-slate-400 dark:text-slate-500 font-normal">
                {summaryGeneratedAt && (
                  <div className="flex items-center gap-2">
                    <Clock size={14} />
                    <span>{t('common.lastUpdated')}: {new Date(summaryGeneratedAt).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2 sm:gap-3">
                <button
                  onClick={() => setShowSummary(false)}
                  className="px-4 py-2 sm:px-6 sm:py-2.5 bg-slate-900 dark:bg-slate-800 hover:bg-slate-800 dark:hover:bg-slate-700 text-white dark:text-slate-100 rounded-xl text-xs sm:text-sm font-normal transition-all active:scale-95 shadow-md"
                >
                  {t('common.close')}
                </button>
              </div>
            </div>
          </div>
        </div>
      , document.body)}
    </>
  );
};
