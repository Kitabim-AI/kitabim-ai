import React, { useEffect, useRef } from 'react';
import {
  X, Type, Minus, Plus, Edit3, Save, MessageSquare,
  RotateCcw, Wand2, ChevronRight, ChevronLeft, CheckCircle2, Loader2, BookOpen
} from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { ChatInterface } from '../chat/ChatInterface';
import { SpellCheckPanel } from '../spell-check/SpellCheckPanel';
import { HighlightedText } from '../spell-check/HighlightedText';
import { useSpellCheck } from '../../hooks/useSpellCheck';
import { MarkdownContent } from '../common/MarkdownContent';
import { GlassPanel } from '../ui/GlassPanel';

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

import { PersistenceService } from '../../services/persistenceService';

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
  const { t } = useI18n();
  const pageTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const globalTextAreaRef = useRef<HTMLTextAreaElement>(null);

  const [shouldRunSpellCheck, setShouldRunSpellCheck] = React.useState(false);
  const [loadedPages, setLoadedPages] = React.useState<any[]>(selectedBook.pages || []);
  const [isLoadingMore, setIsLoadingMore] = React.useState(false);
  const [hasMorePages, setHasMorePages] = React.useState(true);
  const observerTarget = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [isFetchingContent, setIsFetchingContent] = React.useState(false);

  useEffect(() => {
    // Initial sync
    setLoadedPages(selectedBook.pages || []);
  }, [selectedBook.id]); // Only reset on book change, rely on subsequent fetch logic for updates

  // Auto-resize textarea for page edit
  useEffect(() => {
    if (pageTextAreaRef.current) {
      pageTextAreaRef.current.style.height = 'auto';
      pageTextAreaRef.current.style.height = `${pageTextAreaRef.current.scrollHeight}px`;
    }
  }, [tempPageText, editingPageNum]);

  const fetchMorePages = React.useCallback(async () => {
    if (isLoadingMore || !hasMorePages) return;
    setIsLoadingMore(true);

    try {
      const currentLength = loadedPages.length;
      const newPages = await PersistenceService.getBookPages(selectedBook.id, currentLength, 10000);

      if (newPages.length === 0) {
        setHasMorePages(false);
      } else {
        setLoadedPages(prev => {
          // De-duplicate in case of race conditions or overlaps
          const existingIds = new Set(prev.map(p => p.pageNumber));
          const uniqueNew = newPages.filter((p: any) => !existingIds.has(p.pageNumber));
          return [...prev, ...uniqueNew].sort((a, b) => Number(a.pageNumber) - Number(b.pageNumber));
        });
      }
    } catch (err) {
      console.error("Failed to load more pages", err);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMorePages, loadedPages.length, selectedBook.id]);


  useEffect(() => {
    const observer = new IntersectionObserver(
      entries => {
        if (entries[0].isIntersecting) {
          fetchMorePages();
        }
      },
      { threshold: 0.1, rootMargin: '400px' }
    );

    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }

    return () => observer.disconnect();
  }, [fetchMorePages]);


  // Sync changes from parent, but preserve text for currently editing page
  useEffect(() => {
    if (selectedBook.pages && selectedBook.pages.length > 0) {
      setLoadedPages(prev => {
        const prevMap = new Map<number, any>(prev.map(p => [p.pageNumber, p]));
        let hasChanges = false;

        selectedBook.pages.forEach(p => {
          const existing = prevMap.get(p.pageNumber);

          if (!existing) {
            // New page - add it
            prevMap.set(p.pageNumber, p);
            hasChanges = true;
            console.log('[ReaderView] Added new page:', p.pageNumber);
          } else {
            // If this page is currently being edited, only sync status/error to preserve unsaved edits
            // Otherwise, sync everything including text
            const isCurrentlyEditing = editingPageNum !== null && Number(p.pageNumber) === Number(editingPageNum);

            if (isCurrentlyEditing) {
              // Preserve local text and isVerified for the page being edited
              if (existing.status !== p.status || existing.error !== p.error) {
                prevMap.set(p.pageNumber, { ...existing, status: p.status, error: p.error });
                hasChanges = true;
                console.log('[ReaderView] Updated status for editing page:', p.pageNumber);
              }
            } else {
              // For non-editing pages, sync everything from parent
              if (existing.text !== p.text || existing.isVerified !== p.isVerified ||
                existing.status !== p.status || existing.error !== p.error) {
                prevMap.set(p.pageNumber, p);
                hasChanges = true;
                console.log('[ReaderView] Synced page from parent:', p.pageNumber);
              }
            }
          }
        });

        if (hasChanges) {
          return Array.from(prevMap.values()).sort((a, b) => Number(a.pageNumber) - Number(b.pageNumber));
        }
        return prev;
      });
    }
  }, [selectedBook.pages, editingPageNum]);


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

  // Fetch full content when entering global edit mode if not already loaded
  const handleEnterGlobalEdit = async () => {
    setIsEditing(true);

    if (!editContent && !isFetchingContent) {
      setIsFetchingContent(true);
      try {
        const content = await PersistenceService.getBookContent(selectedBook.id);
        setEditContent(content);
      } catch (err) {
        console.error("Failed to fetch full book content:", err);
      } finally {
        setIsFetchingContent(false);
      }
    }
  };

  return (
    <div className="h-[calc(100vh-140px)] flex flex-row-reverse gap-6 animate-fade-in py-4">
      {/* Main Content Area */}
      <div className="flex-grow glass-panel flex flex-col overflow-hidden" style={{ borderRadius: '32px' }}>
        {/* Header Ribbon */}
        <div className="px-8 py-5 border-b border-[#0369a1]/10 flex items-center justify-between bg-white/40">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
              <BookOpen size={20} />
            </div>
            <div>
              <h2 className="font-black text-[#1a1a1a] text-lg">{selectedBook.title}</h2>
              {selectedBook.tags && selectedBook.tags.length > 0 && (
                <div className="flex gap-1.5 mt-1">
                  {selectedBook.tags.map((tag, i) => (
                    <span key={i} className="text-[14px] bg-[#0369a1]/10 text-[#0369a1] px-2 py-0.5 rounded-md font-bold uppercase tracking-wider">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-3">
              {!isEditing ? (
                <button
                  onClick={handleEnterGlobalEdit}
                  className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white text-sm font-black rounded-2xl hover:bg-[#0284c7] transition-all active:scale-95 shadow-md uppercase tracking-widest border border-[#0369a1]/20"
                >
                  <Edit3 size={16} /> {t('common.edit')}
                </button>
              ) : (
                <button
                  onClick={onSaveCorrections}
                  className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white text-sm font-black rounded-2xl hover:bg-[#0284c7] transition-all active:scale-95 shadow-lg uppercase tracking-widest"
                >
                  <Save size={16} /> {t('common.save')}
                </button>
              )}

              <div className="flex items-center gap-1 bg-white/60 backdrop-blur-md border border-[#0369a1]/20 rounded-2xl p-1.5 shadow-sm">
                <button
                  onClick={() => setFontSize(prev => Math.max(14, prev - 2))}
                  className="p-2 hover:bg-[#0369a1]/10 rounded-xl text-[#0369a1] transition-all active:scale-90"
                >
                  <Minus size={16} />
                </button>
                <div className="flex items-center gap-2 px-4 border-x border-[#0369a1]/10">
                  <Type size={16} className="text-[#94a3b8]" />
                  <span className="text-sm font-black text-[#1a1a1a]">{fontSize}</span>
                </div>
                <button
                  onClick={() => setFontSize(prev => Math.min(64, prev + 2))}
                  className="p-2 hover:bg-[#0369a1]/10 rounded-xl text-[#0369a1] transition-all active:scale-90"
                >
                  <Plus size={16} />
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
                className="p-3 text-[#94a3b8] hover:bg-red-50 hover:text-red-500 rounded-2xl transition-all active:scale-95"
              >
                <X size={24} />
              </button>
            </div>
          </div>
        </div>

        {/* Reading Canvas */}
        <div
          dir="rtl"
          className={`flex-grow custom-scrollbar ${isEditing ? 'p-4 flex flex-col' : 'p-6 overflow-y-auto'}`}
          style={{
            background: 'linear-gradient(rgba(255,255,255,0.7), rgba(255,255,255,0.7)), url("https://www.transparenttextures.com/patterns/paper-fibers.png")'
          }}
        >
          {isEditing ? (
            <div className="flex-grow flex flex-col relative" dir="rtl">
              {isFetchingContent && (
                <div className="absolute inset-0 bg-white/60 backdrop-blur-md z-20 flex items-center justify-center rounded-3xl">
                  <div className="flex flex-col items-center gap-4">
                    <Loader2 className="w-10 h-10 text-[#0369a1] animate-spin" />
                    <span className="text-sm font-black text-[#0369a1] uppercase tracking-widest animate-pulse">{t('common.loading')}</span>
                  </div>
                </div>
              )}
              <textarea
                ref={globalTextAreaRef}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="flex-grow w-full p-6 uyghur-text border-2 border-[#0369a1]/10 rounded-3xl focus:border-[#0369a1] outline-none resize-none bg-white shadow-inner overflow-y-auto leading-relaxed text-[#1a1a1a]"
                style={{ fontSize: `${fontSize}px`, minHeight: '500px' }}
                dir="rtl"
                placeholder={isFetchingContent ? "" : t('common.enterContent')}
              />
            </div>
          ) : (
            <div className="max-w-5xl mx-auto space-y-16 pb-40 px-4" dir="rtl">
              {[...loadedPages]
                .sort((a, b) => Number(a.pageNumber) - Number(b.pageNumber))
                .filter((page, index, self) =>
                  self.findIndex(p => p.pageNumber === page.pageNumber) === index
                )
                .filter(page => editingPageNum === null || Number(page.pageNumber) === Number(editingPageNum))
                .map((page) => (
                  <div
                    key={page.pageNumber}
                    ref={(el) => {
                      if (el) {
                        pageRefs.current.set(page.pageNumber, el);
                      } else {
                        pageRefs.current.delete(page.pageNumber);
                      }
                    }}
                    onMouseEnter={() => setCurrentPage(page.pageNumber)}
                    className={`group relative p-8 rounded-[32px] transition-all duration-500 ${currentPage === page.pageNumber ? 'bg-white shadow-2xl ring-1 ring-[#0369a1]/10 scale-[1.03]' : 'bg-transparent opacity-80 scale-100'}`}
                  >
                    <div className="flex items-center justify-between pb-6 mb-8 border-b border-[#0369a1]/5">
                      <div className="flex items-center gap-4">
                        <span className="text-[14px] font-black text-[#94a3b8] tracking-widest uppercase">
                          {t('common.page')} {page.pageNumber}
                        </span>
                        {currentPage === page.pageNumber && (page.status === 'pending' || page.status === 'processing') && (
                          <div className="flex items-center gap-2 px-3 py-1 bg-[#0369a1]/10 rounded-full">
                            <Loader2 size={12} className="text-[#0369a1] animate-spin" />
                            <span className="text-[14px] font-black text-[#0369a1]">{t('admin.table.recognizing')}</span>
                          </div>
                        )}
                        {page.isVerified && (
                          <div className="flex items-center gap-2 text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-500/10 shadow-sm">
                            <CheckCircle2 size={12} strokeWidth={3} />
                            <span className="text-[14px] font-black tracking-widest uppercase">{t('reader.verified')}</span>
                          </div>
                        )}
                      </div>

                      {editingPageNum === null && (
                        <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-all duration-300">
                          <button
                            onClick={() => {
                              if (page.isVerified) {
                                setModal({
                                  isOpen: true,
                                  title: t('reader.reprocess.title'),
                                  message: t('reader.reprocess.message'),
                                  type: 'confirm',
                                  confirmText: t('reader.reprocess.confirm'),
                                  destructive: true,
                                  onConfirm: () => {
                                    onReProcessPage(selectedBook.id, page.pageNumber);
                                    setModal((prev: any) => ({ ...prev, isOpen: false }));
                                  }
                                });
                              } else {
                                onReProcessPage(selectedBook.id, page.pageNumber);
                              }
                            }}
                            className="p-2.5 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-xl transition-all shadow-sm"
                            title={t('reader.reprocess.confirm')}
                          >
                            <RotateCcw size={16} strokeWidth={3} />
                          </button>
                          <button
                            onClick={() => {
                              setEditingPageNum(page.pageNumber);
                              setTempPageText(page.text || '');
                            }}
                            className="flex items-center gap-2 px-4 py-2 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-xl text-[14px] font-black transition-all active:scale-95 shadow-sm uppercase tracking-widest border border-[#0369a1]/10"
                          >
                            <Edit3 size={14} strokeWidth={3} /> {t('common.edit')}
                          </button>
                          <button
                            onClick={() => {
                              setEditingPageNum(page.pageNumber);
                              setTempPageText(page.text || '');
                              setShouldRunSpellCheck(true);
                            }}
                            className="p-2.5 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-xl transition-all shadow-sm"
                            title={t('spellCheck.runCheck')}
                          >
                            <Wand2 size={16} strokeWidth={3} />
                          </button>
                        </div>
                      )}
                    </div>

                    {Number(editingPageNum) === Number(page.pageNumber) ? (
                      <div className="flex flex-col gap-6">
                        <div className="relative w-full">
                          {spellCheckResult && spellCheckResult.corrections.length > 0 && (
                            <div className="absolute inset-0 p-6 pointer-events-none overflow-hidden">
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
                            className="w-full p-6 uyghur-text border-2 border-[#0369a1] rounded-2xl focus:ring-8 focus:ring-[#0369a1]/5 outline-none resize-none bg-white relative z-10 font-bold overflow-hidden leading-relaxed"
                            style={{ fontSize: `${fontSize}px`, backgroundColor: 'white' }}
                            dir="rtl"
                          />
                        </div>
                        <div className="flex items-center gap-4 mt-2">
                          <button
                            onClick={() => {
                              const pageNum = page.pageNumber;
                              setLoadedPages(prev => prev.map(p =>
                                p.pageNumber === pageNum
                                  ? { ...p, text: tempPageText, isVerified: true }
                                  : p
                              ));
                              onUpdatePage(selectedBook.id, pageNum, tempPageText);
                              resetSpellCheck();
                              setTimeout(() => {
                                const pageElement = pageRefs.current.get(pageNum);
                                if (pageElement) {
                                  pageElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                }
                              }, 200);
                            }}
                            className="px-8 py-3.5 bg-[#0369a1] text-white rounded-[20px] text-sm font-black hover:bg-[#0284c7] transition-all active:scale-95 flex items-center gap-3 shadow-xl shadow-[#0369a1]/20"
                          >
                            <Save size={18} strokeWidth={3} /> {t('common.save')}
                          </button>
                          <button
                            onClick={() => {
                              setEditingPageNum(null);
                              resetSpellCheck();
                            }}
                            className="px-8 py-3.5 bg-slate-100 text-[#94a3b8] rounded-[20px] text-sm font-black hover:bg-slate-200 transition-all active:scale-95"
                          >
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    ) : (
                      page.status === 'pending' || page.status === 'processing' ? (
                        <div className="flex flex-col items-center justify-center py-24">
                          <div className="relative">
                            <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                            <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                              <RotateCcw size={20} className="animate-pulse" />
                            </div>
                          </div>
                          <span className="mt-6 text-sm font-black uppercase tracking-[0.2em] text-[#94a3b8] animate-pulse">{t('reader.activeRecognizing')}</span>
                        </div>
                      ) : (
                        <MarkdownContent
                          key={`page-${page.pageNumber}-${page.isVerified ? 'verified' : 'unverified'}-${(page.text || '').length}`}
                          content={page.text || "..."}
                          className="uyghur-text text-[#1a1a1a] leading-[1.8]"
                          style={{ fontSize: `${fontSize}px` }}
                        />
                      )
                    )}
                  </div>
                ))}

              {/* Loader Element for Intersection Observer */}
              {hasMorePages && !isEditing && (
                <div ref={observerTarget} className="flex justify-center p-12">
                  {isLoadingMore && (
                    <div className="flex flex-col items-center gap-4">
                      <div className="w-10 h-10 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                      <span className="text-[14px] text-[#94a3b8] font-black uppercase tracking-widest">{t('common.loadingMore')}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar Area */}
      <div className="w-[550px] flex flex-col gap-6">
        {editingPageNum !== null ? (
          <GlassPanel className="h-full flex flex-col overflow-hidden" style={{ borderRadius: '32px', padding: '24px' }}>
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
          </GlassPanel>
        ) : (
          <GlassPanel className="h-full flex flex-col overflow-hidden" style={{ borderRadius: '32px', padding: '24px' }}>
            <ChatInterface
              type="book"
              chatMessages={chatMessages}
              chatInput={chatInput}
              setChatInput={setChatInput}
              onSendMessage={onSendMessage}
              isChatting={isChatting}
              currentPage={currentPage}
              chatContainerRef={chatContainerRef}
              onClose={onClose}
            />
          </GlassPanel>
        )}
      </div>
    </div>
  );
};
