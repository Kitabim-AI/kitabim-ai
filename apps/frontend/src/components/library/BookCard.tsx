import { Book } from '@shared/types';
import { BookOpen, Sparkles, Wand2, X } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';

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
      ? <strong key={i} className="font-bold text-[#1a1a1a]">{part.slice(2, -2)}</strong>
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
            <h4 className="text-[#0369a1] font-bold text-base sm:text-lg mb-2 flex items-center gap-2">
              <span className="w-6 h-6 rounded-lg bg-[#0369a1]/10 flex items-center justify-center text-xs shrink-0">{listMatch[1]}</span>
              {parseBold(parts[0])}
            </h4>
            <div className="text-slate-700 leading-relaxed pr-1 sm:pr-2">
              {parseBold(parts.slice(1).join(':').trim())}
            </div>
          </div>
        );
      }
      return (
        <div key={i} className="flex gap-3 mb-4">
          <span className="text-[#0369a1] font-bold shrink-0 mt-0.5">{listMatch[1]}.</span>
          <span className="text-slate-700">{parseBold(listMatch[2])}</span>
        </div>
      );
    }

    // 3. If it was a heading but not a numbered list, render as heading
    if (headingMatch) {
      const level = headingMatch[1].length;
      const Tag: any = `h${Math.min(6, level + 1)}`;
      return (
        <Tag key={i} className="font-bold text-[#1a1a1a] text-lg mb-4 mt-6 first:mt-0">
          {parseBold(content)}
        </Tag>
      );
    }

    // 4. Check for bullet points (often used in themes or keywords)
    const bulletMatch = trimmedLine.match(/^([-*•])\s+(.*)/);
    if (bulletMatch) {
      return (
        <div key={i} className="flex gap-3 mb-2 pr-2 sm:pr-4">
          <span className="text-[#0369a1] font-bold shrink-0 mt-2.5 w-1.5 h-1.5 rounded-full bg-[#0369a1]/30" />
          <span className="text-slate-600">{parseBold(bulletMatch[2])}</span>
        </div>
      );
    }

    // 5. Default paragraph
    return <p key={i} className="mb-4 last:mb-0 text-slate-700 leading-relaxed">{parseBold(trimmedLine)}</p>;
  });

