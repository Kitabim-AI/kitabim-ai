import { BookOpen, RefreshCw, Search, Share2 } from 'lucide-react';
import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { ContentSearchHit } from '../../services/searchTabsService';
import { ShareSearchResultModal } from '../share/ShareSearchResultModal';

interface ContentResultsListProps {
  hits: ContentSearchHit[];
  isLoading: boolean;
  hasQuery: boolean;
  query: string;
  noResultsTitleKey?: string;
  onOpenHit: (hit: ContentSearchHit) => void;
}

const BookCoverThumbnail: React.FC<{ src?: string | null; alt: string }> = ({ src, alt }) => {
  const [hasError, setHasError] = useState(false);

  if (src && !hasError) {
    return (
      <img
        src={src}
        alt={alt}
        onError={() => setHasError(true)}
        className="w-7 h-10 object-cover rounded shadow-xs shrink-0"
      />
    );
  }

  return (
    <div
      className="w-7 h-10 rounded shadow-xs shrink-0 bg-gradient-to-br from-[#0369a1]/15 to-[#0369a1]/30 dark:from-[#38bdf8]/15 dark:to-[#38bdf8]/30 flex items-center justify-center text-[#0369a1] dark:text-[#38bdf8] border border-[#0369a1]/20 dark:border-[#38bdf8]/20"
      title={alt}
    >
      <BookOpen size={14} strokeWidth={2} />
    </div>
  );
};

const highlightSnippet = (snippet: string, query: string): React.ReactNode => {
  const trimmed = query.trim();
  if (!trimmed) return snippet;

  try {
    const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = snippet.split(new RegExp(`(${escaped})`, 'gi'));
    return parts.map((part, index) =>
      part.toLowerCase() === trimmed.toLowerCase() ? (
        <mark
          key={index}
          className="bg-amber-200/90 dark:bg-amber-500/30 text-[#1a1a1a] dark:text-amber-200 font-semibold px-1 py-0.5 rounded shadow-sm"
        >
          {part}
        </mark>
      ) : (
        part
      )
    );
  } catch {
    return snippet;
  }
};

export const ContentResultsList: React.FC<ContentResultsListProps> = ({
  hits,
  isLoading,
  hasQuery,
  query,
  noResultsTitleKey,
  onOpenHit,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const isGuest = !isAuthenticated;
  const [shareHit, setShareHit] = useState<ContentSearchHit | null>(null);

  if (isLoading && hits.length === 0) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center gap-4">
        <RefreshCw className="w-8 h-8 text-[#0369a1] dark:text-[#38bdf8] animate-spin" />
        <span className="text-xs font-black text-[#0369a1] dark:text-[#38bdf8] uppercase">
          {t('common.loading')}
        </span>
      </div>
    );
  }

  if (!hasQuery) {
    return (
      <div className="w-full py-20 flex flex-col items-center justify-center opacity-40">
        <Search size={40} strokeWidth={1} className="text-[#0369a1] dark:text-[#38bdf8] mb-4" />
        <p className="text-slate-500 dark:text-slate-400 uyghur-text">
          {t('home.tabs.contentPlaceholder')}
        </p>
      </div>
    );
  }

  if (hits.length === 0) {
    return (
      <div className="w-full py-12 sm:py-20 px-6 sm:px-8 text-center glass-panel flex flex-col items-center justify-center rounded-[32px]">
        <p className="text-[#1a1a1a] dark:text-slate-100 font-bold text-lg sm:text-xl mb-2 uyghur-text max-w-md">
          {t(noResultsTitleKey || 'library.noResults.title')}
        </p>
        <p className="text-[#94a3b8] dark:text-slate-400 font-medium text-sm max-w-sm uyghur-text">
          {t('library.noResults.message')}
        </p>
      </div>
    );
  }

  return (
    <div className="w-full flex flex-col gap-4">
      {hits.map((hit) => {
        const titleWithVolume =
          hit.bookVolume !== null && hit.bookVolume !== undefined
            ? `${hit.bookTitle} (${t('book.volume', { volume: hit.bookVolume })})`
            : hit.bookTitle;

        return (
          <div
            key={hit.id}
            onClick={() => onOpenHit(hit)}
            className="group relative w-full bg-white/80 dark:bg-slate-900/60 backdrop-blur-xl rounded-2xl sm:rounded-3xl p-4 sm:p-6 cursor-pointer transition-all duration-300 border border-[#0369a1]/10 dark:border-[#38bdf8]/10 hover:border-[#0369a1]/30 dark:hover:border-[#38bdf8]/30 hover:-translate-y-0.5 hover:shadow-lg shadow-sm flex flex-col gap-3"
            dir="rtl"
          >
            {/* Top header row */}
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 dark:border-slate-800/80 pb-3">
              <div className="flex items-center gap-2 min-w-0">
                <BookCoverThumbnail src={hit.bookCoverUrl} alt={hit.bookTitle} />
                <div className="min-w-0">
                  <h3 className="font-bold text-[#1a1a1a] dark:text-slate-100 text-sm sm:text-base truncate" title={titleWithVolume}>
                    {titleWithVolume}
                  </h3>
                  {hit.bookAuthor && hit.bookAuthor !== 'Unknown Author' && (
                    <span className="text-xs text-[#0369a1] dark:text-[#38bdf8] font-medium truncate block">
                      {hit.bookAuthor}
                    </span>
                  )}
                </div>
              </div>

              {/* Page Badge */}
              <div className="shrink-0 flex items-center gap-1.5 px-3 py-1 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] font-bold text-xs sm:text-sm rounded-full">
                <span>📖 {hit.pageNumber}-بەت</span>
              </div>
            </div>

            {/* Snippet text */}
            <div
              data-testid="snippet-container"
              className={`uyghur-text text-slate-700 dark:text-slate-300 text-base leading-relaxed bg-slate-50/50 dark:bg-slate-950/40 p-3 sm:p-4 rounded-xl border border-slate-100 dark:border-slate-800/80 ${
                isGuest ? 'select-none' : ''
              }`}
              onCopy={isGuest ? (e) => e.preventDefault() : undefined}
              onContextMenu={isGuest ? (e) => e.preventDefault() : undefined}
            >
              {highlightSnippet(hit.snippet, query)}
            </div>

            {/* Footer action */}
            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setShareHit(hit);
                }}
                className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors"
              >
                <Share2 size={16} strokeWidth={2} />
                <span className="uyghur-text">{t('share.shareSearchResult')}</span>
              </button>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpenHit(hit);
                }}
                className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-[#0369a1] dark:text-[#38bdf8] hover:underline"
              >
                <BookOpen size={16} strokeWidth={2} />
                <span>بەتنى ئوقۇش</span>
              </button>
            </div>
          </div>
        );
      })}

      {shareHit && (
        <ShareSearchResultModal
          title={shareHit.bookTitle}
          subtitle={shareHit.bookAuthor ? `Author: ${shareHit.bookAuthor}` : undefined}
          content={shareHit.snippet}
          sourceLabel={`📖 ${shareHit.pageNumber}-بەت`}
          url={`${window.location.origin}/books/${shareHit.bookId}`}
          onClose={() => setShareHit(null)}
        />
      )}
    </div>
  );
};
