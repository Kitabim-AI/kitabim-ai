import React from 'react';
import { MessageSquare, X, Send, Bot, User, BookOpen, LogIn } from 'lucide-react';
import { Message, Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { useAuth } from '../../hooks/useAuth';
import { OAuthButtonGroup } from '../auth/AuthButton';
import { MarkdownContent } from '../common/MarkdownContent';
import { ReferenceModal } from './ReferenceModal';

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
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  type,
  books = [],
  totalReady = 0,
  chatMessages,
  chatInput,
  setChatInput,
  onSendMessage,
  isChatting,
  streamingMessage = '',
  currentPage,
  onClose,
  chatContainerRef,
  usageStatus,
}) => {
  const { t } = useI18n();
  const { isAuthenticated } = useAuth();
  const isGlobal = type === 'global';
  const [selectedReference, setSelectedReference] = React.useState<{ bookId: string; pageNums: number[] } | null>(null);

  const handleReferenceClick = (bookId: string, pageNums: number[]) => {
    setSelectedReference({ bookId, pageNums });
  };

  if (isGlobal) {
    return (
      <div className="h-[calc(100dvh-72px)] sm:h-[calc(100dvh-88px)] md:h-[calc(100dvh-120px)] lg:h-[calc(100dvh-140px)] w-full lg:max-w-5xl lg:mx-auto flex flex-col gap-3 md:gap-4 lg:gap-6 px-3 py-3 sm:px-6 md:px-0 lg:py-4" dir="rtl" lang="ug">
        {/* Chat Header — hidden on md and smaller */}
        <div className="hidden lg:flex bg-white/60 backdrop-blur-2xl px-8 py-4 items-center justify-between border border-[#0369a1]/10 shadow-sm group" style={{ borderRadius: '32px' }}>
          <div className="flex items-center gap-5">
            <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
              <MessageSquare size={20} className="md:w-6 md:h-6" strokeWidth={2.5} />
            </div>
            <div>
              <h1 className="text-2xl font-normal text-[#1a1a1a]">{t('chat.globalAssistant')}</h1>
              <p className="text-[14px] font-normal text-[#94a3b8] uppercase mt-1">{t('chat.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-3 px-6 py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl border border-[#0369a1]/10 shadow-inner">
              <BookOpen size={18} strokeWidth={2.5} />
              <span className="text-sm font-normal uppercase">
                {t('chat.libraryBookCount', { count: totalReady || books.filter(b => b.status === 'ready').length })}
              </span>
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="p-3 hover:bg-red-50 text-slate-300 hover:text-red-500 rounded-2xl transition-all active:scale-90"
              >
                <X size={24} strokeWidth={3} />
              </button>
            )}
          </div>
        </div>

        {/* Messages Buffer */}
        <div
          ref={chatContainerRef}
          className="flex-grow overflow-y-auto space-y-4 md:space-y-8 lg:space-y-10 px-2 sm:px-4 lg:px-10 py-3 sm:py-4 lg:py-12 bg-white/40 backdrop-blur-xl relative custom-scrollbar shadow-inner border border-white/40 rounded-[24px] sm:rounded-[40px] flex flex-col"
        >
          {chatMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <div className="w-28 h-28 bg-[#0369a1]/10 rounded-[40px] flex items-center justify-center mb-8 border-2 border-[#0369a1]/10 shadow-lg relative group overflow-hidden">
                <div className="absolute inset-0 bg-[#0369a1]/10 animate-pulse" />
                <MessageSquare className="text-[#0369a1] w-14 h-14 relative z-10 transition-transform group-hover:scale-110" strokeWidth={2.5} />
              </div>
              <h4 className="text-2xl font-normal text-[#1a1a1a] mb-4">{t('chat.welcome.title')}</h4>
              <p className="text-slate-500 font-normal max-w-lg leading-loose text-base">
                {t('chat.welcome.message')}
              </p>
              <p className="text-slate-400 font-normal max-w-lg leading-loose text-sm mt-4 italic border-t border-slate-200 pt-4">
                {t('chat.welcome.disclaimer')}
              </p>
            </div>
          ) : (
            chatMessages.map((msg, idx) => (
              <div key={idx} className={`flex gap-2 md:gap-4 lg:gap-6 ${msg.role === 'user' ? 'flex-row' : 'flex-row-reverse'} items-start`}>
                <div className={`w-7 h-7 md:w-10 md:h-10 shrink-0 rounded-xl md:rounded-2xl flex items-center justify-center shadow-lg transition-all transform hover:scale-110 ${msg.role === 'user'
                  ? 'bg-white border-2 border-[#0369a1]/10 text-[#0369a1]'
                  : 'bg-[#0369a1] text-white shadow-[#0369a1]/30'
                  }`}>
                  {msg.role === 'user' ? <User size={14} className="md:w-5 md:h-5" strokeWidth={2.5} /> : <Bot size={14} className="md:w-5 md:h-5" strokeWidth={2.5} />}
                </div>
                <div className={`flex flex-col gap-1 md:gap-2 max-w-[91%] md:max-w-[83%] ${msg.role === 'user' ? 'items-start' : 'items-end'}`}>
                  <span className="text-[10px] md:text-[14px] font-normal text-[#94a3b8] uppercase px-1 md:px-2">
                    {msg.role === 'user' ? t('chat.you') : t('chat.ai')}
                  </span>
                  <div className={`px-3 sm:px-5 lg:px-8 py-2 sm:py-3 lg:py-5 rounded-[20px] lg:rounded-[28px] text-lg font-normal leading-loose uyghur-text shadow-sm ${msg.role === 'user'
                    ? 'bg-white/80 border border-[#0369a1]/10 text-[#1a1a1a] rounded-tr-none'
                    : 'bg-[#0369a1] text-white rounded-tl-none shadow-xl shadow-[#0369a1]/10'
                    }`}>
                    {msg.role === 'user' ? (
                      msg.text
                    ) : (
                      <MarkdownContent
                        content={msg.text}
                        onReferenceClick={handleReferenceClick}
                        className="text-white [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                      />
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
          {streamingMessage && (
            <div className="flex flex-row-reverse gap-2 md:gap-4 lg:gap-6 items-start">
              <div className="w-7 h-7 md:w-10 md:h-10 shrink-0 rounded-xl md:rounded-2xl bg-[#0369a1] text-white flex items-center justify-center shadow-xl shadow-[#0369a1]/20">
                <Bot size={14} className="md:w-5 md:h-5" strokeWidth={2.5} />
              </div>
              <div className="flex flex-col gap-1 md:gap-2 max-w-[91%] md:max-w-[83%] items-end">
                <span className="text-[10px] md:text-[14px] font-normal text-[#94a3b8] uppercase px-1 md:px-2">
                  {t('chat.ai')}
                </span>
                <div className="px-3 sm:px-5 lg:px-8 py-2 sm:py-3 lg:py-5 rounded-[20px] lg:rounded-[28px] rounded-tl-none text-lg font-normal leading-loose uyghur-text shadow-xl shadow-[#0369a1]/10 bg-[#0369a1] text-white">
                  <MarkdownContent
                    content={streamingMessage}
                    onReferenceClick={handleReferenceClick}
                    className="text-white [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                  />
                  <span className="inline-block w-[2px] h-5 bg-white/70 ml-1 animate-pulse" />
                </div>
              </div>
            </div>
          )}
          {isChatting && !streamingMessage && (
            <div className="flex flex-row-reverse gap-2 md:gap-4 lg:gap-6 items-start">
              <div className="w-7 h-7 md:w-10 md:h-10 shrink-0 rounded-xl md:rounded-2xl bg-[#0369a1] text-white flex items-center justify-center shadow-xl shadow-[#0369a1]/20 animate-pulse">
                <Bot size={14} className="md:w-5 md:h-5" strokeWidth={2.5} />
              </div>
              <div className="bg-[#0369a1]/10 px-5 py-4 rounded-[28px] rounded-tl-none flex gap-2 items-center border border-[#0369a1]/10 shadow-sm animate-bounce">
                <div className="w-2 h-2 bg-[#0369a1] rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-[#0369a1] rounded-full animate-bounce [animation-delay:0.2s]" />
                <div className="w-2 h-2 bg-[#0369a1] rounded-full animate-bounce [animation-delay:0.4s]" />
              </div>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="bg-white/80 backdrop-blur-2xl p-[5px] border-2 lg:border-2 border-[#0369a1]/10 shadow-[0_24px_64px_rgba(0,0,0,0.06)] relative transition-all focus-within:border-[#0369a1] focus-within:ring-[12px] focus-within:ring-[#0369a1]/5 rounded-[24px] sm:rounded-[32px]">
          {isAuthenticated ? (
            <div className="flex flex-col gap-2">
              {usageStatus?.hasReachedLimit ? (
                <div className="px-6 py-4 text-center">
                  <p className="text-red-500 font-normal text-lg bg-red-50 px-6 py-3 rounded-2xl border border-red-100 uppercase">
                    {t('chat.limitReached')}
                  </p>
                </div>
              ) : (
                <div className="flex gap-2 items-center">
                  <input
                    type="text"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && !isChatting && !usageStatus?.hasReachedLimit && onSendMessage()}
                    placeholder={usageStatus && usageStatus.limit !== null
                      ? t('chat.inputPlaceholderWithLimit', { usage: usageStatus.usage, limit: usageStatus.limit })
                      : t('chat.inputPlaceholderBook')}
                    className="flex-1 bg-transparent py-3 px-6 text-lg font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none uyghur-text"
                    dir="rtl"
                    disabled={usageStatus?.hasReachedLimit}
                  />
                  <button
                    onClick={onSendMessage}
                    disabled={isChatting || !chatInput.trim() || usageStatus?.hasReachedLimit}
                    className="px-5 sm:px-8 py-3 bg-[#0369a1] hover:bg-[#0284c7] text-white rounded-[24px] text-sm font-normal flex items-center gap-2 sm:gap-3 transition-all active:scale-95 shadow-lg shadow-[#0369a1]/20 disabled:opacity-30 disabled:grayscale uppercase shrink-0"
                  >
                    {t('common.send')}
                    <Send size={18} strokeWidth={3} />
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 px-6 py-4">
              <div className="flex items-center gap-4">
                <div className="p-2 bg-[#0369a1]/10 text-[#0369a1] rounded-xl">
                  <LogIn size={20} />
                </div>
                <p className="text-[#1a1a1a] font-normal">{t('auth.signInToUseChat')}</p>
              </div>
              <OAuthButtonGroup align="up" className="w-full sm:w-auto shadow-none border-[#0369a1]/10" />
            </div>
          )}
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
    <div className="h-full flex flex-col gap-3 md:gap-6 relative" dir="rtl" lang="ug">
      <div className="bg-white/60 backdrop-blur-xl p-3 md:p-5 flex items-center justify-between border border-[#0369a1]/10 shadow-sm rounded-xl md:rounded-[24px]">
        <div className="flex items-center gap-4">
          <div className="p-2.5 bg-[#0369a1] text-white rounded-2xl shadow-lg shadow-[#0369a1]/10">
            <MessageSquare size={18} strokeWidth={2.5} />
          </div>
          <div>
            <h3 className="font-normal text-sm text-[#1a1a1a]">{t('chat.bookAssistant')}{t('chat.sidebarSubtitle')}</h3>
          </div>
        </div>
        {currentPage && (
          <div className="bg-[#0369a1]/10 text-[#0369a1] px-3 py-1 rounded-xl text-[14px] font-normal border border-[#0369a1]/10 shadow-inner">
            {t('chat.pageNumber', { page: currentPage })}
          </div>
        )}
      </div>

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
                <Bot size={40} className="text-[#0369a1]" strokeWidth={1} />
                <p className="text-sm text-[#1a1a1a] font-normal leading-loose">
                  {t('chat.bookAssistantWelcome')}
                </p>
              </div>
            )}
          </div>
        )}
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row' : 'flex-row-reverse'} items-start`}>
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm ${msg.role === 'user' ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'bg-[#0369a1] text-white'
              }`}>
              {msg.role === 'user' ? <User size={18} strokeWidth={2.5} /> : <Bot size={18} strokeWidth={2.5} />}
            </div>
            <div className={`flex flex-col gap-1.5 max-w-[85%] ${msg.role === 'user' ? 'items-start' : 'items-end'}`}>
              <div className={`px-5 py-3.5 rounded-2xl text-sm font-normal leading-relaxed shadow-sm ${msg.role === 'user'
                ? 'bg-white/80 border border-[#0369a1]/10 text-[#1a1a1a] rounded-tr-none'
                : 'bg-[#0369a1] text-white rounded-tl-none shadow-lg shadow-[#0369a1]/5'
                }`}>
                {msg.role === 'user' ? (
                  msg.text
                ) : (
                  <MarkdownContent
                    content={msg.text}
                    onReferenceClick={handleReferenceClick}
                    className="text-white [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                  />
                )}
              </div>
            </div>
          </div>
        ))}
        {streamingMessage && (
          <div className="flex gap-3 flex-row-reverse items-start">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm bg-[#0369a1] text-white">
              <Bot size={18} strokeWidth={2.5} />
            </div>
            <div className="flex flex-col gap-1.5 max-w-[85%] items-end">
              <div className="px-5 py-3.5 rounded-2xl text-sm font-normal leading-relaxed shadow-lg shadow-[#0369a1]/5 bg-[#0369a1] text-white rounded-tl-none">
                <MarkdownContent
                  content={streamingMessage}
                  onReferenceClick={handleReferenceClick}
                  className="text-white [&_strong]:font-bold [&_strong]:text-white [&_code]:bg-white/20 [&_code]:text-white [&_blockquote]:text-white/90 [&_blockquote]:border-white/30 [&_h1]:text-white [&_h2]:text-white [&_h3]:text-white [&_h4]:text-white [&_h5]:text-white [&_h6]:text-white [&_a]:text-blue-100 [&_button]:text-blue-100 [&_a]:decoration-blue-100/50 [&_button]:decoration-blue-100/50"
                />
                <span className="inline-block w-[2px] h-4 bg-white/70 ml-1 animate-pulse" />
              </div>
            </div>
          </div>
        )}
        {isChatting && !streamingMessage && (
          <div className="flex flex-row-reverse gap-3 items-center px-4">
            <div className="w-1.5 h-1.5 bg-[#0369a1] rounded-full animate-bounce" />
            <div className="w-1.5 h-1.5 bg-[#0369a1] rounded-full animate-bounce [animation-delay:0.2s]" />
            <div className="w-1.5 h-1.5 bg-[#0369a1] rounded-full animate-bounce [animation-delay:0.4s]" />
          </div>
        )}
      </div>

      <div className="relative mt-auto p-[5px] bg-white/80 backdrop-blur-2xl border-2 border-[#0369a1]/10 shadow-[0_24px_64px_rgba(0,0,0,0.06)] transition-all focus-within:border-[#0369a1] focus-within:ring-[12px] focus-within:ring-[#0369a1]/5 rounded-[20px] md:rounded-[24px]">
        {isAuthenticated ? (
          <div className="flex flex-col gap-1">
            {usageStatus?.hasReachedLimit ? (
              <div className="py-2 px-4 text-center">
                <p className="text-[12px] text-red-500 font-normal bg-red-50 py-2 rounded-xl border border-red-50/50">
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
                  className="w-full bg-transparent border-none py-3 pl-12 pr-4 text-base font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none uyghur-text"
                  dir="rtl"
                  disabled={usageStatus?.hasReachedLimit}
                />
                <button
                  onClick={onSendMessage}
                  disabled={isChatting || !chatInput.trim() || usageStatus?.hasReachedLimit}
                  className="absolute left-3 top-1/2 -translate-y-1/2 p-3 bg-[#0369a1] text-white rounded-2xl shadow-lg shadow-[#0369a1]/20 hover:scale-105 active:scale-90 transition-all disabled:opacity-30"
                >
                  <Send size={16} strokeWidth={3} />
                </button>
              </>
            )}
          </div>
        ) : (
          <div className="py-2 px-1">
            <OAuthButtonGroup align="up" side="right" className="w-full" />
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