export const BookCard: React.FC<BookCardProps> = ({ book, onClick }) => {
  const { t } = useI18n();
  const [showSummary, setShowSummary] = useState(false);
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
        className="group relative w-full max-w-[300px] bg-white/80 backdrop-blur-xl rounded-2xl sm:rounded-3xl p-3 sm:p-5 cursor-pointer transition-all duration-300 border border-[#0369a1]/10 hover:border-[#0369a1]/30 hover:-translate-y-1 hover:shadow-[0_12px_24px_rgba(3,105,161,0.1)] active:-translate-y-3 shadow-md"
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

          {/* Summary icon — only for ready books */}
          {book.status === 'ready' && (
            <button
              onClick={handleSummaryClick}
              title={t('bookCard.summary.title')}
              className="absolute top-2 left-2 p-1.5 bg-white/80 backdrop-blur-sm rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-200 text-[#0369a1] hover:bg-white shadow-sm z-10"
            >
              <Wand2 size={14} strokeWidth={2.5} />
            </button>
          )}
        </div>

        {/* Book Info */}
        <div className="text-right space-y-1 sm:space-y-4" dir="rtl">
          <h3 className="font-bold text-[#1a1a1a] text-sm sm:text-lg leading-snug line-clamp-2 min-h-[2.5rem] sm:min-h-[3.5rem]" title={titleWithVolume}>
            {titleWithVolume}
          </h3>
          <div className="flex items-center justify-between text-[10px] sm:text-sm pt-2 border-t border-[#0369a1]/5">
            {/* Right side: Author (in RTL) */}
            <div className="text-[#0369a1] font-medium truncate max-w-[60%]">
              {displayAuthor && displayAuthor !== 'Unknown Author' ? displayAuthor : ''}
            </div>

            {/* Left side: Stats & Status (in RTL) */}
            <div className="flex items-center gap-2 sm:gap-3 text-[#64748b] shrink-0 font-medium">


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

      {/* Summary modal */}
      {showSummary && createPortal(
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-2 sm:p-4 md:p-8" dir="rtl" lang="ug">
          <div
            className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in transition-all duration-500"
            onClick={() => setShowSummary(false)}
          />
          <div
            className="bg-white/90 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] md:rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.3)] w-full max-w-2xl max-h-[95vh] sm:max-h-[90vh] relative z-10 overflow-hidden animate-scale-up border border-white/40 flex flex-col"
            onClick={e => e.stopPropagation()}
          >
            {/* Header */}
            <div className="p-4 pb-3 sm:p-6 sm:pb-4 md:p-8 md:pb-6 border-b border-slate-100 flex items-start justify-between bg-white/50">
              <div className="flex items-center gap-3 sm:gap-4 md:gap-6">
                <div className="p-2.5 sm:p-3 md:p-4 bg-[#0369a1] text-white rounded-2xl sm:rounded-[24px] shadow-xl shadow-[#0369a1]/20 shrink-0">
                  <BookOpen size={20} strokeWidth={2.5} className="sm:hidden" />
                  <BookOpen size={28} strokeWidth={2.5} className="hidden sm:block" />
                </div>
                <div>
                  <h3 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] mb-2 leading-tight flex items-center flex-wrap gap-2 text-right">
                    <span>{titleWithVolume}</span>
                    {displayAuthor && (
                      <span className="text-base sm:text-lg text-slate-400 font-normal">({displayAuthor})</span>
                    )}
                  </h3>
                  <div className="flex items-center gap-2 text-[#94a3b8] text-sm font-normal uppercase tracking-wider">
                    <span className="flex items-center gap-1.5 px-3 py-1 bg-[#0369a1]/10 text-[#0369a1] rounded-full text-xs">
                      {t('bookCard.summary.title')}
                    </span>
                    <span className="flex items-center gap-1.5 px-3 py-1 bg-amber-500/10 text-amber-600 rounded-full text-[10px] font-bold">
                      <Sparkles size={12} strokeWidth={2.5} />
                      {t('bookCard.summary.aiBadge')}
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setShowSummary(false)}
                className="p-2 sm:p-3 hover:bg-red-50 text-slate-300 hover:text-red-500 rounded-2xl transition-all active:scale-95 group shrink-0"
              >
                <X size={20} strokeWidth={3} className="sm:hidden" />
                <X size={28} strokeWidth={3} className="hidden sm:block" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-grow overflow-y-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden p-4 sm:p-6 md:p-10 bg-[#f8fafc]/30">
              {isLoadingSummary ? (
                <div className="h-64 flex flex-col items-center justify-center gap-6 opacity-40">
                  <p className="text-sm text-slate-400 font-normal uppercase tracking-widest">{t('bookCard.summary.loading')}</p>
                </div>
              ) : summaryText ? (
                <div className="bg-white/80 p-4 pt-8 sm:p-6 sm:pt-10 md:p-10 md:pt-12 rounded-[20px] sm:rounded-[24px] md:rounded-[32px] shadow-sm border border-white relative overflow-hidden">
                  <div className="absolute top-0 right-0 w-32 h-32 bg-[#0369a1]/5 rounded-bl-[100px] -mr-10 -mt-10" />
                  <div className="text-[#1e293b] leading-[2] uyghur-text text-base sm:text-lg relative z-10">
                    {renderSummary(summaryText)}
                  </div>
                </div>
              ) : (
                <div className="h-64 flex flex-col items-center justify-center text-center gap-4 opacity-40">
                  <p className="text-sm sm:text-base text-slate-400 font-normal">{t('bookCard.summary.noSummary')}</p>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-4 px-4 sm:p-4 sm:px-6 md:p-6 md:px-10 bg-white/50 border-t border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs text-slate-400 font-normal">
                {summaryGeneratedAt && (
                  <span>{t('common.lastUpdated')}: {new Date(summaryGeneratedAt).toLocaleDateString()}</span>
                )}
              </div>
              <button
                onClick={() => setShowSummary(false)}
                className="px-4 py-2 sm:px-6 sm:py-2.5 md:px-8 md:py-3 bg-slate-900 hover:bg-slate-800 text-white rounded-2xl text-sm font-normal transition-all active:scale-95 shadow-lg shadow-black/10 uppercase tracking-widest"
              >
                {t('common.close')}
              </button>
            </div>
          </div>
        </div>
      , document.body)}
    </>
  );
};
