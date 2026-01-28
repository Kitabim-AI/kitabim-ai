import React from 'react';
import { MessageSquare, Globe, X, Loader2, Send } from 'lucide-react';
import { Message, Book } from '../../types';

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
  const isGlobal = type === 'global';

  if (isGlobal) {
    return (
      <div className="h-[calc(100vh-140px)] max-w-4xl mx-auto w-full flex flex-col gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
        <div className="bg-indigo-950 text-white p-8 rounded-3xl shadow-2xl flex flex-col h-full border border-white/5 relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full -mr-32 -mt-32 blur-[100px] pointer-events-none"></div>
          <div className="absolute bottom-0 left-0 w-64 h-64 bg-indigo-400/5 rounded-full -ml-32 -mb-32 blur-[80px] pointer-events-none"></div>

          <div className="flex items-center justify-between mb-8 relative">
            <div className="flex items-center gap-4">
              <div className="bg-indigo-500/20 p-3 rounded-2xl border border-indigo-500/30">
                <Globe className="w-6 h-6 text-indigo-300" />
              </div>
              <div>
                <h3 className="text-xl font-bold tracking-tight">كىتابىم خەزىنىسى</h3>
                <p className="text-[10px] text-indigo-300 font-black uppercase tracking-[0.2em] mt-0.5 opacity-80">
                  پارچە كىتابتىن ئىزدەۋاتىدۇ {totalReady || books.filter(b => b.status === 'ready').length}
                </p>
              </div>
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="p-2 hover:bg-white/10 rounded-xl transition-colors text-indigo-300 hover:text-white"
              >
                <X size={20} />
              </button>
            )}
          </div>

          <div ref={chatContainerRef} className="flex-grow overflow-y-auto mb-6 space-y-6 pr-2 scrollbar-hide">
            {chatMessages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center px-10">
                <div className="w-20 h-20 bg-indigo-500/10 rounded-full flex items-center justify-center mb-6 border border-white/5 animate-bounce">
                  <MessageSquare className="text-indigo-400 w-10 h-10" />
                </div>
                <h4 className="text-lg font-bold text-white mb-2">!كىتابىم خەزىنىسىگە خۇش كەپسىز</h4>
                <p className="text-indigo-300 text-sm max-w-sm leading-relaxed">
                  كۈتۈپخانىمىزدىكى بارلىق كىتابلارنى ئوقۇپ، سىزگە جاۋاب بېرىمەن
                </p>
              </div>
            ) : (
              chatMessages.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-2 duration-300`}>
                  <div className={`max-w-[85%] p-5 rounded-3xl text-sm leading-relaxed shadow-lg ${msg.role === 'user'
                    ? 'bg-gradient-to-br from-indigo-500 to-indigo-700 text-white rounded-tr-none border border-white/10'
                    : 'bg-white/5 backdrop-blur-md text-indigo-50 border border-white/10 rounded-tl-none uyghur-text text-[1.1rem] leading-[1.8] font-medium'
                    }`}>
                    {msg.text}
                  </div>
                </div>
              ))
            )}
            {isChatting && (
              <div className="flex justify-start">
                <div className="bg-white/5 border border-white/5 p-4 rounded-2xl rounded-tl-none flex gap-1.5 items-center">
                  <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce" />
                  <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce [animation-delay:0.2s]" />
                  <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce [animation-delay:0.4s]" />
                </div>
              </div>
            )}
          </div>

          <div className="relative">
            <input
              type="text"
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onSendMessage()}
              placeholder="كۈتۈپخانىدىكى ھەرقانداق كىتابتىن سۇئال سوراڭ..."
              className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 l-6 pr-14 text-white focus:ring-4 focus:ring-indigo-500/20 outline-none transition-all uyghur-text text-lg"
              dir="rtl"
            />
            <button
              onClick={onSendMessage}
              disabled={isChatting || !chatInput.trim()}
              className="absolute left-2 top-1/2 -translate-y-1/2 p-2.5 bg-indigo-500 text-white rounded-xl hover:bg-indigo-400 transition-all shadow-xl active:scale-95 disabled:opacity-30 disabled:grayscale"
            >
              <Send size={20} className="stroke-[2.5]" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-indigo-950 text-white p-6 rounded-2xl shadow-2xl flex flex-col h-full border border-white/5 relative overflow-hidden">
      <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-full -mr-16 -mt-16 blur-3xl pointer-events-none"></div>

      <div className="flex items-center gap-3 mb-6 relative">
        <div className="bg-indigo-500/20 p-2.5 rounded-xl border border-indigo-500/30">
          <MessageSquare className="w-5 h-5 text-indigo-300" />
        </div>
        <div>
          <h3 className="font-bold text-sm">كىتابىم ياردەمچىسى</h3>
          <div className="flex items-center gap-2">
            <p className="text-[10px] text-indigo-300 font-bold uppercase tracking-widest">ئەقلىي ئىقتىدارلىق ئىزدەش</p>
            {currentPage && (
              <div className="px-1.5 py-0.5 bg-indigo-500/30 text-[9px] rounded-md border border-indigo-500/20 text-indigo-200 uppercase font-black">
                بەت: {currentPage}
              </div>
            )}
          </div>
        </div>
      </div>

      <div ref={chatContainerRef} className="flex-grow overflow-y-auto space-y-4 pr-2 mb-4 scroll-smooth custom-scrollbar">
        {chatMessages.length === 0 && (
          <div className="bg-white/5 border border-white/5 rounded-2xl p-6 text-center">
            <p className="text-sm text-white/60 leading-relaxed uyghur-text">
              مەن سىزگە بۇ كىتابتىكى مەزمۇنلارنى تېپىشقا ياردەم بېرەلەيمەن. خالىغان سوئالنى سورىسىڭىز بولىدۇ.
            </p>
          </div>
        )}
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-in fade-in slide-in-from-bottom-1 duration-200`}>
            <div className={`max-w-[90%] px-4 py-3 rounded-2xl text-sm ${msg.role === 'user'
              ? 'bg-gradient-to-br from-indigo-500 to-indigo-600 text-white rounded-tr-none shadow-md'
              : 'bg-white/10 backdrop-blur-sm text-white rounded-tl-none border border-white/5 uyghur-text text-right leading-[1.8] text-[0.95rem]'
              }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {isChatting && (
          <div className="flex justify-start">
            <div className="bg-white/5 p-4 rounded-2xl rounded-tl-none border border-white/5">
              <Loader2 size={16} className="animate-spin text-indigo-400" />
            </div>
          </div>
        )}
      </div>

      <div className="mt-auto relative">
        <input
          type="text"
          placeholder="سوئال سوراش..."
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && onSendMessage()}
          className="w-full bg-white/5 border border-white/10 rounded-xl py-3.5 pl-5 pr-12 text-sm text-white focus:ring-2 focus:ring-indigo-500 transition-all outline-none uyghur-text"
          dir="rtl"
        />
        <button
          onClick={onSendMessage}
          disabled={isChatting}
          className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-indigo-50 text-indigo-600 rounded-lg hover:bg-white transition-all disabled:opacity-50"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
};
