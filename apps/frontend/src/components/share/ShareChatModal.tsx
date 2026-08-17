import { Check, ClipboardPaste, Copy, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { cleanShareText, buildSafeTweetText, formatShareSource, DEFAULT_SHARE_HASHTAGS } from '../../utils/shareText';
import { FacebookIcon, XIcon } from './ShareIcons';

interface ShareChatModalProps {
  question: string;
  answer: string;
  bookId?: string;
  bookTitle?: string;
  bookAuthor?: string;
  onClose: () => void;
}

export const ShareChatModal: React.FC<ShareChatModalProps> = ({ question, answer, bookId, bookTitle, bookAuthor, onClose }) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [fbClicked, setFbClicked] = useState(false);

  const safeQ = cleanShareText(question || '');
  const safeA = cleanShareText(answer || '');

  const shareUrl = window.location.origin;
  const sourceLine = formatShareSource({ bookTitle, bookAuthor });

  const footerText = `-- كىتابىم تورى\n${shareUrl}`;
  const qaText = [
    safeQ ? `سوئال: ${safeQ}` : '',
    safeA ? `زېرەكچاق: ${safeA}` : '',
    sourceLine,
    footerText
  ].filter(Boolean).join('\n\n');

  const handleCopy = async () => {
    await navigator.clipboard.writeText(qaText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleTwitter = () => {
    const tweetText = buildSafeTweetText({
      headLines: [safeQ ? `سوئال: ${safeQ}` : ''],
      contentPrefix: 'زېرەكچاق: ',
      contentText: safeA,
      tailLines: [
        sourceLine,
        footerText,
        DEFAULT_SHARE_HASHTAGS,
      ],
    });
    const twitterUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(tweetText)}`;
    window.open(twitterUrl, '_blank', 'noopener,noreferrer,width=550,height=420');
  };

  const handleFacebook = async () => {
    await navigator.clipboard.writeText(qaText).catch(() => { });
    const fbUrl = bookId
      ? `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(`${window.location.origin}/api/share/book/${bookId}`)}`
      : `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(shareUrl)}`;

    window.open(fbUrl, '_blank', 'noopener,noreferrer,width=620,height=560');
    setFbClicked(true);
  };

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" dir="rtl">
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in"
        onClick={onClose}
      />

      <div
        className="relative z-10 w-full max-w-md bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[32px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] dark:shadow-black/35 overflow-hidden border border-white/40 dark:border-slate-800 animate-fade-in"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-4 border-b border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-100 rounded-xl">
              <XIcon />
            </div>
            <span className="font-normal text-[#1a1a1a] dark:text-slate-100 uyghur-text">{t('share.shareQA')}</span>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-red-50 dark:hover:bg-red-950/20 text-slate-300 dark:text-slate-500 hover:text-red-400 dark:hover:text-red-400 rounded-xl transition-all"
          >
            <X size={20} strokeWidth={2.5} />
          </button>
        </div>

        {/* Q&A preview */}
        <div className="p-5 pb-4 flex flex-col gap-3">
          <p className="text-xs text-slate-400 dark:text-slate-500 uppercase tracking-wider font-normal text-right">
            {t('share.previewLabel')}
          </p>

          {/* Book source chip */}
          {bookTitle && (
            <div className="flex items-center justify-end gap-2 px-3 py-2 bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 border border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl">
              <div className="flex flex-col items-end min-w-0">
                <span className="text-xs font-normal text-[#0369a1] dark:text-[#38bdf8] uyghur-text leading-snug truncate max-w-full">{bookTitle}</span>
                {bookAuthor && (
                  <span className="text-[10px] text-slate-400 dark:text-slate-500 font-normal uyghur-text truncate max-w-full">{bookAuthor}</span>
                )}
              </div>
              <span className="text-base shrink-0">📖</span>
            </div>
          )}

          {/* Question bubble */}
          {question && (
            <div className="bg-white dark:bg-slate-950 border border-[#0369a1]/10 dark:border-slate-800 rounded-2xl px-4 py-2.5 text-sm text-[#1a1a1a] dark:text-slate-100 font-normal uyghur-text leading-relaxed line-clamp-3">
              {question}
            </div>
          )}

          {/* Answer bubble */}
          <div className="bg-[#0369a1] dark:bg-[#38bdf8] rounded-2xl px-4 py-2.5 text-sm text-white dark:text-slate-950 font-normal uyghur-text leading-relaxed w-full max-h-48 overflow-y-auto custom-scrollbar-mini">
            {safeA}
          </div>
        </div>

        {/* Paste hint — shown after FB button is clicked */}
        {fbClicked && (
          <div className="mx-5 mb-3 flex items-center gap-2 px-4 py-2.5 bg-[#1877F2]/8 dark:bg-[#1877F2]/10 border border-[#1877F2]/20 rounded-2xl">
            <ClipboardPaste size={15} className="text-[#1877F2] shrink-0" strokeWidth={2} />
            <p className="text-xs text-[#1877F2] font-normal uyghur-text leading-relaxed text-right">
              {t('share.pasteHint')}
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="grid grid-cols-3 gap-2 p-5 pt-0">
          <button
            onClick={handleCopy}
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-[#1a1a1a] dark:text-slate-200 rounded-2xl text-xs font-normal transition-all active:scale-95"
          >
            {copied ? <Check size={15} className="text-emerald-500" strokeWidth={2.5} /> : <Copy size={15} strokeWidth={2.5} />}
            <span className="uyghur-text whitespace-nowrap">
              {copied ? t('share.contentCopied') : t('share.copyContent')}
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
            className="flex items-center justify-center gap-1.5 px-3 py-2.5 bg-[#1877F2] hover:bg-[#166fe5] text-white rounded-2xl text-xs font-normal transition-all active:scale-95 shadow-md shadow-[#1877F2]/30"
          >
            {fbClicked
              ? <><Check size={15} strokeWidth={2.5} /><span className="uyghur-text whitespace-nowrap">{t('share.textCopied')}</span></>
              : <><FacebookIcon /><span className="uyghur-text whitespace-nowrap">{t('share.postToFacebook')}</span></>
            }
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
