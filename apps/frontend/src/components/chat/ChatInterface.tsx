import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, LogIn, ChevronDown } from 'lucide-react';
import { Message, Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { translations } from '../../i18n/i18n';
import { useAuth } from '../../hooks/useAuth';
import { useAppContext } from '../../context/AppContext';
import { OAuthButtonGroup } from '../auth/AuthButton';
import { MarkdownContent } from '../common/MarkdownContent';
import { ReferenceModal } from './ReferenceModal';
import { ProverbDisplay } from '../common/ProverbDisplay';
import { CHARACTERS, DEFAULT_CHARACTER_ID } from '../../constants/characters';

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
  currentPage?: number | null;
  onClose?: () => void;
  chatContainerRef: React.RefObject<HTMLDivElement>;
  usageStatus?: { usage: number, limit: number | null, hasReachedLimit: boolean } | null;
  selectedCharacterId?: string;
  setSelectedCharacterId?: (id: string) => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  type,
  chatMessages,
  chatInput,
  setChatInput,
  onSendMessage,
  isChatting,
  streamingMessage = '',
  chatContainerRef,
  usageStatus,
  selectedCharacterId,
  setSelectedCharacterId,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const { fontSize } = useAppContext();
  const isGlobal = type === 'global';
  const chatFontSize = fontSize;
  const [selectedReference, setSelectedReference] = React.useState<{ bookId: string; pageNums: number[] } | null>(null);
  const readerInputRef = useRef<HTMLInputElement>(null);
  const readerOuterRef = useRef<HTMLDivElement>(null);
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

  // iOS fix: keyboard overlaps the chat. Cap maxHeight to the visible viewport area
  // so the flex column shrinks and keeps the input above the keyboard.
  // keyboardHeight > 100 guards against firing on desktop or minor viewport changes.
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => {
      const keyboardHeight = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      for (const ref of [readerOuterRef, globalOuterRef]) {
        if (!ref.current) continue;
        if (keyboardHeight > 100) {
          const rect = ref.current.getBoundingClientRect();
          const available = viewport.height - Math.max(0, rect.top);
          ref.current.style.maxHeight = `${Math.max(100, available)}px`;
        } else {
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

  const handleReferenceClick = (bookId: string, pageNums: number[]) => {
    setSelectedReference({ bookId, pageNums });
  };

  const currentCharacter = isGlobal
    ? (CHARACTERS.find(c => c.id === selectedCharacterId) || CHARACTERS[0])
    : (CHARACTERS.find(c => c.id === DEFAULT_CHARACTER_ID) || CHARACTERS[0]);

  if (isGlobal) {
    return (
      <div className="w-full lg:max-w-5xl lg:mx-auto flex flex-col gap-3 md:gap-4 lg:gap-6 px-3 py-3 sm:px-6 md:px-0 lg:py-4 pb-24" dir="rtl" lang="ug">
        {/* Chat Header */}
        <div className="flex bg-white/60 backdrop-blur-2xl px-4 sm:px-8 py-3 sm:py-4 items-center justify-between border border-[#0369a1]/10 shadow-sm group" style={{ borderRadius: '32px' }}>
          <div className="flex items-center gap-3 sm:gap-5">
            <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 icon-shake">
              <Bot size={20} className="sm:w-7 sm:h-7" strokeWidth={2.5} />
            </div>
            <div>
              <h1
                className="font-normal text-[#1a1a1a] text-base sm:text-xl lg:text-2xl"
                style={{ fontSize: `${fontSize + 2}px` }}
              >
                {t('chat.globalAssistant')}
              </h1>
              <ProverbDisplay
                size="xs"
                keywords={t('proverbs.chat')}
                className="opacity-70 uppercase mt-[-2px] hidden sm:flex"
                defaultText={t('chat.subtitle')}
              />
            </div>
          </div>
        </div>

        {/* Unified Chat Card — messages + input, auto height, never shrinks */}
        <div className="glass-panel border border-white/60 rounded-[24px] sm:rounded-[40px] flex flex-col overflow-hidden min-h-[70vh]">
          {/* Messages */}
          <div
            ref={chatContainerRef}
            className="flex-1 space-y-4 md:space-y-8 px-4 sm:px-6 lg:px-10 py-6 sm:py-8 lg:py-12 flex flex-col"
          >
            {chatMessages.length === 0 ? (
              <div className="flex flex-col items-center justify-center text-center py-12">
                <div className="w-24 h-24 bg-[#0369a1]/10 rounded-[36px] flex items-center justify-center mb-6 border-2 border-[#0369a1]/10 shadow-lg relative group overflow-hidden">
                  <div className="absolute inset-0 bg-[#0369a1]/10 animate-pulse" />
                  <Bot size={56} className="text-[#0369a1] relative z-10 transition-transform group-hover:scale-110" strokeWidth={2.5} />
                </div>
                <h4 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] mb-4">{t('chat.welcome.title')}</h4>
                <p className="text-slate-500 font-normal max-w-lg leading-loose text-base">{t('chat.welcome.message')}</p>
                <p className="text-slate-400 font-normal max-w-lg leading-loose text-sm mt-4 italic border-t border-slate-200 pt-4">{t('chat.welcome.disclaimer')}</p>
              </div>
            ) : (
              chatMessages.map((msg, idx) => (
                <div key={idx} className={`flex gap-2 md:gap-4 lg:gap-6 ${msg.role === 'user' ? 'flex-col md:flex-row items-start' : 'flex-col items-end md:flex-row-reverse md:items-start'}`}>
                  <div className={`w-7 h-7 md:w-10 md:h-10 shrink-0 rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg transition-all transform hover:scale-110 ${msg.role === 'user' ? 'bg-white border-2 border-[#0369a1]/10 text-[#0369a1]' : 'bg-[#0369a1] text-white shadow-[#0369a1]/30'}`}>
                    {msg.role === 'user' ? (
                      <User size={16} className="md:w-5 md:h-5" strokeWidth={2.5} />
                    ) : (
                      <span className="text-lg md:text-xl">{CHARACTERS.find(c => c.id === msg.characterId)?.avatar_emoji || currentCharacter.avatar_emoji}</span>
                    )}
                  </div>
                  <div
                    className={`px-3 sm:px-5 lg:px-8 py-2 sm:py-3 lg:py-5 rounded-[20px] lg:rounded-[28px] font-normal uyghur-text shadow-sm ${msg.role === 'user' ? 'bg-white/80 border border-[#0369a1]/10 text-[#1a1a1a] rounded-tr-none' : 'bg-[#0369a1] text-white rounded-tl-none shadow-xl shadow-[#0369a1]/10'}`}
                    style={{ fontSize: `${fontSize}px`, lineHeight: '1.8' }}
                  >
                    {msg.role === 'user' ? msg.text : (
                      <MarkdownContent
                        content={msg.text}
                        onReferenceClick={handleReferenceClick}
                        className="text-white uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                        style={{ fontSize: `${fontSize}px` }}
                      />
                    )}
                  </div>
                </div>
              ))
            )}
            {streamingMessage && (
              <div className="flex flex-col items-end md:flex-row-reverse md:items-start gap-2 md:gap-4 lg:gap-6">
                <div className="w-7 h-7 md:w-10 md:h-10 shrink-0 rounded-xl md:rounded-2xl bg-[#0369a1] text-white flex items-center justify-center shadow-xl shadow-[#0369a1]/20">
                  <span className="text-lg md:text-xl">{currentCharacter.avatar_emoji}</span>
                </div>
                <div className="px-3 sm:px-5 lg:px-8 py-2 sm:py-3 lg:py-5 rounded-[20px] lg:rounded-[28px] rounded-tl-none font-normal uyghur-text shadow-xl shadow-[#0369a1]/10 bg-[#0369a1] text-white" style={{ fontSize: `${fontSize}px`, lineHeight: '1.8' }}>
                  <MarkdownContent
                    content={streamingMessage}
                    onReferenceClick={handleReferenceClick}
                    className="text-white uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                    style={{ fontSize: `${fontSize}px` }}
                  />
                </div>
              </div>
            )}
            {isChatting && !streamingMessage && (
              <div className="flex flex-col items-end md:flex-row-reverse md:items-start gap-2 md:gap-4 lg:gap-6">
                <div className="w-7 h-7 md:w-10 md:h-10 shrink-0 rounded-xl md:rounded-2xl bg-[#0369a1] text-white flex items-center justify-center shadow-xl shadow-[#0369a1]/20 animate-pulse">
                  <span className="text-lg md:text-xl">{currentCharacter.avatar_emoji}</span>
                </div>
                <div className="bg-[#0369a1]/10 px-5 py-4 rounded-[28px] rounded-tl-none flex gap-2 items-center border border-[#0369a1]/10 shadow-sm">
                  <TypingCarousel className="text-[#0369a1]" fontSize={chatFontSize} />
                </div>
              </div>
            )}
          </div>

          {/* Input Bar — inside card, styled like reader chat */}
          <div className="relative p-1 sm:p-2 bg-white/80 backdrop-blur-2xl border-t-2 border-[#0369a1]/10 shadow-[0_-8px_32px_rgba(0,0,0,0.04)] transition-all focus-within:border-[#0369a1]/30">
            {isAuthenticated ? (
              <>
                {usageStatus?.hasReachedLimit ? (
                  <div className="py-2 px-4 text-center">
                    <p className="text-xs text-red-500 font-normal bg-red-50 py-2 rounded-xl border border-red-50/50">{t('chat.limitReached')}</p>
                  </div>
                ) : (
                  <>
                    <input
                      type="text"
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && !isChatting && !usageStatus?.hasReachedLimit && onSendMessage()}
                      onFocus={(e) => { const el = e.target; setTimeout(() => el?.scrollIntoView({ block: 'nearest' }), 300); }}
                      placeholder={usageStatus && usageStatus.limit !== null ? t('chat.inputPlaceholderWithLimit', { usage: usageStatus.usage, limit: usageStatus.limit }) : t('chat.inputPlaceholderBook')}
                      className="w-full bg-transparent border-none py-2 sm:py-3 pl-[52px] sm:pl-[72px] pr-[72px] sm:pr-[88px] font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none uyghur-text"
                      style={{ fontSize: `${fontSize}px` }}
                      dir="rtl"
                      disabled={usageStatus?.hasReachedLimit}
                    />
                    {/* Send button — absolute left */}
                    <button
                      onClick={onSendMessage}
                      disabled={isChatting || !chatInput.trim() || usageStatus?.hasReachedLimit}
                      className="absolute left-[12px] sm:left-[20px] top-1/2 -translate-y-1/2 p-2 sm:p-3 bg-[#0369a1] text-white rounded-2xl shadow-lg shadow-[#0369a1]/20 hover:scale-105 active:scale-90 transition-all disabled:opacity-30"
                    >
                      <Send size={16} strokeWidth={3} />
                    </button>
                    {/* Character dropdown — absolute right */}
                    <div ref={charMenuRef} className="absolute right-[12px] sm:right-[20px] top-1/2 -translate-y-1/2">
                      <button
                        className="flex items-center gap-1.5 px-2 py-1.5 sm:px-3 sm:py-2 bg-[#0369a1]/5 hover:bg-[#0369a1]/10 text-[#0369a1] rounded-xl transition-all active:scale-95 border border-[#0369a1]/10"
                        onClick={() => setIsCharMenuOpen(prev => !prev)}
                      >
                        <span className="text-lg sm:text-xl">{currentCharacter.avatar_emoji}</span>
                        <ChevronDown size={12} className="opacity-50" />
                      </button>
                      {isCharMenuOpen && (
                        <div className="absolute bottom-full right-0 mb-3 bg-white/95 backdrop-blur-xl border border-[#0369a1]/10 rounded-[28px] shadow-2xl p-2 min-w-[200px] z-50 animate-in fade-in slide-in-from-bottom-2">
                          <div className="grid grid-cols-1 gap-1">
                            {CHARACTERS.map(char => (
                              <button
                                key={char.id}
                                onClick={() => { setSelectedCharacterId?.(char.id); setIsCharMenuOpen(false); }}
                                className={`flex items-center gap-3 w-full p-3 rounded-2xl transition-all text-right ${selectedCharacterId === char.id ? 'bg-[#0369a1] text-white' : 'hover:bg-slate-50 text-slate-700'}`}
                                dir="rtl"
                              >
                                <span className="text-2xl">{char.avatar_emoji}</span>
                                <span className="font-normal text-sm">{char.name_uy}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className="flex items-center justify-between gap-2 px-4 py-2.5 sm:py-3 min-h-[52px] sm:min-h-[60px]">
                <p className="text-[#1a1a1a] font-normal text-[11px] sm:text-sm leading-relaxed text-right">{t('auth.signInToUseChat')}</p>
                <OAuthButtonGroup align="up" side="right" className="shrink-0" />
              </div>
            )}
          </div>
        </div>
        {
          selectedReference && (
            <ReferenceModal
              isOpen={!!selectedReference}
              onClose={() => setSelectedReference(null)}
              bookId={selectedReference.bookId}
              pageNumbers={selectedReference.pageNums}
            />
          )
        }
      </div >
    );
  }

  // Sidebar (Reader) Chat Version
  return (
    <div ref={readerOuterRef} className="flex-1 min-h-0 flex flex-col gap-3 md:gap-6 relative overflow-hidden" dir="rtl" lang="ug">
      <div
        ref={chatContainerRef}
        className="flex-grow overflow-y-auto space-y-6 px-4 custom-scrollbar-mini py-2 flex flex-col"
      >
        {chatMessages.length === 0 && (
          <div className="flex-grow flex flex-col justify-center py-10">
            {!isAuthenticated ? (
              <div className="flex flex-col items-center justify-center gap-5 py-8 px-4">
                <div className="p-4 bg-[#0369a1]/10 rounded-[28px]">
                  <LogIn className="text-[#0369a1] w-10 h-10" strokeWidth={1.5} />
                </div>
                <p className="text-sm text-[#94a3b8] font-normal text-center leading-loose">
                  {t('auth.signInMessage')}
                </p>
              </div>
            ) : (
              <div className="text-center py-12 px-8 bg-white/40 border-2 border-dashed border-[#0369a1]/10 rounded-[32px] flex flex-col items-center justify-center gap-4 opacity-60">
                <Bot size={48} className="text-[#0369a1]" strokeWidth={1} />
                <p
                  className="font-normal leading-loose text-[#1a1a1a]"
                  style={{ fontSize: `${chatFontSize}px` }}
                >
                  {t('chat.bookAssistantWelcome')}
                </p>
              </div>
            )}
          </div>
        )}
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`flex gap-2 ${msg.role === 'user' ? 'flex-col items-start' : 'flex-col items-end'}`}>
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm ${msg.role === 'user' ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'bg-[#0369a1] text-white'
              }`}>
              {msg.role === 'user' ? (
                <User size={18} strokeWidth={2.5} />
              ) : (
                <span className="text-base">
                  {CHARACTERS.find(c => c.id === msg.characterId)?.avatar_emoji || '🤖'}
                </span>
              )}
            </div>
            <div className={`flex flex-col gap-1.5 ${msg.role === 'user' ? 'max-w-[85%] items-start' : 'w-full items-end'}`}>
              <div
                className={`px-5 py-3.5 rounded-2xl font-normal uyghur-text shadow-sm ${msg.role === 'user'
                  ? 'bg-white/80 border border-[#0369a1]/10 text-[#1a1a1a] rounded-tr-none'
                  : 'bg-[#0369a1] text-white rounded-tl-none shadow-lg shadow-[#0369a1]/5'
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
            </div>
          </div>
        ))}
        {streamingMessage && (
          <div className="flex gap-2 flex-col items-end">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm bg-[#0369a1] text-white">
              <Bot size={18} strokeWidth={2.5} />
            </div>
            <div className="flex flex-col gap-1.5 w-full items-end">
              <div
                className="px-5 py-3.5 rounded-2xl font-normal shadow-lg shadow-[#0369a1]/5 bg-[#0369a1] text-white rounded-tl-none uyghur-text"
                style={{ fontSize: `${chatFontSize}px`, lineHeight: '1.8' }}
              >
                <MarkdownContent
                  content={streamingMessage}
                  onReferenceClick={handleReferenceClick}
                  className="text-white uyghur-text [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                  style={{ fontSize: `${chatFontSize}px` }}
                />
              </div>
            </div>
          </div>
        )}
        {isChatting && !streamingMessage && (
          <div className="flex gap-2 flex-col items-end">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm bg-[#0369a1] text-white animate-pulse">
              <span className="text-base">{currentCharacter.avatar_emoji}</span>
            </div>
            <div className="bg-[#0369a1]/10 px-4 py-3 rounded-2xl rounded-tl-none flex gap-2 items-center border border-[#0369a1]/10 shadow-sm">
              <TypingCarousel className="text-[#0369a1]" fontSize={chatFontSize} />
            </div>
          </div>
        )}
      </div>

      <div className="relative flex-shrink-0 p-1 sm:p-2 bg-white/80 backdrop-blur-2xl border-2 border-[#0369a1]/10 shadow-[0_24px_64px_rgba(0,0,0,0.06)] transition-all focus-within:border-[#0369a1] focus-within:ring-[12px] focus-within:ring-[#0369a1]/5 rounded-[20px] md:rounded-[24px]">
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
                  ref={readerInputRef}
                  className="w-full bg-transparent border-none py-2 sm:py-3 pl-[52px] sm:pl-[76px] pr-2 sm:pr-4 font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none uyghur-text"
                  style={{ fontSize: `${chatFontSize}px` }}
                  dir="rtl"
                  disabled={usageStatus?.hasReachedLimit}
                />
                <button
                  onClick={onSendMessage}
                  disabled={isChatting || !chatInput.trim() || usageStatus?.hasReachedLimit}
                  className="absolute left-[12px] sm:left-[24px] top-1/2 -translate-y-1/2 p-2 sm:p-3 bg-[#0369a1] text-white rounded-2xl shadow-lg shadow-[#0369a1]/20 hover:scale-105 active:scale-90 transition-all disabled:opacity-30"
                >
                  <Send size={16} strokeWidth={3} />
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2 px-4 py-2.5 sm:py-3 min-h-[52px] sm:min-h-[60px]">
            <p className="text-[#1a1a1a] font-normal text-[11px] sm:text-sm leading-relaxed text-right">
              {t('auth.signInToUseChat')}
            </p>
            <OAuthButtonGroup align="up" side="right" className="shrink-0" />
          </div>
        )}
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
