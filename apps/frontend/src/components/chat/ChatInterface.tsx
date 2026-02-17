import React from 'react';
import { MessageSquare, Globe, X, Send, Bot, User, BookOpen } from 'lucide-react';
import { Message, Book } from '@shared/types';
import { GlassPanel } from '../ui/GlassPanel';
import { useI18n } from '../../i18n/I18nContext';

interface ChatInterfaceProps {
  type: 'book' | 'global';
  books?: Book[];
  totalReady?: number;
  chatMessages: Message[];
  chatInput: string;
  setChatInput: (input: string) => void;
  onSendMessage: () => void;
  isChatting: boolean;
  currentPage?: number | null;
  onClose?: () => void;
  chatContainerRef: React.RefObject<HTMLDivElement>;
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
  currentPage,
  onClose,
  chatContainerRef,
}) => {
  const { t } = useI18n();
  const isGlobal = type === 'global';

  if (isGlobal) {
    return (
      <div className="h-[calc(100vh-140px)] max-w-5xl mx-auto w-full flex flex-col gap-6 animate-fade-in py-4" dir="rtl">
        {/* Chat Header */}
        <div className="bg-white/60 backdrop-blur-2xl px-8 py-6 flex items-center justify-between border border-[#75C5F0]/10 shadow-sm" style={{ borderRadius: '32px' }}>
          <div className="flex items-center gap-5">
            <div className="p-4 bg-[#75C5F0] text-white rounded-[24px] shadow-xl shadow-[#75C5F0]/20 transform rotate-3 transition-transform hover:rotate-0">
              <Globe size={28} strokeWidth={2.5} />
            </div>
            <div>
              <h1 className="text-2xl font-black text-[#1a1a1a]">{t('chat.globalAssistant')}</h1>
              <p className="text-sm font-bold text-[#94a3b8] mt-1">{t('chat.subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden md:flex items-center gap-3 px-6 py-2.5 bg-[#e8f4f8] text-[#75C5F0] rounded-2xl border border-[#75C5F0]/10 shadow-inner">
              <BookOpen size={18} strokeWidth={2.5} />
              <span className="text-sm font-black uppercase tracking-widest">
                {t('chat.allBooks')} • {totalReady || books.filter(b => b.status === 'ready').length}
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
          className="flex-grow overflow-y-auto space-y-10 px-10 py-12 bg-white/40 backdrop-blur-xl relative custom-scrollbar shadow-inner border border-white/40"
          style={{ borderRadius: '40px' }}
        >
          {chatMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <div className="w-28 h-28 bg-[#e8f4f8] rounded-[40px] flex items-center justify-center mb-8 border-2 border-[#75C5F0]/10 shadow-lg relative group overflow-hidden">
                <div className="absolute inset-0 bg-[#75C5F0]/10 animate-pulse" />
                <MessageSquare className="text-[#75C5F0] w-14 h-14 relative z-10 transition-transform group-hover:scale-110" strokeWidth={2.5} />
              </div>
              <h4 className="text-3xl font-black text-[#1a1a1a] mb-4 tracking-tight">{t('chat.welcome.title')}</h4>
              <p className="text-slate-500 font-bold max-w-lg leading-loose text-lg">
                {t('chat.welcome.message')}
              </p>
            </div>
          ) : (
            chatMessages.map((msg, idx) => (
              <div key={idx} className={`flex gap-6 ${msg.role === 'user' ? 'flex-row' : 'flex-row-reverse'} items-start animate-fade-in`}>
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center shadow-lg transition-all transform hover:scale-110 ${msg.role === 'user'
                  ? 'bg-white border-2 border-[#75C5F0]/10 text-[#75C5F0]'
                  : 'bg-[#75C5F0] text-white shadow-[#75C5F0]/30'
                  }`}>
                  {msg.role === 'user' ? <User size={24} strokeWidth={2.5} /> : <Bot size={24} strokeWidth={2.5} />}
                </div>
                <div className={`flex flex-col gap-2 max-w-[80%] ${msg.role === 'user' ? 'items-start' : 'items-end'}`}>
                  <span className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.2em] px-2">
                    {msg.role === 'user' ? t('chat.you') : t('chat.ai')}
                  </span>
                  <div className={`px-8 py-5 rounded-[28px] text-lg font-black leading-loose uyghur-text shadow-sm ${msg.role === 'user'
                    ? 'bg-white/80 border border-[#75C5F0]/10 text-[#1a1a1a] rounded-tr-none'
                    : 'bg-[#75C5F0] text-white rounded-tl-none shadow-xl shadow-[#75C5F0]/10'
                    }`}>
                    {msg.text}
                  </div>
                </div>
              </div>
            ))
          )}
          {isChatting && (
            <div className="flex flex-row-reverse gap-6 items-start animate-fade-in">
              <div className="w-12 h-12 rounded-2xl bg-[#75C5F0] text-white flex items-center justify-center shadow-xl shadow-[#75C5F0]/20 animate-pulse">
                <Bot size={24} strokeWidth={2.5} />
              </div>
              <div className="bg-[#e8f4f8] px-8 py-5 rounded-[28px] rounded-tl-none flex gap-2 items-center border border-[#75C5F0]/10 shadow-sm animate-bounce">
                <div className="w-2 h-2 bg-[#75C5F0] rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-[#75C5F0] rounded-full animate-bounce [animation-delay:0.2s]" />
                <div className="w-2 h-2 bg-[#75C5F0] rounded-full animate-bounce [animation-delay:0.4s]" />
              </div>
            </div>
          )}
        </div>

        {/* Input Bar */}
        <div className="bg-white px-6 py-5 border-2 border-[#75C5F0] shadow-[0_24px_64px_rgba(117,197,240,0.2)] relative transition-all focus-within:shadow-[0_24px_64px_rgba(117,197,240,0.3)]" style={{ borderRadius: '32px' }}>
          <div className="flex gap-4 items-center">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !isChatting && onSendMessage()}
              placeholder={t('chat.inputPlaceholderBook')}
              className="flex-1 bg-transparent py-2 px-4 text-xl font-black text-[#1a1a1a] placeholder:text-slate-300 outline-none uyghur-text"
              dir="rtl"
            />
            <button
              onClick={onSendMessage}
              disabled={isChatting || !chatInput.trim()}
              className="px-10 py-4 bg-[#75C5F0] hover:bg-[#5AB0E5] text-white rounded-[24px] font-black flex items-center gap-4 transition-all active:scale-95 shadow-xl shadow-[#75C5F0]/20 disabled:opacity-30 disabled:grayscale"
            >
              {t('common.send')}
              <Send size={20} strokeWidth={3} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Sidebar (Reader) Chat Version
  return (
    <div className="h-full flex flex-col gap-6 animate-fade-in relative" dir="rtl">
      <div className="bg-white/60 backdrop-blur-xl p-5 flex items-center justify-between border border-[#75C5F0]/10 shadow-sm" style={{ borderRadius: '24px' }}>
        <div className="flex items-center gap-4">
          <div className="p-2.5 bg-[#75C5F0] text-white rounded-2xl shadow-lg shadow-[#75C5F0]/10">
            <MessageSquare size={18} strokeWidth={2.5} />
          </div>
          <div>
            <h3 className="font-black text-sm text-[#1a1a1a]">{t('chat.bookAssistant')}</h3>
            <p className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.1em]">{t('chat.sidebarSubtitle')}</p>
          </div>
        </div>
        {currentPage && (
          <div className="bg-[#e8f4f8] text-[#75C5F0] px-3 py-1 rounded-xl text-[14px] font-black border border-[#75C5F0]/10 shadow-inner">
            {t('chat.pageNumber', { page: currentPage })}
          </div>
        )}
      </div>

      <div
        ref={chatContainerRef}
        className="flex-grow overflow-y-auto space-y-6 px-4 custom-scrollbar-mini py-2"
      >
        {chatMessages.length === 0 && (
          <div className="text-center py-20 px-8 bg-white/40 border-2 border-dashed border-[#75C5F0]/10 rounded-[32px] flex flex-col items-center justify-center gap-4 opacity-60">
            <Bot size={40} className="text-[#75C5F0]" strokeWidth={1} />
            <p className="text-sm text-[#1a1a1a] font-black leading-loose">
              {t('chat.bookAssistantWelcome')}
            </p>
          </div>
        )}
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`flex gap-3 ${msg.role === 'user' ? 'flex-row' : 'flex-row-reverse'} items-start animate-fade-in`}>
            <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm shadow-sm ${msg.role === 'user' ? 'bg-[#e8f4f8] text-[#75C5F0]' : 'bg-[#75C5F0] text-white'
              }`}>
              {msg.role === 'user' ? <User size={18} strokeWidth={2.5} /> : <Bot size={18} strokeWidth={2.5} />}
            </div>
            <div className={`flex flex-col gap-1.5 max-w-[85%] ${msg.role === 'user' ? 'items-start' : 'items-end'}`}>
              <div className={`px-5 py-3.5 rounded-2xl text-sm font-black leading-relaxed shadow-sm ${msg.role === 'user'
                ? 'bg-white/80 border border-[#75C5F0]/10 text-[#1a1a1a] rounded-tr-none'
                : 'bg-[#75C5F0] text-white rounded-tl-none shadow-lg shadow-[#75C5F0]/5'
                }`}>
                {msg.text}
              </div>
            </div>
          </div>
        ))}
        {isChatting && (
          <div className="flex flex-row-reverse gap-3 items-center px-4 animate-fade-in">
            <div className="w-1.5 h-1.5 bg-[#75C5F0] rounded-full animate-bounce" />
            <div className="w-1.5 h-1.5 bg-[#75C5F0] rounded-full animate-bounce [animation-delay:0.2s]" />
            <div className="w-1.5 h-1.5 bg-[#75C5F0] rounded-full animate-bounce [animation-delay:0.4s]" />
          </div>
        )}
      </div>

      <div className="relative mt-auto p-2 bg-white/60 backdrop-blur-xl border border-[#75C5F0]/10 shadow-lg" style={{ borderRadius: '24px' }}>
        <input
          type="text"
          placeholder={t('chat.inputPlaceholderBook')}
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isChatting && onSendMessage()}
          className="w-full bg-transparent border-none py-3 pl-12 pr-4 text-sm font-black text-[#1a1a1a] placeholder:text-slate-300 outline-none uyghur-text"
          dir="rtl"
        />
        <button
          onClick={onSendMessage}
          disabled={isChatting || !chatInput.trim()}
          className="absolute left-3 top-1/2 -translate-y-1/2 p-3 bg-[#75C5F0] text-white rounded-2xl shadow-lg shadow-[#75C5F0]/20 hover:scale-105 active:scale-90 transition-all disabled:opacity-30"
        >
          <Send size={16} strokeWidth={3} />
        </button>
      </div>
    </div>
  );
};
