import { Check, Copy, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';

interface ShareSearchResultModalProps {
  title: string;
  subtitle?: string;
  content: string;
  sourceLabel?: string;
  url?: string;
  onClose: () => void;
}

const FacebookIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
  </svg>
);

const XIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
  </svg>
);

export const ShareSearchResultModal: React.FC<ShareSearchResultModalProps> = ({
  title,
  subtitle,
  content,
  sourceLabel,
  url,
  onClose,
}) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  const shareTargetUrl = url || window.location.origin;

  const fullTextToShare = [
    title ? `📌 ${title}` : '',
    subtitle ? `(${subtitle})` : '',
    content ? `"${content}"` : '',
    sourceLabel ? `— Source: ${sourceLabel}` : '',
    `Kitabim AI: ${shareTargetUrl}`,
  ]
    .filter(Boolean)
    .join('\n\n');

  const handleCopy = async () => {
    await navigator.clipboard.writeText(fullTextToShare);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTwitter = () => {
    const tweetText = [
      title ? `📌 ${title}` : '',
      content ? `"${content.slice(0, 160)}"` : '',
      sourceLabel ? `— ${sourceLabel}` : '',
      shareTargetUrl,
    ]
      .filter(Boolean)
      .join('\n\n');

    const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
    window.open(twitterUrl, '_blank', 'noopener,noreferrer,width=550,height=420');
  };

  const handleFacebook = async () => {
    await navigator.clipboard.writeText(fullTextToShare).catch(() => {});
    const fbUrl = `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareTargetUrl)}`;
    window.open(fbUrl, '_blank', 'noopener,noreferrer,width=620,height=560');
  };

  const previewContent = content.length > 200 ? content.slice(0, 200) + '…' : content;

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" dir="rtl">
      <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl" onClick={onClose} />

      <div
        className="relative z-10 w-full max-w-md bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[32px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] dark:shadow-black/35 overflow-hidden border border-white/40 dark:border-slate-800 animate-scale-up"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl">
              <XIcon />
            </div>
            <span className="font-normal text-[#1a1a1a] dark:text-slate-100 uyghur-text">
              {t('share.shareSearchResult')}
            </span>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-red-50 dark:hover:bg-red-950/20 text-slate-300 dark:text-slate-500 hover:text-red-400 dark:hover:text-red-400 rounded-xl transition-all"
          >
            <X size={20} strokeWidth={2.5} />
          </button>
        </div>

        {/* Search Result Card Preview */}
        <div className="p-5 pb-4 flex flex-col gap-3">
          <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wider font-normal text-right">
            {t('share.previewLabel')}
          </p>

          <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 p-4 shadow-sm flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-bold text-sm text-[#1a1a1a] dark:text-slate-100 uyghur-text">
                {title}
              </h4>
              {sourceLabel && (
                <span className="px-2.5 py-0.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] font-medium text-xs rounded-full shrink-0">
                  {sourceLabel}
                </span>
              )}
            </div>

            {subtitle && (
              <p className="text-xs text-slate-500 dark:text-slate-400 font-medium uyghur-text">
                {subtitle}
              </p>
            )}

            {previewContent && (
              <p className="text-sm text-slate-700 dark:text-slate-300 uyghur-text leading-relaxed bg-slate-50 dark:bg-slate-900 p-3 rounded-xl border border-slate-100 dark:border-slate-800">
                {previewContent}
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="grid grid-cols-3 gap-2 p-5 pt-0">
          <button
            onClick={handleCopy}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[#1a1a1a] dark:text-slate-200 rounded-2xl text-xs font-normal transition-all active:scale-95"
          >
            {copied ? (
              <Check size={15} className="text-emerald-500" strokeWidth={2.5} />
            ) : (
              <Copy size={15} strokeWidth={2.5} />
            )}
            <span className="uyghur-text">{copied ? t('share.linkCopied') : t('share.copyLink')}</span>
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
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-[#1877F2] hover:bg-[#166fe5] text-white rounded-2xl text-xs font-normal transition-all active:scale-95 shadow-md shadow-[#1877F2]/30"
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
