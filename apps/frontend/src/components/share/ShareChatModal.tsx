import { Check, ClipboardPaste, Copy, X } from 'lucide-react';
import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';

const MAX_Q = 400;
const MAX_A = 900;

interface ShareChatModalProps {
  question: string;
  answer: string;
  bookId?: string;
  bookTitle?: string;
  bookAuthor?: string;
  onClose: () => void;
}

const FacebookIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
  </svg>
);

export const ShareChatModal: React.FC<ShareChatModalProps> = ({ question, answer, bookId, bookTitle, bookAuthor, onClose }) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const [fbClicked, setFbClicked] = useState(false);

  const params = new URLSearchParams({ q: question.slice(0, MAX_Q), a: answer.slice(0, MAX_A) });
  if (bookId) params.set('book_id', bookId);
  const shareUrl = `${window.location.origin}/api/share/qa?${params.toString()}`;

  const qaText = [question, answer].filter(Boolean).join('\n\n');

  const handleCopy = async () => {
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFacebook = async () => {
    // Copy Q&A text to clipboard so user can paste into the FB post composer
    await navigator.clipboard.writeText(qaText).catch(() => {});

    const fbUrl = bookId
      ? `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(`${window.location.origin}/api/share/book/${bookId}`)}`
      : 'https://www.facebook.com/';

    window.open(fbUrl, '_blank', 'noopener,noreferrer,width=620,height=560');
    setFbClicked(true);
  };

  const previewAnswer = answer.length > 220 ? answer.slice(0, 220) + '…' : answer;

  return createPortal(
    <div className="fixed inset-0 z-[300] flex items-center justify-center p-4" dir="rtl">
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl"
        onClick={onClose}
      />

      <div
        className="relative z-10 w-full max-w-md bg-white/95 backdrop-blur-2xl rounded-[32px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] overflow-hidden border border-white/40 animate-scale-up"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-[#1877F2]/10 text-[#1877F2] rounded-xl">
              <FacebookIcon />
            </div>
            <span className="font-normal text-[#1a1a1a] uyghur-text">{t('share.shareQA')}</span>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-red-50 text-slate-300 hover:text-red-400 rounded-xl transition-all"
          >
            <X size={20} strokeWidth={2.5} />
          </button>
        </div>

        {/* Q&A preview */}
        <div className="p-5 pb-4 flex flex-col gap-3">
          <p className="text-xs text-slate-400 uppercase tracking-wider font-normal text-right">
            {t('share.previewLabel')}
          </p>

          {/* Book source chip */}
          {bookTitle && (
            <div className="flex items-center justify-end gap-2 px-3 py-2 bg-[#0369a1]/5 border border-[#0369a1]/10 rounded-2xl">
              <div className="flex flex-col items-end min-w-0">
                <span className="text-xs font-normal text-[#0369a1] uyghur-text leading-snug truncate max-w-full">{bookTitle}</span>
                {bookAuthor && (
                  <span className="text-[10px] text-slate-400 font-normal uyghur-text truncate max-w-full">{bookAuthor}</span>
                )}
              </div>
              <span className="text-base shrink-0">📖</span>
            </div>
          )}

          {/* Question bubble */}
          {question && (
            <div className="bg-white border border-[#0369a1]/10 rounded-2xl rounded-tr-none px-4 py-2.5 text-sm text-[#1a1a1a] font-normal uyghur-text leading-relaxed line-clamp-3">
              {question}
            </div>
          )}

          {/* Answer bubble */}
          <div className="bg-[#0369a1] rounded-2xl rounded-tl-none px-4 py-2.5 text-sm text-white font-normal uyghur-text leading-relaxed w-full">
            {previewAnswer}
          </div>
        </div>

        {/* Paste hint — shown after FB button is clicked */}
        {fbClicked && (
          <div className="mx-5 mb-3 flex items-center gap-2 px-4 py-2.5 bg-[#1877F2]/8 border border-[#1877F2]/20 rounded-2xl">
            <ClipboardPaste size={15} className="text-[#1877F2] shrink-0" strokeWidth={2} />
            <p className="text-xs text-[#1877F2] font-normal uyghur-text leading-relaxed text-right">
              {t('share.pasteHint')}
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 p-5 pt-0">
          <button
            onClick={handleCopy}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-[#1a1a1a] rounded-2xl text-sm font-normal transition-all active:scale-95"
          >
            {copied ? <Check size={16} className="text-emerald-500" strokeWidth={2.5} /> : <Copy size={16} strokeWidth={2.5} />}
            <span className="uyghur-text">
              {copied ? t('share.linkCopied') : t('share.copyLink')}
            </span>
          </button>

          <button
            onClick={handleFacebook}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-[#1877F2] hover:bg-[#166fe5] text-white rounded-2xl text-sm font-normal transition-all active:scale-95 shadow-lg shadow-[#1877F2]/30"
          >
            {fbClicked
              ? <><Check size={16} strokeWidth={2.5} /><span className="uyghur-text whitespace-nowrap">{t('share.textCopied')}</span></>
              : <><FacebookIcon /><span className="uyghur-text whitespace-nowrap">{t('share.postToFacebook')}</span></>
            }
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
