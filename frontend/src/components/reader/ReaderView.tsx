import React from 'react';
import { Edit3, Save, Minus, Plus, Type, X, RotateCcw, Loader2 } from 'lucide-react';
import { Book } from '../../types';
import { ChatInterface } from '../chat/ChatInterface';

interface ReaderViewProps {
  selectedBook: Book;
  isEditing: boolean;
  setIsEditing: (editing: boolean) => void;
  editContent: string;
  setEditContent: (content: string) => void;
  onSaveCorrections: () => void;
  fontSize: number;
  setFontSize: (size: number | ((prev: number) => number)) => void;
  onClose: () => void;
  onReprocess: (id: string) => void;
  onReProcessPage: (id: string, num: number) => void;
  onUpdatePage: (id: string, num: number, text: string) => void;
  currentPage: number | null;
  setCurrentPage: (page: number) => void;
  editingPageNum: number | null;
  setEditingPageNum: (num: number | null) => void;
  tempPageText: string;
  setTempPageText: (text: string) => void;
  chatMessages: any[];
  chatInput: string;
  setChatInput: (input: string) => void;
  onSendMessage: () => void;
  isChatting: boolean;
  chatContainerRef: React.RefObject<HTMLDivElement>;
}

export const ReaderView: React.FC<ReaderViewProps> = ({
  selectedBook,
  isEditing,
  setIsEditing,
  editContent,
  setEditContent,
  onSaveCorrections,
  fontSize,
  setFontSize,
  onClose,
  onReprocess,
  onReProcessPage,
  onUpdatePage,
  currentPage,
  setCurrentPage,
  editingPageNum,
  setEditingPageNum,
  tempPageText,
  setTempPageText,
  chatMessages,
  chatInput,
  setChatInput,
  onSendMessage,
  isChatting,
  chatContainerRef,
}) => {
  return (
    <div className="h-[calc(100vh-140px)] flex gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex-grow bg-white border border-slate-200 rounded-2xl shadow-sm flex flex-col overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div>
            <h2 className="font-bold text-slate-900">{selectedBook.title}</h2>
            {selectedBook.tags && selectedBook.tags.length > 0 && (
              <div className="flex gap-1 mt-1">
                {selectedBook.tags.map((tag, i) => (
                  <span key={i} className="text-[10px] bg-indigo-50 text-indigo-700 px-1.5 py-0.5 rounded border border-indigo-100 font-medium">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {selectedBook.status !== 'processing' && (
              <button
                onClick={() => onReprocess(selectedBook.id)}
                className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 text-amber-700 text-sm font-semibold rounded-lg hover:bg-amber-100 transition-colors"
              >
                <RotateCcw size={16} /> Fix / Retrofit
              </button>
            )}
            {!isEditing ? (
              <button onClick={() => setIsEditing(true)} className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 text-sm font-semibold rounded-lg hover:bg-slate-50 transition-colors">
                <Edit3 size={16} /> Global Edit
              </button>
            ) : (
              <button onClick={onSaveCorrections} className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-100">
                <Save size={16} /> Update Knowledge Base
              </button>
            )}

            <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1 mx-2">
              <button
                onClick={() => setFontSize(prev => Math.max(12, prev - 2))}
                className="p-1 hover:bg-slate-100 rounded text-slate-500 transition-colors"
                title="Decrease Font Size"
              >
                <Minus size={14} />
              </button>
              <div className="flex items-center gap-1 px-2 text-slate-400 border-x border-slate-100">
                <Type size={14} />
                <span className="text-[10px] font-bold font-mono">{fontSize}</span>
              </div>
              <button
                onClick={() => setFontSize(prev => Math.min(64, prev + 2))}
                className="p-1 hover:bg-slate-100 rounded text-slate-500 transition-colors"
                title="Increase Font Size"
              >
                <Plus size={14} />
              </button>
            </div>

            <button onClick={onClose} className="p-2 text-slate-400 hover:bg-slate-200 rounded-lg transition-colors">
              <X size={20} />
            </button>
          </div>
        </div>

        <div className="flex-grow p-10 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/paper-fibers.png')]">
          {isEditing ? (
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-full p-6 uyghur-text border border-indigo-200 rounded-xl focus:ring-4 focus:ring-indigo-500/10 outline-none resize-none bg-white shadow-inner"
              style={{ fontSize: `${fontSize}px` }}
              dir="rtl"
            />
          ) : (
            <div className="max-w-3xl mx-auto space-y-12 pb-32">
              {selectedBook.results.sort((a, b) => a.pageNumber - b.pageNumber).map((page) => (
                <div
                  key={page.pageNumber}
                  onMouseEnter={() => setCurrentPage(page.pageNumber)}
                  className={`relative p-8 rounded-2xl transition-all duration-300 ${currentPage === page.pageNumber ? 'bg-white shadow-xl ring-1 ring-indigo-100 scale-[1.02]' : 'bg-transparent opacity-80'}`}
                >
                  <div className="absolute top-4 left-4 flex items-center gap-4">
                    <div className="text-[10px] font-bold text-slate-300 font-mono uppercase tracking-widest">
                      Page {page.pageNumber}
                    </div>
                    <button
                      onClick={() => onReProcessPage(selectedBook.id, page.pageNumber)}
                      className="p-1 px-2 bg-indigo-50 text-indigo-600 rounded text-[9px] font-bold hover:bg-indigo-600 hover:text-white transition-all opacity-0 group-hover:opacity-100 flex items-center gap-1 shadow-sm"
                    >
                      <RotateCcw size={10} /> RE-OCR PAGE
                    </button>
                    <button
                      onClick={() => { setEditingPageNum(page.pageNumber); setTempPageText(page.text || ''); }}
                      className="p-1 px-2 bg-slate-50 text-slate-600 rounded text-[9px] font-bold hover:bg-slate-600 hover:text-white transition-all opacity-0 group-hover:opacity-100 flex items-center gap-1 shadow-sm"
                    >
                      <Edit3 size={10} /> EDIT TEXT
                    </button>
                  </div>

                  {editingPageNum === page.pageNumber ? (
                    <div className="flex flex-col gap-4">
                      <textarea
                        value={tempPageText}
                        onChange={(e) => setTempPageText(e.target.value)}
                        className="w-full h-64 p-4 uyghur-text border border-indigo-200 rounded-xl focus:ring-4 focus:ring-indigo-500/10 outline-none resize-none bg-white font-medium"
                        style={{ fontSize: `${fontSize}px` }}
                        dir="rtl"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => onUpdatePage(selectedBook.id, page.pageNumber, tempPageText)}
                          className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-bold flex items-center gap-2"
                        >
                          <Save size={16} /> Save Changes & Update RAG
                        </button>
                        <button
                          onClick={() => setEditingPageNum(null)}
                          className="px-4 py-2 bg-slate-100 text-slate-600 rounded-lg text-sm font-bold"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {(page.status === 'pending' || page.status === 'processing') && (
                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 text-indigo-400">
                          <Loader2 size={32} className="animate-spin" />
                        </div>
                      )}
                      <div
                        className="uyghur-text text-slate-800 leading-relaxed whitespace-pre-wrap"
                        style={{ fontSize: `${fontSize}px` }}
                      >
                        {page.text || "..."}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="w-[420px] flex flex-col gap-4">
        <ChatInterface
          type="book"
          chatMessages={chatMessages}
          chatInput={chatInput}
          setChatInput={setChatInput}
          onSendMessage={onSendMessage}
          isChatting={isChatting}
          currentPage={currentPage}
          chatContainerRef={chatContainerRef}
        />
      </div>
    </div>
  );
};
