import { Book, Conversation, Message } from '@shared/types';
import {
  AlertTriangle,
  BookOpen,
  Bot,
  ChevronDown,
  Globe,
  History,
  Loader2,
  LogIn,
  MessageSquare,
  PanelLeftClose,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  Send,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  User,
  X,
} from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { CHARACTERS, DEFAULT_CHARACTER_ID } from '../../constants/characters';
import { useAppContext } from '../../context/AppContext';
import { useAuth } from '../../hooks/useAuth';
import { AgentStep } from '../../hooks/useChat';
import { useI18n } from '../../i18n/I18nContext';
import { translations } from '../../i18n/i18n';
import { OAuthButtonGroup } from '../auth/AuthButton';
import { MarkdownContent } from '../common/MarkdownContent';
import { AgentThinkingSteps } from './AgentThinkingSteps';
import { ReferenceModal } from './ReferenceModal';

const CHAR_INTERVAL = 55;   // ms per character
const HOLD_AFTER_TYPED = 1800; // ms to hold the full phrase before switching
const FADE_DURATION = 350;  // ms fade out

function TypingCarousel({ className, fontSize }: { className?: string; fontSize?: number }) {
  const { language } = useI18n();
  const phrases: string[] = (translations[language] as any)?.chat?.thinkingPhrases ?? [];
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [charIdx, setCharIdx] = useState(0);
  const [visible, setVisible] = useState(true);

  const phrase = phrases[phraseIdx] ?? '';

  // Character-by-character typing, then hold, then fade and advance
  useEffect(() => {
    if (!phrases.length) return;
    if (charIdx < phrase.length) {
      const t = setTimeout(() => setCharIdx(i => i + 1), CHAR_INTERVAL);
      return () => clearTimeout(t);
    }
    // Fully typed — hold, then fade out and switch
    const t = setTimeout(() => {
      setVisible(false);
      setTimeout(() => {
        setPhraseIdx(i => (i + 1) % phrases.length);
        setCharIdx(0);
        setVisible(true);
      }, FADE_DURATION);
    }, HOLD_AFTER_TYPED);
    return () => clearTimeout(t);
  }, [charIdx, phrase, phrases.length]);

  const displayed = phrase.slice(0, charIdx);
  const isTyping = charIdx < phrase.length;

  return (
    <span
      key={phraseIdx}
      dir="rtl"
      className={`uyghur-text transition-opacity ${visible ? 'opacity-100' : 'opacity-0'} ${className ?? ''}`}
      style={{ transitionDuration: `${FADE_DURATION}ms`, ...(fontSize ? { fontSize: `${fontSize}px` } : {}) }}
    >
      {displayed}
      {isTyping && (
        <span
          className="inline-block w-[2px] bg-current align-middle mx-px animate-[blink_0.9s_step-end_infinite]"
          style={{ height: '1em' }}
        />
      )}
    </span>
  );
}

interface ChatInterfaceProps {
  type: 'book' | 'global';
  books?: Book[];
  totalReady?: number;
  chatMessages: Message[];
  chatInput: string;
  setChatInput: (input: string) => void;
  onSendMessage: () => void;
  isChatting: boolean;
  streamingMessage?: string;
  streamingPartialResult?: boolean;

  bookId?: string;
  bookTitle?: string;
  bookAuthor?: string;
  agentSteps?: AgentStep[];
  currentPage?: number | null;
  chatContainerRef: React.RefObject<HTMLDivElement>;
  usageStatus?: { usage: number, limit: number | null, hasReachedLimit: boolean } | null;
  selectedCharacterId?: string;
  setSelectedCharacterId?: (id: string) => void;
  submitFeedback?: (messageIndex: number, feedback: 'positive' | 'negative') => void;

  conversationId?: string;
  conversations?: Conversation[];
  isLoadingConversations?: boolean;
  isLoadingMessages?: boolean;
  onSelectConversation?: (conversationId: string) => void;
  onStartNewChat?: () => void;
  onDeleteConversation?: (conversationId: string) => void;

  onHideChat?: () => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  type,
  chatMessages,
  chatInput,
  setChatInput,
  onSendMessage,
  isChatting,
  streamingMessage = '',
  streamingPartialResult = false,

  agentSteps = [],
  chatContainerRef,
  usageStatus,
  selectedCharacterId,
  setSelectedCharacterId,
  submitFeedback,

  conversationId,
  conversations = [],
  isLoadingConversations = false,
  isLoadingMessages = false,
  onSelectConversation,
  onStartNewChat,
  onDeleteConversation,
  onHideChat,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const { fontSize, setModal } = useAppContext();
  const isGlobal = type === 'global';
  const chatFontSize = fontSize;
  const [selectedReference, setSelectedReference] = React.useState<{ bookId: string; pageNums: number[]; isGraph?: boolean; graphQuery?: string } | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(() => typeof window !== 'undefined' ? window.innerWidth >= 1024 : false);
  const inputRef = useRef<HTMLInputElement>(null);
  const readerOuterRef = useRef<HTMLDivElement>(null);


