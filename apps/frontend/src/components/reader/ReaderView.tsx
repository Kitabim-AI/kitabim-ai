import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  X, Type, Minus, Plus, Edit3, Save, MessageSquare,
  RotateCcw, Wand2, ChevronRight, ChevronLeft, CheckCircle2, Loader2, BookOpen
} from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { ChatInterface } from '../chat/ChatInterface';
import { SpellCheckPanel } from '../spell-check/SpellCheckPanel';
import { useSpellCheck } from '../../hooks/useSpellCheck';
import { GlassPanel } from '../ui/GlassPanel';
import { useIsEditor, useAuth } from '../../hooks/useAuth';
import { useAppContext } from '../../context/AppContext';
import { PersistenceService } from '../../services/persistenceService';
import { PageItem } from './PageItem';
import VirtualScrollReader from './VirtualScrollReader';

export const ReaderView: React.FC = () => {
  const {
    selectedBook,
    view,
    setView,
    previousView,
    currentPage,
    setCurrentPage,
    chat,
    bookActions,
    setModal
  } = useAppContext();

  if (!selectedBook) return null;

  const { t } = useI18n();
  const isEditor = useIsEditor();
  const { isAuthenticated, user } = useAuth();
  const isGuestOrReader = !isAuthenticated || (user?.role === 'reader');

  // Reader-specific state
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [fontSize, setFontSize] = useState(20);
  const [editingPageNum, setEditingPageNum] = useState<number | null>(null);
  const [tempPageText, setTempPageText] = useState('');
  const [pageInput, setPageInput] = useState((currentPage || 1).toString());
  const [shouldRunSpellCheck, setShouldRunSpellCheck] = useState(false);
  const [loadedPages, setLoadedPages] = useState<any[]>(selectedBook.pages || []);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMorePages, setHasMorePages] = useState(true);
  const [isFetchingContent, setIsFetchingContent] = useState(false);
  const [mobileTab, setMobileTab] = useState<'reader' | 'chat'>('reader');

  const pageTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const globalTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const observerTarget = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const mainScrollRef = useRef<HTMLDivElement>(null);

  const onClose = () => setView(previousView);

  useEffect(() => {
    if (isGuestOrReader) {
      setLoadedPages([]);
    } else {
      setLoadedPages(selectedBook.pages || []);
    }
  }, [selectedBook.id, isGuestOrReader]);

  useEffect(() => {
    if (isGuestOrReader && currentPage !== null) {
      const fetchSpecificPage = async () => {
        setIsLoadingMore(true);
        try {
          const pages = await PersistenceService.getBookPages(selectedBook.id, currentPage - 1, 1);
          setLoadedPages(pages);
          setPageInput(currentPage.toString());
        } catch (err) {
          console.error("Failed to fetch requested page", err);
        } finally {
          setIsLoadingMore(false);
        }
      };
      fetchSpecificPage();
    }
  }, [selectedBook.id, currentPage, isGuestOrReader]);

  useEffect(() => {
    if (currentPage !== null) {
      setPageInput(currentPage.toString());
    }
  }, [currentPage]);

  useEffect(() => {
    if (pageTextAreaRef.current) {
      pageTextAreaRef.current.style.height = 'auto';
      pageTextAreaRef.current.style.height = `${pageTextAreaRef.current.scrollHeight}px`;
    }
  }, [tempPageText, editingPageNum]);

  const fetchMorePages = useCallback(async () => {
    if (isLoadingMore || !hasMorePages || isGuestOrReader) return;
    setIsLoadingMore(true);

    try {
      const currentLength = loadedPages.length;
      const newPages = await PersistenceService.getBookPages(selectedBook.id, currentLength, 10000);

      if (newPages.length === 0) {
        setHasMorePages(false);
      } else {
        setLoadedPages(prev => {
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
  }, [isLoadingMore, hasMorePages, loadedPages.length, selectedBook.id, isGuestOrReader]);

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

  useEffect(() => {
    if (selectedBook.pages && selectedBook.pages.length > 0) {
      setLoadedPages(prev => {
        const prevMap = new Map<number, any>(prev.map(p => [p.pageNumber, p]));
        let hasChanges = false;

        selectedBook.pages.forEach(p => {
          const existing = prevMap.get(p.pageNumber);
          if (!existing) {
            prevMap.set(p.pageNumber, p);
            hasChanges = true;
          } else {
            const isCurrentlyEditing = editingPageNum !== null && Number(p.pageNumber) === Number(editingPageNum);
            if (isCurrentlyEditing) {
              if (existing.status !== p.status || existing.error !== p.error) {
                prevMap.set(p.pageNumber, { ...existing, status: p.status, error: p.error });
                hasChanges = true;
              }
            } else {
              if (existing.text !== p.text || existing.isVerified !== p.isVerified ||
                existing.status !== p.status || existing.error !== p.error) {
                prevMap.set(p.pageNumber, p);
                hasChanges = true;
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
    isChecking: isCheckingSpell,
    spellCheckResult,
    appliedCorrections,
    ignoredCorrections,
    runSpellCheck,
    applyCorrection,
    ignoreCorrection,
    resetSpellCheck,
  } = useSpellCheck(selectedBook.id, editingPageNum || 0);

  useEffect(() => {
    if (editingPageNum !== null && shouldRunSpellCheck && tempPageText) {
      runSpellCheck(tempPageText);
      setShouldRunSpellCheck(false);
    }
  }, [editingPageNum, shouldRunSpellCheck, tempPageText, runSpellCheck]);

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

  const handleSaveCorrections = () => {
    bookActions.saveCorrections(selectedBook, editContent, setIsEditing);
  };

  const [isSaving, setIsSaving] = useState(false);

  const handleUpdatePage = async (id: string, num: number, text: string) => {
    setIsSaving(true);
    try {
      await bookActions.handleUpdatePage(id, num, text, setEditingPageNum);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="h-[calc(100vh-100px)] sm:h-[calc(100vh-120px)] md:h-[calc(100vh-140px)] flex flex-col xl:flex-row-reverse gap-4 xl:gap-6 py-2 md:py-4" lang="ug">
      {/* Mobile/Tablet Tab Switcher */}
      <div className="xl:hidden flex gap-2 px-2">
        <button
          onClick={() => setMobileTab('reader')}
          className={`flex-1 flex items-center justify-center gap-3 py-3 px-4 rounded-2xl font-bold text-sm transition-all ${mobileTab === 'reader'
            ? 'bg-[#0369a1] text-white shadow-lg'
            : 'bg-white/60 text-[#64748b] border border-[#0369a1]/10'
            }`}
        >
          <BookOpen className="inline-block" size={18} />
          <span>{t('reader.reading')}</span>
        </button>
        <button
          onClick={() => setMobileTab('chat')}
          className={`flex-1 flex items-center justify-center gap-3 py-3 px-4 rounded-2xl font-bold text-sm transition-all ${mobileTab === 'chat'
            ? 'bg-[#0369a1] text-white shadow-lg'
            : 'bg-white/60 text-[#64748b] border border-[#0369a1]/10'
            }`}
        >
          <MessageSquare className="inline-block" size={18} />
          <span>{t('chat.chat')}</span>
        </button>
      </div>

      {/* Main Content Area */}
      <div className={`flex-grow glass-panel flex-col overflow-hidden rounded-[32px] border border-[#0369a1]/10 shadow-2xl ${mobileTab === 'reader' ? 'flex' : 'hidden xl:flex'}`}>
        {/* Header Ribbon */}
        <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-[#0369a1]/10 flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-4 bg-white/40">
          <div className="flex items-center gap-4">
            <div className="p-2 bg-[#0369a1] text-white rounded-xl shadow-lg">
              <BookOpen size={20} />
            </div>
            <div>
              <h2 className="font-normal text-[#1a1a1a] text-base sm:text-lg">
                {selectedBook.title}
                {selectedBook.volume ? ` (${t('book.volume', { volume: selectedBook.volume })})` : ''}
              </h2>
              {selectedBook.author && (
                <p className="text-xs sm:text-sm text-[#64748b] mt-0.5">
                  {selectedBook.author}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap md:flex-nowrap">
            {isEditor && (
              !isEditing ? (
                <button onClick={handleEnterGlobalEdit} className="flex items-center gap-2 px-3 sm:px-4 py-2.5 min-h-[44px] bg-[#0369a1] text-white text-xs sm:text-sm rounded-2xl hover:bg-[#0284c7] transition-all">
                  <Edit3 size={16} />
                  <span className="hidden sm:inline">{t('reader.editBook')}</span>
                </button>
              ) : (
                <button onClick={handleSaveCorrections} className="flex items-center gap-2 px-3 sm:px-4 py-2.5 min-h-[44px] bg-[#0369a1] text-white text-xs sm:text-sm rounded-2xl hover:bg-[#0284c7] transition-all">
                  <Save size={16} />
                  <span className="hidden sm:inline">{t('common.save')}</span>
                </button>
              )
            )}

            <div className="flex items-center gap-1 bg-white/60 border border-[#0369a1]/20 rounded-2xl p-1 shadow-sm">
              <button onClick={() => setFontSize(prev => Math.max(14, prev - 2))} className="p-2.5 sm:p-2 min-w-[44px] sm:min-w-0 min-h-[44px] sm:min-h-0 hover:bg-[#0369a1]/10 rounded-xl text-[#0369a1] transition-all"><Minus size={18} /></button>
              <span className="text-sm px-2 font-bold min-w-[32px] text-center">{fontSize}</span>
              <button onClick={() => setFontSize(prev => Math.min(64, prev + 2))} className="p-2.5 sm:p-2 min-w-[44px] sm:min-w-0 min-h-[44px] sm:min-h-0 hover:bg-[#0369a1]/10 rounded-xl text-[#0369a1] transition-all"><Plus size={18} /></button>
            </div>


            <button onClick={() => isEditing ? setIsEditing(false) : (editingPageNum !== null ? setEditingPageNum(null) : onClose())} className="p-2.5 min-w-[44px] min-h-[44px] text-[#94a3b8] hover:bg-red-50 hover:text-red-500 rounded-2xl transition-all"><X size={20} /></button>
          </div>
        </div>

        {/* Reading Canvas */}
        <div ref={mainScrollRef} dir="rtl" className={`flex-grow overflow-y-auto custom-scrollbar paper-background ${isEditing ? 'p-3 sm:p-4' : 'p-4 sm:p-6'}`}>
          {isEditing ? (
            <div className="h-full relative">
              {isFetchingContent && <div className="absolute inset-0 bg-white/60 backdrop-blur-sm z-20 flex items-center justify-center"><Loader2 className="w-8 h-8 text-[#0369a1] animate-spin" /></div>}
              <textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} className="w-full h-full p-6 uyghur-text border-2 border-[#0369a1]/10 rounded-3xl outline-none resize-none bg-white shadow-inner" style={{ fontSize: `${fontSize}px` }} placeholder={t('common.enterContent')} />
            </div>
          ) : isGuestOrReader ? (
            <VirtualScrollReader
              bookId={selectedBook.id}
              totalPages={selectedBook.totalPages || (selectedBook as any).total_pages || 0}
              fontSize={fontSize}
              initialPage={currentPage || 1}
              onPageChange={setCurrentPage}
              scrollParentRef={mainScrollRef}
            />
          ) : (
            <div className={`max-w-4xl mx-auto ${isGuestOrReader ? 'pt-8' : 'space-y-16 pb-40'}`}>
              {[...loadedPages]
                .sort((a, b) => a.pageNumber - b.pageNumber)
                .filter(page => isGuestOrReader ? Number(page.pageNumber) === Number(currentPage) : (editingPageNum === null || Number(page.pageNumber) === Number(editingPageNum)))
                .map(page => (
                  <PageItem
                    key={page.pageNumber}
                    page={page}
                    isActive={currentPage === page.pageNumber}
                    isEditing={editingPageNum === page.pageNumber}
                    fontSize={fontSize}
                    onSetActive={() => !isGuestOrReader && setCurrentPage(page.pageNumber)}
                    onEdit={() => { setEditingPageNum(page.pageNumber); setTempPageText(page.text || ''); }}
                    onReprocess={() => bookActions.handleReProcessPage(selectedBook.id, page.pageNumber)}
                    onSpellCheck={() => { setEditingPageNum(page.pageNumber); setTempPageText(page.text || ''); setShouldRunSpellCheck(true); }}
                    tempText={tempPageText}
                    onTempTextChange={setTempPageText}
                    onSave={() => handleUpdatePage(selectedBook.id, page.pageNumber, tempPageText)}
                    onCancel={() => setEditingPageNum(null)}
                    spellCheckResult={spellCheckResult}
                    isLoading={!page.text && (!page.pipelineStep && (page.status === 'ocr_processing' || page.status === 'indexing' || page.status === 'pending')) || (page.pipelineStep === 'ocr' && page.milestone !== 'succeeded')}
                    isSaving={isSaving}
                  />
                ))}
              {!isEditing && !isGuestOrReader && hasMorePages && <div ref={observerTarget} className="h-20 flex items-center justify-center">{isLoadingMore && <Loader2 className="animate-spin text-[#0369a1]" />}</div>}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar Area */}
      <div className={`w-full xl:w-[500px] 2xl:w-[600px] flex-col gap-6 ${mobileTab === 'chat' ? 'flex' : 'hidden xl:flex'}`}>
        <GlassPanel className="h-full flex flex-col overflow-hidden rounded-[32px] p-4 sm:p-6 shadow-xl border border-[#0369a1]/10">
          {editingPageNum !== null ? (
            <SpellCheckPanel
              bookId={selectedBook.id}
              pageNumber={editingPageNum}
              pageText={tempPageText}
              isChecking={isCheckingSpell}
              spellCheckResult={spellCheckResult}
              onRunSpellCheck={() => runSpellCheck(tempPageText)}
              onApplyCorrection={(c) => setTempPageText(applyCorrection(c, tempPageText))}
              onIgnoreCorrection={ignoreCorrection}
              appliedCorrections={appliedCorrections}
              ignoredCorrections={ignoredCorrections}
            />
          ) : (
            <ChatInterface
              type="book"
              chatMessages={chat.chatMessages}
              chatInput={chat.chatInput}
              setChatInput={chat.setChatInput}
              onSendMessage={chat.handleSendMessage}
              isChatting={chat.isChatting}
              streamingMessage={chat.streamingMessage}
              currentPage={currentPage}
              usageStatus={chat.usageStatus}
              chatContainerRef={chat.chatContainerRef}
            />
          )}
        </GlassPanel>
      </div>
    </div>
  );
};
