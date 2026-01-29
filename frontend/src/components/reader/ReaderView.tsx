import React, { useEffect, useRef } from 'react';
import {
  X, Type, Minus, Plus, Edit3, Save, MessageSquare,
  RotateCcw, Wand2, ChevronRight, ChevronLeft, CheckCircle2, Loader2
} from 'lucide-react';
import { Book } from '../../types';
import { ChatInterface } from '../chat/ChatInterface';
import { SpellCheckPanel } from '../spell-check/SpellCheckPanel';
import { HighlightedText } from '../spell-check/HighlightedText';
import { useSpellCheck } from '../../hooks/useSpellCheck';

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
  setModal: (modal: any) => void;
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
  setModal,
}) => {
  const pageTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const globalTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const [shouldRunSpellCheck, setShouldRunSpellCheck] = React.useState(false);

  // Auto-resize textarea for page edit
  useEffect(() => {
    if (pageTextAreaRef.current) {
      pageTextAreaRef.current.style.height = 'auto';
      pageTextAreaRef.current.style.height = `${pageTextAreaRef.current.scrollHeight}px`;
    }
  }, [tempPageText, editingPageNum]);

  // Auto-resize textarea for global edit
  useEffect(() => {
    if (globalTextAreaRef.current && isEditing) {
      globalTextAreaRef.current.style.height = 'auto';
      globalTextAreaRef.current.style.height = `${globalTextAreaRef.current.scrollHeight}px`;
    }
  }, [editContent, isEditing]);

  const {
    isChecking,
    spellCheckResult,
    appliedCorrections,
    ignoredCorrections,
    runSpellCheck,
    applyCorrection,
    ignoreCorrection,
    resetSpellCheck,
  } = useSpellCheck(selectedBook.id, editingPageNum || 0);

  // Trigger auto-spell check when entering edit mode via the magic button
  useEffect(() => {
    if (editingPageNum !== null && shouldRunSpellCheck && tempPageText) {
      runSpellCheck(tempPageText);
      setShouldRunSpellCheck(false);
    }
  }, [editingPageNum, shouldRunSpellCheck, tempPageText]);

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
            <div className="flex items-center gap-3">
              {!isEditing ? (
                <button
                  onClick={() => setIsEditing(true)}
                  className="flex items-center gap-1.5 px-5 py-[10px] bg-indigo-50 text-indigo-600 text-[11px] font-black rounded-xl hover:bg-indigo-600 hover:text-white transition-all active:scale-95 shadow-sm shadow-indigo-100/50 uppercase tracking-tight"
                >
                  <Edit3 size={16} className="stroke-[3]" /> EDIT BOOK
                </button>
              ) : (
                <button
                  onClick={onSaveCorrections}
                  className="flex items-center gap-1.5 px-5 py-[10px] bg-indigo-600 text-white text-[11px] font-black rounded-xl hover:bg-indigo-700 transition-all active:scale-95 shadow-md shadow-indigo-100 uppercase tracking-tight"
                >
                  <Save size={16} className="stroke-[3]" /> UPDATE KNOWLEDGE BASE
                </button>
              )}
              <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-xl p-1 shadow-sm">
                <button
                  onClick={() => setFontSize(prev => Math.max(12, prev - 2))}
                  className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors active:scale-90"
                  title="Decrease Font Size"
                >
                  <Minus size={14} />
                </button>
                <div className="flex items-center gap-1 px-3 text-slate-400 border-x border-slate-100">
                  <Type size={14} />
                  <span className="text-[11px] font-bold font-mono text-slate-600">{fontSize}</span>
                </div>
                <button
                  onClick={() => setFontSize(prev => Math.min(64, prev + 2))}
                  className="p-1.5 hover:bg-slate-100 rounded-lg text-slate-500 transition-colors active:scale-90"
                  title="Increase Font Size"
                >
                  <Plus size={14} />
                </button>
              </div>

              <button
                onClick={() => {
                  if (isEditing) {
                    setIsEditing(false);
                  } else if (editingPageNum !== null) {
                    setEditingPageNum(null);
                    resetSpellCheck();
                  } else {
                    onClose();
                  }
                }}
                className="p-2 text-slate-400 hover:bg-red-50 hover:text-red-500 rounded-xl transition-all active:scale-95"
                aria-label="Close Reader"
              >
                <X size={20} />
              </button>
            </div>
          </div>
        </div>

        <div className="flex-grow p-10 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/paper-fibers.png')]">
          {isEditing ? (
            <textarea
              ref={globalTextAreaRef}
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full p-6 uyghur-text border border-indigo-200 rounded-xl focus:ring-4 focus:ring-indigo-500/10 outline-none resize-none bg-white shadow-inner overflow-hidden"
              style={{ fontSize: `${fontSize}px` }}
              dir="rtl"
            />
          ) : (
            <div className="max-w-3xl mx-auto space-y-12 pb-32">
              {[...selectedBook.results]
                .sort((a, b) => Number(a.pageNumber) - Number(b.pageNumber))
                // Deduplicate by pageNumber just in case
                .filter((page, index, self) =>
                  self.findIndex(p => p.pageNumber === page.pageNumber) === index
                )
                .filter(page => editingPageNum === null || Number(page.pageNumber) === Number(editingPageNum))
                .map((page) => (
                  <div
                    key={page.pageNumber}
                    onMouseEnter={() => setCurrentPage(page.pageNumber)}
                    className={`group relative p-8 rounded-2xl transition-all duration-300 ${currentPage === page.pageNumber ? 'bg-white shadow-xl ring-1 ring-indigo-100 scale-[1.02]' : 'bg-transparent opacity-80'}`}
                  >
                    <div className="flex items-center justify-between border-b border-transparent group-hover:border-slate-100 pb-4 mb-6 transition-colors">
                      <div className="flex items-center gap-3">
                        <span className="text-[11px] font-black text-slate-400 font-mono tracking-tighter uppercase">
                          PAGE {page.pageNumber}
                        </span>
                        {page.isVerified && (
                          <div className="flex items-center gap-1 text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full ring-1 ring-emerald-500/20 shadow-sm shadow-emerald-100/50">
                            <CheckCircle2 size={10} className="stroke-[3]" />
                            <span className="text-[9px] font-black tracking-tight">VERIFIED</span>
                          </div>
                        )}
                      </div>

                      {editingPageNum === null && (
                        <div className="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-all duration-300">
                          <button
                            onClick={() => {
                              if (page.isVerified) {
                                setModal({
                                  isOpen: true,
                                  title: "Confirm Re-OCR",
                                  message: "This page has manual edits or verifications. Re-OCR will delete your work and replace it with fresh AI reading. Are you sure?",
                                  type: 'confirm',
                                  confirmText: "RE-OCR anyway",
                                  onConfirm: () => {
                                    onReProcessPage(selectedBook.id, page.pageNumber);
                                    setModal((prev: any) => ({ ...prev, isOpen: false }));
                                  }
                                });
                              } else {
                                onReProcessPage(selectedBook.id, page.pageNumber);
                              }
                            }}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-600 text-indigo-600 hover:text-white rounded-lg text-[9px] font-black transition-all active:scale-95 shadow-sm shadow-indigo-100/50"
                          >
                            <RotateCcw size={10} className="stroke-[3]" /> RE-OCR PAGE
                          </button>
                          <button
                            onClick={() => {
                              setEditingPageNum(page.pageNumber);
                              setTempPageText(page.text || '');
                            }}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-600 text-indigo-600 hover:text-white rounded-lg text-[9px] font-black transition-all active:scale-95 shadow-sm shadow-indigo-100/50"
                          >
                            <Edit3 size={10} className="stroke-[3]" /> EDIT PAGE
                          </button>
                          <button
                            onClick={() => {
                              setEditingPageNum(page.pageNumber);
                              setTempPageText(page.text || '');
                              setShouldRunSpellCheck(true);
                            }}
                            className="flex items-center gap-1 px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-600 text-indigo-600 hover:text-white rounded-lg text-[9px] font-black transition-all active:scale-95 shadow-sm shadow-indigo-100/50"
                          >
                            <Wand2 size={10} className="stroke-[3]" /> SPELL CHECK
                          </button>
                        </div>
                      )}
                    </div>

                    {Number(editingPageNum) === Number(page.pageNumber) ? (
                      <div className="flex flex-col gap-4">
                        <div className="relative w-full">
                          {spellCheckResult && spellCheckResult.corrections.length > 0 && (
                            <div className="absolute inset-0 p-4 pointer-events-none overflow-hidden">
                              <HighlightedText
                                text={tempPageText}
                                corrections={spellCheckResult.corrections}
                                className="uyghur-text leading-relaxed whitespace-pre-wrap"
                                style={{ fontSize: `${fontSize}px` }}
                                isLayer={true}
                              />
                            </div>
                          )}
                          <textarea
                            ref={pageTextAreaRef}
                            value={tempPageText}
                            onChange={(e) => setTempPageText(e.target.value)}
                            className="w-full p-4 uyghur-text border border-indigo-200 rounded-xl focus:ring-4 focus:ring-indigo-500/10 outline-none resize-none bg-white/50 relative z-10 font-medium overflow-hidden leading-relaxed"
                            style={{ fontSize: `${fontSize}px`, backgroundColor: 'transparent' }}
                            dir="rtl"
                          />
                        </div>
                        <div className="flex items-center gap-3 mt-2">
                          <button
                            onClick={() => {
                              onUpdatePage(selectedBook.id, page.pageNumber, tempPageText);
                              resetSpellCheck();
                            }}
                            className="px-6 py-2.5 bg-indigo-600 text-white rounded-xl text-xs font-black hover:bg-indigo-700 transition-all active:scale-95 flex items-center gap-2 shadow-lg shadow-indigo-100/50"
                          >
                            <Save size={14} className="stroke-[3]" /> SAVE & VERIFY PAGE
                          </button>
                          <button
                            onClick={() => {
                              setEditingPageNum(null);
                              resetSpellCheck();
                            }}
                            className="px-6 py-2.5 bg-slate-100 text-slate-600 rounded-xl text-xs font-black hover:bg-slate-200 transition-all active:scale-95"
                          >
                            CANCEL
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
        {editingPageNum !== null ? (
          <SpellCheckPanel
            bookId={selectedBook.id}
            pageNumber={editingPageNum}
            pageText={tempPageText}
            isChecking={isChecking}
            spellCheckResult={spellCheckResult}
            onRunSpellCheck={() => runSpellCheck(tempPageText)}
            onApplyCorrection={(correction) => {
              const newText = applyCorrection(correction, tempPageText);
              setTempPageText(newText);
            }}
            onIgnoreCorrection={ignoreCorrection}
            appliedCorrections={appliedCorrections}
            ignoredCorrections={ignoredCorrections}
          />
        ) : (
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
        )}
      </div>
    </div>
  );
};
