import {
  BookOpen,
  Calendar,
  Check,
  Coins,
  Copy,
  Eye,
  EyeOff,
  Globe,
  HelpCircle,
  Loader,
  MessageSquare,
  Sparkles,
  User,
  X,
} from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../i18n/I18nContext';
import { formatAnswerCost } from '../../utils/costUtils';
import { MarkdownContent } from '../common/MarkdownContent';

export interface RagQuestionDetail {
  id: number;
  question: string;
  answer?: string | null;
  retrievedContext?: string | null;
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
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
}

interface QuestionDetailModalProps {
  question: RagQuestionDetail;
  onClose: () => void;
  onToggleHomepage?: (question: RagQuestionDetail) => void;
  isToggling?: boolean;
}

function formatDate(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export const QuestionDetailModal: React.FC<QuestionDetailModalProps> = ({
  question,
  onClose,
  onToggleHomepage,
  isToggling = false,
}) => {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const handleCopyAnswer = async () => {
    if (!question.answer) return;
    try {
      await navigator.clipboard.writeText(question.answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy answer:', err);
    }
  };

  const totalTokens = (question.inputTokens || 0) + (question.outputTokens || 0);

  return createPortal(
    <div
      className="fixed inset-0 z-[300] flex items-center justify-center p-3 sm:p-6 md:p-8"
      dir="rtl"
    >
      {/* Backdrop */}
      <div
        className="modal-backdrop absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in"
        onClick={onClose}
      />

      {/* Dialog container */}
      <div
        className="relative z-10 w-full max-w-3xl max-h-[90vh] flex flex-col bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl rounded-3xl sm:rounded-[36px] shadow-[0_32px_128px_rgba(0,0,0,0.25)] dark:shadow-black/50 overflow-hidden border border-slate-200/80 dark:border-slate-800 animate-fade-in"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 sm:p-6 pb-4 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-2xl">
              <MessageSquare size={20} strokeWidth={2.2} />
            </div>
            <div>
              <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-slate-100 uyghur-text">
                {t('admin.questions.modalTitle')}
              </h3>
              <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-slate-500 dark:text-slate-400">
                {/* Scope Badge */}
                <span
                  className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium ${
                    question.isGlobal
                      ? 'bg-violet-50 dark:bg-violet-950/40 text-violet-600 dark:text-violet-400 border border-violet-100 dark:border-violet-900/40'
                      : 'bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400 border border-amber-100 dark:border-amber-900/40'
                  }`}
                >
                  {question.isGlobal ? <Globe size={11} /> : <BookOpen size={11} />}
                  <span>
                    {question.isGlobal
                      ? t('admin.questions.scopeGlobal')
                      : t('admin.questions.scopeBook')}
                  </span>
                </span>

                {/* Book Title */}
                {!question.isGlobal && (question.bookTitle || question.bookId) && (
                  <span
                    className="truncate max-w-[200px] sm:max-w-xs font-semibold text-amber-700 dark:text-amber-400/90 uyghur-text"
                    title={question.bookTitle || question.bookId || undefined}
                  >
                    📖 {question.bookTitle || question.bookId}
                  </span>
                )}

                {/* Timestamp */}
                <span className="flex items-center gap-1 font-mono text-[11px] text-slate-400">
                  <Calendar size={11} />
                  {formatDate(question.ts)}
                </span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            aria-label="Close"
            className="p-2 hover:bg-red-50 dark:hover:bg-red-950/20 text-slate-400 hover:text-red-500 dark:hover:text-red-400 rounded-2xl transition-all cursor-pointer"
          >
            <X size={20} strokeWidth={2.2} />
          </button>
        </div>

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto p-5 sm:p-7 space-y-6 [scrollbar-width:thin]">
          {/* Question Section */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs font-bold text-[#0369a1] dark:text-[#38bdf8] uppercase tracking-wider uyghur-text">
              <HelpCircle size={14} />
              <span>{t('admin.questions.questionLabel')}</span>
            </div>
            <div className="bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 border border-[#0369a1]/15 dark:border-[#38bdf8]/15 rounded-2xl p-4 sm:p-5 text-slate-900 dark:text-slate-100 font-bold text-base sm:text-lg uyghur-text leading-relaxed select-text shadow-xs">
              {question.question}
            </div>
          </div>

          {/* Answer Section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider uyghur-text">
                <Sparkles size={14} />
                <span>{t('admin.questions.answerLabel')}</span>
              </div>

              {question.answer && (
                <button
                  onClick={handleCopyAnswer}
                  title={t('admin.questions.copyAnswer')}
                  className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-slate-500 hover:text-[#0369a1] dark:hover:text-[#38bdf8] hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-all cursor-pointer"
                >
                  {copied ? (
                    <>
                      <Check size={13} className="text-emerald-500" />
                      <span className="text-emerald-500 uyghur-text">
                        {t('admin.questions.copied')}
                      </span>
                    </>
                  ) : (
                    <>
                      <Copy size={13} />
                      <span className="uyghur-text">{t('admin.questions.copyAnswer')}</span>
                    </>
                  )}
                </button>
              )}
            </div>

            {question.answer ? (
              <div className="bg-slate-50/90 dark:bg-slate-950/60 border border-slate-200/80 dark:border-slate-800/80 rounded-2xl p-4 sm:p-6 text-slate-800 dark:text-slate-100 text-sm sm:text-base uyghur-text leading-relaxed select-text shadow-xs">
                <MarkdownContent content={question.answer} />
              </div>
            ) : (
              <div className="p-8 text-center bg-slate-50/50 dark:bg-slate-950/30 border border-dashed border-slate-200 dark:border-slate-800 rounded-2xl text-slate-400 dark:text-slate-500 text-sm uyghur-text">
                {t('admin.questions.noAnswer')}
              </div>
            )}
          </div>

          {/* Metadata & Scores Bar */}
          <div className="bg-slate-50/70 dark:bg-slate-800/40 border border-slate-200/70 dark:border-slate-800/60 rounded-2xl p-4 sm:p-5 space-y-3 uyghur-text">
            <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
              {/* User Details */}
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 uyghur-text">
                <User size={13} className="shrink-0" />
                <span className="font-semibold">{t('admin.questions.colUser')}:</span>
                <span className="font-medium text-slate-800 dark:text-slate-200">
                  {question.userDisplayName || '—'}
                </span>
              </div>

              {/* User Feedback */}
              <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 uyghur-text">
                <span className="font-semibold">{t('admin.questions.colFeedback')}:</span>
                {question.userFeedback === 'positive' ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 border border-emerald-200/60 dark:border-emerald-900/40 text-xs font-medium uyghur-text">
                    👍 {t('admin.questions.feedbackPositive') || 'ئىجابىي'}
                  </span>
                ) : question.userFeedback === 'negative' ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400 border border-red-200/60 dark:border-red-900/40 text-xs font-medium uyghur-text">
                    👎 {t('admin.questions.feedbackNegative') || 'سەلبىي'}
                  </span>
                ) : (
                  <span className="text-slate-400">—</span>
                )}
              </div>

              {/* Cost & Tokens */}
              {question.costUsd !== undefined && question.costUsd > 0 && (
                <div className="inline-flex items-center gap-1.5 text-slate-600 dark:text-slate-400 text-xs font-medium uyghur-text">
                  <Coins size={13} className="text-amber-600 dark:text-amber-400 shrink-0" />
                  <span>{formatAnswerCost(question.costUsd, totalTokens, t)}</span>
                </div>
              )}
            </div>

            {/* Eval Scores (if completed) */}
            {question.evalStatus === 'completed' && (
              <div className="pt-3 border-t border-slate-200/60 dark:border-slate-700/50 flex flex-wrap items-center gap-2.5 sm:gap-3 text-xs">
                <span className="text-slate-500 dark:text-slate-400 font-semibold uyghur-text">
                  {t('admin.questions.colEvalQuality')}:
                </span>
                {question.faithfulnessScore !== null && (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 text-[11px] border border-emerald-200/60 dark:border-emerald-800/40 uyghur-text">
                    <span>{t('admin.questions.evalFaithfulness')}:</span>
                    <span className="font-mono tabular-nums ltr-text font-semibold">{question.faithfulnessScore.toFixed(2)}</span>
                  </span>
                )}
                {question.answerRelevanceScore !== null && (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 text-[11px] border border-blue-200/60 dark:border-blue-800/40 uyghur-text">
                    <span>{t('admin.questions.evalAnswerRelevance')}:</span>
                    <span className="font-mono tabular-nums ltr-text font-semibold">{question.answerRelevanceScore.toFixed(2)}</span>
                  </span>
                )}
                {question.contextPrecisionScore !== null && (
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-violet-50 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 text-[11px] border border-violet-200/60 dark:border-violet-800/40 uyghur-text">
                    <span>{t('admin.questions.evalContextPrecision')}:</span>
                    <span className="font-mono tabular-nums ltr-text font-semibold">{question.contextPrecisionScore.toFixed(2)}</span>
                  </span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-t border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/50">
          {onToggleHomepage ? (
            <button
              onClick={() => onToggleHomepage(question)}
              disabled={isToggling}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold transition-all cursor-pointer ${
                question.showOnHomepage
                  ? 'bg-amber-100 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/50'
                  : 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 hover:opacity-95'
              }`}
            >
              {isToggling ? (
                <Loader size={14} className="animate-spin" />
              ) : question.showOnHomepage ? (
                <EyeOff size={14} />
              ) : (
                <Eye size={14} />
              )}
              <span className="uyghur-text">
                {question.showOnHomepage
                  ? t('admin.questions.hideFromHome')
                  : t('admin.questions.showOnHome')}
              </span>
            </button>
          ) : (
            <div />
          )}

          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-slate-200 dark:bg-slate-800 hover:bg-slate-300 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs sm:text-sm font-semibold transition-all cursor-pointer uyghur-text"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