  const focusInput = React.useCallback(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, []);

  const handleStartNewChat = () => {
    onStartNewChat?.();
    if (window.innerWidth < 1024) {
      setIsHistoryOpen(false);
    }
    focusInput();
  };

  useEffect(() => {
    focusInput();
  }, [focusInput, conversationId]);
  const globalOuterRef = useRef<HTMLDivElement>(null);
  const [isCharMenuOpen, setIsCharMenuOpen] = React.useState(false);
  const charMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isCharMenuOpen) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (charMenuRef.current && !charMenuRef.current.contains(e.target as Node)) {
        setIsCharMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('touchstart', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('touchstart', close);
    };
  }, [isCharMenuOpen]);

  // Auto-submit when opened from home page search with a pre-filled question.
  // Deferred via setTimeout so useChat's view-change effect (which resets the
  // abort controller) finishes before we start the stream.
  useEffect(() => {
    if (!isGlobal || !chatInput.trim() || chatMessages.length > 0) return;
    const timer = setTimeout(onSendMessage, 0);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // iOS fix: keyboard overlaps the chat. Cap maxHeight to the visible viewport area
  // so the flex column shrinks and keeps the input above the keyboard.
  // rect.top is captured once when the keyboard first opens so that subsequent
  // scroll events (iOS scrolls the page as the keyboard animates) don't cause
  // the available height to recalculate and produce a bounce animation.
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const capturedTop = new Map<HTMLElement, number>();
    const update = () => {
      const keyboardHeight = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      for (const ref of [readerOuterRef, globalOuterRef]) {
        if (!ref.current) continue;
        if (keyboardHeight > 100) {
          if (!capturedTop.has(ref.current)) {
            capturedTop.set(ref.current, ref.current.getBoundingClientRect().top);
          }
          const top = capturedTop.get(ref.current)!;
          const available = viewport.height - Math.max(0, top);
          ref.current.style.maxHeight = `${Math.max(100, available)}px`;
        } else {
          capturedTop.delete(ref.current);
          ref.current.style.maxHeight = '';
        }
      }
    };
    viewport.addEventListener('resize', update);
    viewport.addEventListener('scroll', update);
    return () => {
      viewport.removeEventListener('resize', update);
      viewport.removeEventListener('scroll', update);
    };
  }, []);

  const handleReferenceClick = (bookId: string, pageNums: number[], isGraph?: boolean, graphQuery?: string) => {
    setSelectedReference({ bookId, pageNums, isGraph, graphQuery });
  };

  const currentCharacter = isGlobal
    ? (CHARACTERS.find(c => c.id === selectedCharacterId) || CHARACTERS[0])
    : (CHARACTERS.find(c => c.id === DEFAULT_CHARACTER_ID) || CHARACTERS[0]);

  if (isGlobal) {
    return (
      <div ref={globalOuterRef} className="w-full lg:max-w-7xl lg:mx-auto flex flex-col lg:flex-row-reverse gap-3 md:gap-4 lg:gap-6 px-3 py-3 sm:px-6 md:px-0 lg:py-4 flex-grow min-h-0" dir="rtl" lang="ug">

        {/* Left / Main Chat Window Area */}
        <div className="glass-panel border border-white/60 rounded-[24px] sm:rounded-[40px] flex flex-col overflow-hidden flex-1 min-h-0">
          {/* Header Bar with Mobile History Toggle */}
          <div className="px-4 py-3 sm:px-6 sm:py-3.5 border-b border-slate-200/50 dark:border-slate-800/50 flex items-center justify-between bg-slate-50/40 dark:bg-slate-900/40 min-h-[58px] sm:min-h-[64px]">
            <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
              <div className="p-2 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shrink-0">
                <Bot size={20} />
              </div>
              <span className="font-semibold text-sm sm:text-base text-slate-800 dark:text-slate-100 uyghur-text truncate">
                {t('chat.globalAssistant')}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {!isHistoryOpen && (
                <button
                  onClick={() => setIsHistoryOpen(true)}
                  className="lg:hidden p-2 bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 rounded-xl transition-all shadow-sm"
                  title={t('chat.historyTitle')}
                >
                  <History size={20} />
                </button>
              )}
            </div>
          </div>

          {/* Messages */}
          <div
            ref={chatContainerRef}
            className="flex-1 overflow-y-auto custom-scrollbar-mini space-y-4 md:space-y-6 px-3 sm:px-5 lg:px-6 py-4 sm:py-6 flex flex-col"
          >
            {isLoadingMessages ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-3">
                <Loader2 className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" size={32} />
                <span className="text-sm font-normal uyghur-text">{t('common.loading')}</span>
              </div>
            ) : chatMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-12">
                <div className="w-24 h-24 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 rounded-[36px] flex items-center justify-center mb-6 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-lg relative group overflow-hidden">
                  <div className="absolute inset-0 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 animate-pulse" />
                  <Bot size={56} className="text-[#0369a1] dark:text-[#38bdf8] relative z-10 transition-transform group-hover:scale-110" strokeWidth={2.5} />
                </div>
                <h4 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] dark:text-slate-100 mb-4">{t('chat.welcome.title')}</h4>
                <p className="text-slate-500 dark:text-slate-400 font-normal max-w-lg leading-loose text-base">{t('chat.welcome.message')}</p>
                <p className="text-slate-400 dark:text-slate-500 font-normal max-w-lg leading-loose text-sm mt-4 italic border-t border-slate-200 dark:border-slate-800 pt-4">{t('chat.welcome.disclaimer')}</p>
              </div>
            ) : (
              chatMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex flex-col gap-1.5 md:gap-2 ${
                    msg.role === 'user' ? 'items-start' : 'items-end'
                  }`}
                >
                  <div dir="ltr" style={{ fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }} className={`w-8 h-8 md:w-10 md:h-10 shrink-0 rounded-2xl flex items-center justify-center shadow-md transition-all transform hover:scale-105 ${msg.role === 'user' ? 'bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700/80 text-[#0369a1] dark:text-[#38bdf8]' : 'bg-[#0369a1] text-white shadow-[#0369a1]/20'}`}>
                    {msg.role === 'user' ? (
                      <User size={18} className="md:w-5 md:h-5" strokeWidth={2.5} />
                    ) : (
                      <span className="text-lg md:text-xl leading-none flex items-center justify-center select-none" style={{ lineHeight: 1 }}>
                        {CHARACTERS.find(c => c.id === msg.characterId)?.avatar_emoji || currentCharacter.avatar_emoji}
                      </span>
                    )}
                  </div>

                  <div className={`flex flex-col min-w-0 ${msg.role === 'user' ? 'max-w-[85%] sm:max-w-xl items-start' : 'w-full items-end'}`}>
                    <div
                      className={`px-5 py-4 rounded-3xl shadow-sm transition-all text-[#1a1a1a] dark:text-slate-100 ${
                        msg.role === 'user'
                          ? 'rounded-tr-none bg-white/90 dark:bg-slate-800/90 border border-slate-200/80 dark:border-slate-700/60'
                          : 'rounded-tl-none bg-[#0369a1] dark:bg-[#0369a1] text-white shadow-md shadow-[#0369a1]/10 w-full'
                      }`}
                      style={{ fontSize: `${chatFontSize}px`, lineHeight: '1.8' }}
                    >
                      <MarkdownContent
                        content={msg.text}
                        onReferenceClick={handleReferenceClick}
                        className={msg.role === 'user' ? 'uyghur-text' : 'text-white uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50'}
                        style={{ fontSize: `${chatFontSize}px` }}
                      />
                    </div>
                    {msg.partialResult && (
                      <div className="mt-1 flex items-start gap-1.5 text-amber-700 bg-amber-50 border border-amber-200/80 px-3 py-2 rounded-2xl text-xs max-w-md shadow-sm font-normal uyghur-text animate-in fade-in">
                        <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                        <span>{t('chat.partialResultsWarning')}</span>
                      </div>
                    )}
                    {msg.role === 'model' && submitFeedback && (
                      <div dir="ltr" className="mt-1 flex items-center gap-0.5 px-1">
                        <button
                          onClick={() => submitFeedback(idx, 'positive')}
                          disabled={!!msg.feedback}
                          title="جاۋاب ياقتى"
                          className={`p-1.5 rounded-lg transition-all disabled:cursor-default ${msg.feedback === 'positive' ? 'text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10' : 'text-slate-300 dark:text-slate-400 hover:text-emerald-400 hover:bg-emerald-50/60 dark:hover:bg-emerald-500/10'}`}
                        >
                          <ThumbsUp size={18} strokeWidth={2} />
                        </button>
                        <button
                          onClick={() => submitFeedback(idx, 'negative')}
                          disabled={!!msg.feedback}
                          title="جاۋاب ياقمىدى"
                          className={`p-1.5 rounded-lg transition-all disabled:cursor-default ${msg.feedback === 'negative' ? 'text-red-500 bg-red-50 dark:bg-red-500/10' : 'text-slate-300 dark:text-slate-400 hover:text-red-400 hover:bg-red-50/60 dark:hover:bg-red-500/10'}`}
                        >
                          <ThumbsDown size={18} strokeWidth={2} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}

            {isChatting && (
              <div className="flex flex-col gap-1.5 md:gap-2 items-end">
                <div dir="ltr" style={{ fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }} className="w-8 h-8 md:w-10 md:h-10 shrink-0 rounded-2xl bg-[#0369a1] text-white flex items-center justify-center shadow-lg shadow-[#0369a1]/30">
                  <span className="text-lg md:text-xl leading-none flex items-center justify-center select-none" style={{ lineHeight: 1 }}>
                    {currentCharacter.avatar_emoji}
                  </span>
                </div>
                {streamingMessage ? (
                  <div className="flex flex-col w-full min-w-0 items-end">
                    <div
                      className="px-5 py-4 rounded-3xl rounded-tl-none shadow-md shadow-[#0369a1]/10 bg-[#0369a1] text-white w-full"
                      style={{ fontSize: `${chatFontSize}px`, lineHeight: '1.8' }}
                    >
                      <MarkdownContent
                        content={streamingMessage}
                        onReferenceClick={handleReferenceClick}
                        className="text-white/90 uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                        style={{ fontSize: `${chatFontSize}px` }}
                      />
                      <div dir="ltr" className="flex gap-[3px] mt-1.5 items-end">
                        <span className="w-1 h-1 rounded-full bg-white/60 animate-bounce" style={{ animationDelay: '0ms' }} />
                        <span className="w-1 h-1 rounded-full bg-white/60 animate-bounce" style={{ animationDelay: '120ms' }} />
                        <span className="w-1 h-1 rounded-full bg-white/60 animate-bounce" style={{ animationDelay: '240ms' }} />
                      </div>
                    </div>
                    {streamingPartialResult && (
                      <div className="mt-1 flex items-start gap-1.5 text-amber-700 bg-amber-50 border border-amber-200/80 px-3 py-2 rounded-2xl text-xs max-w-md shadow-sm font-normal uyghur-text animate-in fade-in">
                        <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                        <span>{t('chat.partialResultsWarning')}</span>
                      </div>
                    )}
                  </div>
                ) : agentSteps.length > 0 ? (
                  <div className="w-full min-w-0">
                    <AgentThinkingSteps steps={agentSteps} fontSize={chatFontSize} compact />
                  </div>
                ) : (
                  <div className="bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-5 py-4 rounded-3xl rounded-tl-none flex gap-2 items-center border border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-sm">
                    <TypingCarousel className="text-[#0369a1] dark:text-[#38bdf8]" fontSize={chatFontSize} />
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Input container */}
          <div className="relative flex-shrink-0 p-2 sm:p-3 bg-white/80 dark:bg-slate-900/80 backdrop-blur-2xl border-t border-slate-200/60 dark:border-slate-800/60 shadow-xl transition-all focus-within:border-[#0369a1] dark:focus-within:border-[#38bdf8]">
            {isAuthenticated ? (
              <div className="flex flex-col gap-1">
                {usageStatus?.hasReachedLimit ? (
                  <div className="py-2 px-4 text-center">
                    <p className="text-xs text-red-500 font-normal bg-red-50 py-2 rounded-xl border border-red-50/50">
                      {t('chat.limitReached')}
                    </p>
                  </div>
                ) : (
                  <>
                    <input
                      type="text"
                      placeholder={usageStatus && usageStatus.limit !== null
                        ? t('chat.inputPlaceholderWithLimit', { usage: usageStatus.usage, limit: usageStatus.limit })
                        : t('chat.inputPlaceholderBook')}
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && !isChatting && !usageStatus?.hasReachedLimit && onSendMessage()}
                      onFocus={(e) => { const el = e.target; setTimeout(() => el?.scrollIntoView({ block: 'nearest' }), 300); }}
                      ref={inputRef}
                      className="w-full bg-transparent border-none py-2.5 sm:py-3.5 pl-[60px] sm:pl-[72px] pr-4 sm:pr-6 font-normal text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-300 dark:placeholder:text-slate-500 outline-none uyghur-text"
                      style={{ fontSize: `${chatFontSize}px`, lineHeight: 'normal' }}
                      dir="rtl"
                      disabled={usageStatus?.hasReachedLimit}
                      maxLength={500}
                    />
                    <button
                      onClick={onSendMessage}
                      data-testid="send-button"
                      disabled={isChatting || !chatInput.trim() || usageStatus?.hasReachedLimit}
                      className="absolute left-3.5 sm:left-5 top-1/2 -translate-y-1/2 flex items-center justify-center w-9 h-9 sm:w-10 sm:h-10 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl sm:rounded-2xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 hover:scale-105 active:scale-90 transition-all disabled:opacity-30"
                    >
                      <Send size={18} strokeWidth={2.5} className="sm:w-5 sm:h-5" />
                    </button>
                  </>
                )}
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2 px-4 py-2.5 sm:py-3 min-h-[52px] sm:min-h-[60px]">
                <p className="text-[#1a1a1a] dark:text-slate-200 font-normal text-[11px] sm:text-sm leading-relaxed text-right">{t('auth.signInToUseChat')}</p>
                <OAuthButtonGroup align="up" side="left" className="shrink-0" />
              </div>
            )}
          </div>
        </div>

        {/* Mobile Slide-Over Drawer Backdrop */}
        {isHistoryOpen && (
          <div
            className="lg:hidden fixed top-[72px] sm:top-[88px] bottom-0 inset-x-0 bg-black/60 backdrop-blur-sm z-40 animate-in fade-in"
            onClick={() => setIsHistoryOpen(false)}
          />
        )}

        {/* Conversation History Side Panel (Desktop inline + Mobile slide-over drawer) */}
        <div
          className={`flex flex-col overflow-hidden bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl border border-white/60 dark:border-slate-800/80 shrink-0 shadow-xl transition-all duration-300 ${
            isHistoryOpen
              ? 'fixed top-[72px] sm:top-[88px] bottom-0 right-0 z-50 w-80 max-w-[85vw] rounded-none sm:rounded-l-[32px] border-y-0 border-r-0 lg:static lg:w-72 xl:w-80 lg:h-auto lg:rounded-[32px] lg:border animate-in slide-in-from-right'
              : 'hidden lg:flex lg:w-16 lg:h-auto lg:rounded-[32px] lg:border'
          }`}
        >
          {/* Card Header */}
          <div className="px-4 py-3 sm:px-6 sm:py-3.5 border-b border-slate-200/50 dark:border-slate-800/50 flex items-center justify-between gap-2 bg-slate-50/40 dark:bg-slate-900/40 min-h-[58px] sm:min-h-[64px]">
            {isHistoryOpen ? (
              <>
                <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
                  <div className="p-2 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shrink-0">
                    <History size={20} />
                  </div>
                  <span className="font-semibold text-sm sm:text-base text-slate-800 dark:text-slate-100 truncate uyghur-text">
                    {t('chat.historyTitle')}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {onStartNewChat && (
                    <button
                      onClick={handleStartNewChat}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 hover:opacity-90 rounded-xl text-xs font-medium transition-all shadow-sm uyghur-text"
                      title={t('chat.newChat')}
                    >
                      <Plus size={14} strokeWidth={2.5} />
                      <span>{t('chat.newChat')}</span>
                    </button>
                  )}
                  <button
                    onClick={() => setIsHistoryOpen(false)}
                    className="p-2 bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 rounded-xl transition-all shadow-sm"
                    title="Close"
                  >
                    <X size={20} className="lg:hidden" />
                    <PanelRightClose size={20} className="hidden lg:block" />
                  </button>
                </div>
              </>
            ) : (
              <div className="flex flex-col items-center w-full gap-3 py-1">
                <button
                  onClick={() => setIsHistoryOpen(true)}
                  className="p-2 bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 rounded-xl transition-all shadow-sm"
                  title={t('chat.historyTitle')}
                >
                  <PanelRightOpen size={20} />
                </button>
                {onStartNewChat && (
                  <button
                    onClick={handleStartNewChat}
                    className="p-2 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl transition-all shadow-sm"
                    title={t('chat.newChat')}
                  >
                    <Plus size={18} strokeWidth={2.5} />
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Card Body */}
          {isHistoryOpen && (
            <div className="flex-1 overflow-y-auto custom-scrollbar-mini p-0 min-h-0 divide-y divide-slate-100 dark:divide-slate-800/40">
              {isLoadingConversations ? (
                <div className="flex flex-col items-center justify-center py-10 text-slate-400 gap-2">
                  <Loader2 className="animate-spin text-[#0369a1] dark:text-[#38bdf8]" size={24} />
                  <span className="text-xs text-slate-400">{t('common.loading')}</span>
                </div>
              ) : !isAuthenticated ? (
                <div className="flex flex-col items-center justify-center py-8 px-4 text-center text-xs text-slate-500 dark:text-slate-400 gap-3">
                  <History size={36} className="text-slate-300 dark:text-slate-600" />
                  <p className="leading-relaxed uyghur-text">{t('chat.loginToSaveHistory')}</p>
                </div>
              ) : conversations.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center text-slate-400 gap-2">
                  <MessageSquare size={36} className="opacity-40" />
                  <span className="text-xs font-normal uyghur-text">{t('chat.noHistory')}</span>
                </div>
              ) : (
                conversations.map((conv) => {
                  const isActive = conversationId === conv.id;
                  const isReaderChat = !conv.isGlobal || Boolean(conv.bookId);
                  const displayTitle = conv.bookTitle
                    ? t('chat.bookAboutTitle', { title: conv.bookTitle })
                    : (conv.title || 'سۆھبەت');

                  return (
                    <div
                      key={conv.id}
                      onClick={() => {
                        onSelectConversation?.(conv.id);
                        if (window.innerWidth < 1024) {
                          setIsHistoryOpen(false);
                        }
                      }}
                      className={`group relative flex items-center justify-between px-4 py-3 cursor-pointer transition-all ${
                        isActive
                          ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/15'
                          : 'hover:bg-slate-100/80 dark:hover:bg-slate-800/50'
                      }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <div
                          title={isReaderChat ? 'Reader Chat' : 'Global Chat'}
                          className={`p-1.5 rounded-lg shrink-0 ${
                            isActive
                              ? 'bg-[#0369a1] text-white dark:bg-[#38bdf8] dark:text-slate-950'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-400'
                          }`}
                        >
                          {isReaderChat ? <BookOpen size={14} /> : <Globe size={14} />}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className={`text-xs sm:text-sm font-normal truncate uyghur-text ${isActive ? 'font-medium text-[#0369a1] dark:text-[#38bdf8]' : 'text-slate-700 dark:text-slate-200'}`}>
                            {displayTitle}
                          </p>
                          <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5 font-normal">
                            {new Date(conv.updatedAt).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      {onDeleteConversation && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setModal({
                              isOpen: true,
                              title: t('chat.deleteConversation'),
                              message: t('chat.confirmDeleteConversation'),
                              type: 'confirm',
                              destructive: true,
                              confirmText: t('common.delete'),
                              onConfirm: async () => {
                                setModal((prev: any) => ({ ...prev, isLoading: true }));
                                try {
                                  await onDeleteConversation(conv.id);
                                } finally {
                                  setModal((prev: any) => ({ ...prev, isOpen: false, isLoading: false }));
                                }
                              },
                            });
                          }}
                          title={t('chat.deleteConversation')}
                          className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-50 dark:hover:bg-red-950/40 text-slate-400 hover:text-red-500 rounded-lg transition-all shrink-0"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {selectedReference && (
          <ReferenceModal
            isOpen={!!selectedReference}
            onClose={() => setSelectedReference(null)}
            bookId={selectedReference.bookId}
            pageNumbers={selectedReference.pageNums}
          />
        )}
      </div>
    );
  }

  // Sidebar (Reader) Chat Version
  return (
    <div ref={readerOuterRef} className="flex-1 min-h-0 flex flex-col relative overflow-hidden" dir="rtl" lang="ug">
      {/* Reader Chat Header Toolbar — matches book content card header styling */}
      <div className="flex-shrink-0 px-3 sm:px-6 py-2 sm:py-4 border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex flex-row items-center justify-between gap-1 sm:gap-4 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm">
        {/* Right in RTL: Bot icon in blue badge + Assistant Title */}
        <div className="flex items-center gap-2 sm:gap-4 min-w-0">
          <div className="flex items-center justify-center min-w-[40px] min-h-[40px] w-10 h-10 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shrink-0">
            <Bot size={20} />
          </div>
          <div className="min-w-0 flex flex-col justify-center">
            <h2
              className="font-bold text-[#1a1a1a] dark:text-slate-100 uyghur-text truncate"
              style={{ fontSize: '18px' }}
            >
              {t('chat.bookAssistant')}
            </h2>
          </div>
        </div>

        {/* Left in RTL: Action controls */}
        <div className="flex items-center gap-0.5 sm:gap-2 shrink-0">
          {onHideChat && (
            <button
              onClick={onHideChat}
              className="hidden xl:flex items-center justify-center p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 shadow-sm"
              title={t('reader.hideChat')}
            >
              <PanelLeftClose size={18} className="sm:w-5 sm:h-5" />
            </button>
          )}
          {(conversationId || chatMessages.length > 0) && (
            <button
              onClick={() => {
                setModal({
                  isOpen: true,
                  title: t('chat.deleteConversation'),
                  message: t('chat.confirmDeleteConversation'),
                  type: 'confirm',
                  destructive: true,
                  confirmText: t('common.delete'),
                  onConfirm: async () => {
                    setModal((prev: any) => ({ ...prev, isLoading: true }));
                    try {
                      if (conversationId && onDeleteConversation) {
                        await onDeleteConversation(conversationId);
                      } else {
                        onStartNewChat?.();
                      }
                    } finally {
                      setModal((prev: any) => ({ ...prev, isOpen: false, isLoading: false }));
                    }
                  },
                });
              }}
              title={t('chat.deleteConversation')}
              aria-label={t('chat.deleteConversation')}
              className="flex items-center justify-center p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all bg-white/60 dark:bg-slate-800/80 border border-red-200 dark:border-red-900/30 text-red-400 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/20 hover:text-red-500 dark:hover:text-red-400 shadow-sm"
            >
              <Trash2 size={18} className="sm:w-5 sm:h-5" />
            </button>
          )}
        </div>
      </div>

      <div
        ref={chatContainerRef}
        className="flex-grow overflow-y-auto space-y-6 custom-scrollbar-mini p-4 sm:p-6 flex flex-col"
      >
        {chatMessages.length === 0 && (
          <div className="flex-grow flex flex-col justify-center py-10">
            {!isAuthenticated ? (
              <div className="flex flex-col items-center justify-center gap-5 py-8 px-4">
                <div className="p-4 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 rounded-[28px]">
                  <LogIn className="text-[#0369a1] dark:text-[#38bdf8] w-10 h-10" strokeWidth={1.5} />
                </div>
                <p className="text-sm text-[#94a3b8] dark:text-slate-400 font-normal text-center leading-loose">
                  {t('auth.signInMessage')}
                </p>
              </div>
            ) : (
              <div className="text-center py-12 px-8 bg-white/40 dark:bg-slate-900/40 border-2 border-dashed border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-[32px] flex flex-col items-center justify-center gap-4 opacity-60">
                <Bot size={48} className="text-[#0369a1] dark:text-[#38bdf8]" strokeWidth={1} />
                <p
                  className="font-normal leading-loose text-[#1a1a1a] dark:text-slate-100"
                  style={{ fontSize: `${chatFontSize}px` }}
                >
                  {t('chat.bookAssistantWelcome')}
                </p>
              </div>
            )}
          </div>
        )}
        {chatMessages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex flex-col gap-1.5 ${
              msg.role === 'user' ? 'items-start' : 'items-end'
            }`}
          >
            <div dir="ltr" style={{ fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }} className={`w-9 h-9 rounded-xl shrink-0 flex items-center justify-center text-sm shadow-sm ${msg.role === 'user' ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8]' : 'bg-[#0369a1] text-white'
              }`}>
              {msg.role === 'user' ? (
                <User size={18} strokeWidth={2.5} />
              ) : (
                <span className="text-lg leading-none flex items-center justify-center select-none" style={{ lineHeight: 1 }}>
                  {CHARACTERS.find(c => c.id === msg.characterId)?.avatar_emoji || currentCharacter.avatar_emoji || '🤖'}
                </span>
              )}
            </div>
            <div className={`flex flex-col gap-1.5 min-w-0 ${msg.role === 'user' ? 'max-w-[85%] items-start' : 'w-full items-end'}`}>
              <div
                className={`px-4 py-3 rounded-2xl font-normal uyghur-text shadow-sm ${msg.role === 'user'
                  ? 'rounded-tr-none bg-white/90 dark:bg-slate-800/90 border border-slate-200/60 dark:border-slate-700/60 text-[#1a1a1a] dark:text-slate-100'
                  : 'rounded-tl-none bg-[#0369a1] dark:bg-[#0369a1] text-white shadow-md shadow-[#0369a1]/10 w-full'
                  }`}
                style={{ fontSize: `${chatFontSize}px`, lineHeight: '1.8' }}
              >
                {msg.role === 'user' ? (
                  msg.text
                ) : (
                  <MarkdownContent
                    content={msg.text}
                    onReferenceClick={handleReferenceClick}
                    className="text-white uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                    style={{ fontSize: `${chatFontSize}px` }}
                  />
                )}
              </div>
              {msg.role === 'model' && msg.partialResult && (
                <div className="mt-1 flex items-start gap-1.5 text-amber-700 bg-amber-50 border border-amber-200/80 px-3 py-2 rounded-2xl text-xs max-w-md shadow-sm font-normal uyghur-text animate-in fade-in">
                  <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                  <span>{t('chat.partialResultsWarning')}</span>
                </div>
              )}
              {msg.role === 'model' && !isChatting && (
                <div dir="ltr" className="flex gap-0.5 items-center px-1">
                  {msg.evalId !== undefined && (
                    <>
                      <button
                        onClick={() => submitFeedback?.(idx, 'positive')}
                        disabled={!!msg.feedback}
                        title="👍"
                        className={`p-1.5 rounded-lg transition-all disabled:cursor-default ${msg.feedback === 'positive' ? 'text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10' : 'text-slate-300 dark:text-slate-400 hover:text-emerald-400 hover:bg-emerald-50/60 dark:hover:bg-emerald-500/10'}`}
                      >
                        <ThumbsUp size={18} strokeWidth={2} />
                      </button>
                      <button
                        onClick={() => submitFeedback?.(idx, 'negative')}
                        disabled={!!msg.feedback}
                        title="👎"
                        className={`p-1.5 rounded-lg transition-all disabled:cursor-default ${msg.feedback === 'negative' ? 'text-red-500 bg-red-50 dark:bg-red-500/10' : 'text-slate-300 dark:text-slate-400 hover:text-red-400 hover:bg-red-50/60 dark:hover:bg-red-500/10'}`}
                      >
                        <ThumbsDown size={18} strokeWidth={2} />
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {isChatting && (
          <div className="flex flex-col gap-1.5 items-end">
            <div dir="ltr" style={{ fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }} className="w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm bg-[#0369a1] text-white animate-pulse shrink-0">
              <span className="text-lg leading-none flex items-center justify-center select-none" style={{ lineHeight: 1 }}>
                {currentCharacter.avatar_emoji}
              </span>
            </div>
            {streamingMessage ? (
              <div className="flex flex-col gap-1.5 w-full min-w-0 items-end">
                <div
                  className={`px-4 py-3 rounded-2xl rounded-tl-none font-normal shadow-md shadow-[#0369a1]/10 bg-[#0369a1] text-white w-full uyghur-text transition-opacity duration-300 opacity-100`}
                  style={{ fontSize: `${chatFontSize}px`, lineHeight: '1.8' }}
                >
                  <MarkdownContent
                    content={streamingMessage}
                    onReferenceClick={handleReferenceClick}
                    className="text-white/90 uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                    style={{ fontSize: `${chatFontSize}px` }}
                  />
                  <div dir="ltr" className="flex gap-[3px] mt-1.5 items-end">
                    <span className="w-1 h-1 rounded-full bg-white/60 animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-1 h-1 rounded-full bg-white/60 animate-bounce" style={{ animationDelay: '120ms' }} />
                    <span className="w-1 h-1 rounded-full bg-white/60 animate-bounce" style={{ animationDelay: '240ms' }} />
                  </div>
                </div>
                {streamingPartialResult && (
                  <div className="mt-1 flex items-start gap-1.5 text-amber-700 bg-amber-50 border border-amber-200/80 px-3 py-2 rounded-2xl text-xs max-w-md shadow-sm font-normal uyghur-text animate-in fade-in">
                    <AlertTriangle size={14} className="shrink-0 mt-0.5" />
                    <span>{t('chat.partialResultsWarning')}</span>
                  </div>
                )}
              </div>
            ) : agentSteps.length > 0 ? (
              <div className="w-full min-w-0">
                <AgentThinkingSteps steps={agentSteps} fontSize={chatFontSize} compact />
              </div>
            ) : (
              <div className="bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-4 py-3 rounded-2xl rounded-tl-none flex gap-2 items-center border border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-sm">
                <TypingCarousel className="text-[#0369a1] dark:text-[#38bdf8]" fontSize={chatFontSize} />
              </div>
            )}
          </div>
        )}
      </div>

      <div className="p-2 sm:p-3 xl:p-4 pt-0 shrink-0">
        <div className="relative flex-shrink-0 p-1 sm:p-1.5 bg-white/80 dark:bg-slate-900/80 backdrop-blur-2xl border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-xl transition-all focus-within:border-[#0369a1] dark:focus-within:border-[#38bdf8] focus-within:ring focus-within:ring-[12px] focus-within:ring-[#0369a1]/5 dark:focus-within:ring-[#38bdf8]/5 rounded-[20px] md:rounded-[24px]">
          {isAuthenticated ? (
            <div className="flex flex-col gap-1">
              {usageStatus?.hasReachedLimit ? (
                <div className="py-2 px-4 text-center">
                  <p className="text-xs text-red-500 font-normal bg-red-50 py-2 rounded-xl border border-red-50/50">
                    {t('chat.limitReached')}
                  </p>
                </div>
              ) : (
                <>
                  <input
                    type="text"
                    placeholder={usageStatus && usageStatus.limit !== null
                      ? t('chat.inputPlaceholderWithLimit', { usage: usageStatus.usage, limit: usageStatus.limit })
                      : t('chat.inputPlaceholderBook')}
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && !isChatting && !usageStatus?.hasReachedLimit && onSendMessage()}
                    onFocus={(e) => { const el = e.target; setTimeout(() => el?.scrollIntoView({ block: 'nearest' }), 300); }}
                    ref={inputRef}
                    className="w-full bg-transparent border-none py-1.5 sm:py-2 pl-12 sm:pl-14 pr-3 sm:pr-4 font-normal text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-300 dark:placeholder:text-slate-500 outline-none uyghur-text"
                    style={{ fontSize: `${chatFontSize}px`, lineHeight: 'normal' }}
                    dir="rtl"
                    disabled={usageStatus?.hasReachedLimit}
                    maxLength={500}
                  />
                  <button
                    onClick={onSendMessage}
                    data-testid="send-button"
                    disabled={isChatting || !chatInput.trim() || usageStatus?.hasReachedLimit}
                    className="absolute left-2 sm:left-2.5 top-1/2 -translate-y-1/2 flex items-center justify-center w-8 h-8 sm:w-9 sm:h-9 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl sm:rounded-2xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 hover:scale-105 active:scale-90 transition-all disabled:opacity-30"
                  >
                    <Send size={16} strokeWidth={2.5} className="sm:w-4 sm:h-4" />
                  </button>
                </>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2 px-4 py-2.5 sm:py-3 min-h-[52px] sm:min-h-[60px]">
              <p className="text-[#1a1a1a] dark:text-slate-200 font-normal text-[11px] sm:text-sm leading-relaxed text-right">
                {t('auth.signInToUseChat')}
              </p>
              <OAuthButtonGroup align="up" side="left" className="shrink-0" />
            </div>
          )}
        </div>
      </div>
      {/* Reference Modal */}
      {selectedReference && (
        <ReferenceModal
          isOpen={!!selectedReference}
          onClose={() => setSelectedReference(null)}
          bookId={selectedReference?.bookId || ''}
          pageNumbers={selectedReference?.pageNums || []}
        />
      )}
    </div>
  );
};
