import { Book } from '@shared/types';
import { Check, Copy, ExternalLink, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { buildSafeTweetText } from '../../utils/shareText';
import { FacebookIcon, XIcon } from './ShareIcons';

interface ShareModalProps {
  book: Book;
  onClose: () => void;
}

export const ShareModal: React.FC<ShareModalProps> = ({ book, onClose }) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const shareUrl = `${window.location.origin}/api/share/book/${book.id}`;
  const deepLink = `${window.location.origin}/books/${book.id}`;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(deepLink);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFacebook = () => {
    const fbUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`;
    window.open(fbUrl, '_blank', 'noopener,noreferrer,width=600,height=500');
  };

  const handleTwitter = () => {
    const tweetText = buildSafeTweetText({
      headLines: [],
      contentPrefix: '📖 ',
      contentText: `${titleWithVolume}${displayAuthor ? ` - ${displayAuthor}` : ''}`,
      tailLines: [deepLink],
    });
    const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
    window.open(twitterUrl, '_blank', 'noopener,noreferrer,width=550,height=420');
  };

  const displayAuthor = book.author?.trim();
  const titleWithVolume =
    book.volume != null
      ? `${book.title} (${t('book.volume', { volume: book.volume })})`
      : book.title;

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" dir="rtl">
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl"
        onClick={onClose}
      />

      <div
        className="relative z-10 w-full max-w-md bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[32px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] dark:shadow-black/35 overflow-hidden border border-white/40 dark:border-slate-800 animate-scale-up"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 rounded-xl">
              <XIcon />
            </div>
            <span className="font-normal text-[#1a1a1a] dark:text-slate-100 uyghur-text">{t('share.shareBook')}</span>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-red-50 dark:hover:bg-red-950/20 text-slate-300 dark:text-slate-500 hover:text-red-400 dark:hover:text-red-400 rounded-xl transition-all"
          >
            <X size={20} strokeWidth={2.5} />
          </button>
        </div>

        {/* Facebook preview card */}
        <div className="p-5 pb-4">
          <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-3 font-normal text-right">
            {t('share.previewLabel')}
          </p>
          <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-sm">
            {/* Cover image */}
            <div className="w-full aspect-[1.91/1] bg-gradient-to-br from-[#FFD54F] via-[#FF9800] to-[#F06292] overflow-hidden">
              {book.coverUrl ? (
                <img
                  src={book.coverUrl}
                  alt={book.title}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-4xl">📖</div>
              )}
            </div>
            {/* OG text preview */}
            <div className="p-3 text-left bg-[#f0f2f5] dark:bg-slate-900/50">
              <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wide">kitabim.ai</p>
              <p className="text-sm font-semibold text-[#1c1e21] dark:text-slate-200 leading-snug mt-0.5 line-clamp-1">
                {titleWithVolume}
              </p>
              {displayAuthor && (
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-1">{displayAuthor}</p>
              )}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="grid grid-cols-3 gap-2 p-5 pt-0">
          <button
            onClick={handleCopy}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[#1a1a1a] dark:text-slate-200 rounded-2xl text-xs font-normal transition-all active:scale-95"
          >
            {copied ? <Check size={15} className="text-emerald-500" strokeWidth={2.5} /> : <Copy size={15} strokeWidth={2.5} />}
            <span className="uyghur-text">
              {copied ? t('share.linkCopied') : t('share.copyLink')}
            </span>
          </button>

          <button
            onClick={handleTwitter}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-black hover:bg-slate-900 dark:bg-slate-800 dark:hover:bg-slate-700 text-white rounded-2xl text-xs font-normal transition-all active:scale-95 shadow-md"
          >
            <XIcon />
            <span className="uyghur-text whitespace-nowrap">{t('share.postToX')}</span>
          </button>

          <button
            onClick={handleFacebook}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-[#1877F2] hover:bg-[#166fe5] text-white rounded-2xl text-xs font-normal transition-all active:scale-95 shadow-md shadow-[#1877F2]/30 dark:shadow-[#1877F2]/10"
          >
            <FacebookIcon />
            <span className="uyghur-text whitespace-nowrap">{t('share.postToFacebook')}</span>
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
