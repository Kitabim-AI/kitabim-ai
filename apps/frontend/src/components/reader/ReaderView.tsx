import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  X, Type, Minus, Plus, Edit3, Save, MessageSquare,
  RotateCcw, Wand2, ChevronRight, ChevronLeft, CheckCircle2, Loader2, BookOpen,
  Maximize2, Minimize2, Download
} from 'lucide-react';
import { Book } from '@shared/types';
import { useI18n } from '../../i18n/I18nContext';
import { ChatInterface } from '../chat/ChatInterface';
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
    setModal,
    setIsReaderFullscreen,
    fontSize,
    setFontSize,
  } = useAppContext();

  if (!selectedBook) return null;

  const { t } = useI18n();
  const isEditor = useIsEditor();
  const { isAuthenticated, user } = useAuth();
  const isGuestOrReader = !isAuthenticated || (user?.role === 'reader');

  // Reader-specific state
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Sync local fullscreen state → context (so Shell can hide the navbar)
  useEffect(() => {
    setIsReaderFullscreen(isFullscreen);
    return () => setIsReaderFullscreen(false);
  }, [isFullscreen]);

  // Exit fullscreen automatically when screen grows to lg (1024px+)
  useEffect(() => {
    const onResize = () => { if (window.innerWidth >= 1024) setIsFullscreen(false); };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);
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
    spellCheckResult,
    runSpellCheck,
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

  const [isDownloading, setIsDownloading] = useState(false);
  const handleDownload = async () => {
    if (isDownloading) return;
    setIsDownloading(true);
    try {
      const fileName = selectedBook.fileName || `${selectedBook.title || selectedBook.id}.${selectedBook.fileType || 'pdf'}`;
      await PersistenceService.downloadBook(selectedBook.id, fileName);
    } catch (err: any) {
      console.error("Download failed:", err);
      // We could use addNotification here if we had access to it from context directly
      // but selectedBook and other actions are already in useAppContext
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className={isFullscreen
      ? 'fixed inset-0 z-50 flex flex-col bg-[#f0f4f8] notranslate'
      : `h-[calc(100dvh-72px)] sm:h-[calc(100dvh-88px)] md:h-[calc(100dvh-120px)] flex flex-col xl:flex-row-reverse ${mobileTab === 'chat' ? 'gap-3' : 'gap-4'} xl:gap-6 py-0 md:py-4 notranslate`
    } lang="ug" translate="no">
      {/* Mobile/Tablet Tab Switcher */}
      <div className={`xl:hidden flex gap-2 ${mobileTab === 'reader' ? 'px-2' : 'p-2'}${isFullscreen ? ' hidden' : ''}`}>
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
      <div className={`flex-grow glass-panel flex-col overflow-hidden rounded-[32px] border border-[#0369a1]/10 shadow-2xl relative ${mobileTab === 'reader' ? 'flex' : 'hidden xl:flex'}`}>
        {/* Floating minimize button — fullscreen only */}
        {isFullscreen && (
          <button
            onClick={() => setIsFullscreen(false)}
            className="absolute top-4 left-4 z-20 p-2.5 bg-white/80 backdrop-blur-sm text-[#0369a1] hover:bg-white rounded-2xl shadow-lg border border-[#0369a1]/10 transition-all"
            title="Exit fullscreen"
          >
            <Minimize2 size={20} />
          </button>
        )}
        {/* Header Ribbon */}
        <div className={`px-3 sm:px-6 py-2 sm:py-4 border-b border-[#0369a1]/10 flex flex-row items-center justify-between gap-1 sm:gap-4 bg-white/80 backdrop-blur-sm ${isFullscreen ? 'hidden' : ''}`}>
          <div className="flex items-center gap-2 sm:gap-4 min-w-0 flex-shrink">
            <div className="hidden sm:flex p-2 bg-[#0369a1] text-white rounded-xl shadow-lg shrink-0">
              <BookOpen size={20} />
            </div>
            <div className="min-w-0 flex flex-col justify-center">
              <h2
                className="font-bold text-[#1a1a1a] truncate"
                style={{ fontSize: `${fontSize}px` }}
              >
                {selectedBook.title}
                {selectedBook.volume ? ` (${t('book.volume', { volume: selectedBook.volume })})` : ''}
              </h2>
              {selectedBook.author && (
                <p
                  className="text-[#64748b] mt-0.5 truncate hidden sm:block"
                  style={{ fontSize: `${Math.max(12, fontSize - 4)}px` }}
                >
                  {selectedBook.author}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-0.5 sm:gap-2 shrink-0">
            {isEditor && (
              <div className="flex items-center gap-1 sm:gap-2">
                {!isEditing ? (
                  <>
                    <button
                      onClick={handleDownload}
                      disabled={isDownloading}
                      className="flex items-center gap-2 px-2 sm:px-4 py-2 min-h-[36px] sm:min-h-[44px] bg-white border border-[#0369a1]/20 text-[#0369a1] text-xs sm:text-sm rounded-xl sm:rounded-2xl hover:bg-[#0369a1]/10 transition-all font-bold disabled:opacity-50"
                      title={t('common.download')}
                    >
                      {isDownloading ? (
                        <Loader2 size={14} className="animate-spin sm:w-4 sm:h-4" />
                      ) : (
                        <Download size={14} className="sm:w-4 sm:h-4" />
                      )}
                      <span className="hidden sm:inline">{t('common.download')}</span>
                    </button>
                    <button onClick={handleEnterGlobalEdit} className="flex items-center gap-2 px-2 sm:px-4 py-2 min-h-[36px] sm:min-h-[44px] bg-[#0369a1] text-white text-xs sm:text-sm rounded-xl sm:rounded-2xl hover:bg-[#0284c7] transition-all">
                      <Edit3 size={14} className="sm:w-4 sm:h-4" />
                      <span className="hidden sm:inline">{t('reader.editBook')}</span>
                    </button>
                  </>
                ) : (
                  <button onClick={handleSaveCorrections} className="flex items-center gap-2 px-2 sm:px-4 py-2 min-h-[36px] sm:min-h-[44px] bg-[#0369a1] text-white text-xs sm:text-sm rounded-xl sm:rounded-2xl hover:bg-[#0284c7] transition-all">
                    <Save size={14} className="sm:w-4 sm:h-4" />
                    <span className="hidden sm:inline">{t('common.save')}</span>
                  </button>
                )}
              </div>
            )}

            <div className="flex items-center gap-0.5 sm:gap-1 bg-white/60 border border-[#0369a1]/20 rounded-xl sm:rounded-2xl p-0.5 sm:p-1 shadow-sm">
              <button onClick={() => setFontSize(prev => Math.max(14, prev - 2))} className="p-1 sm:p-2 min-w-[32px] sm:min-w-0 min-h-[32px] sm:min-h-0 hover:bg-[#0369a1]/10 rounded-lg text-[#0369a1] transition-all focus:outline-none"><Minus size={16} /></button>
              <span className="text-xs sm:text-sm px-1 font-bold min-w-[20px] text-center">{fontSize}</span>
              <button onClick={() => setFontSize(prev => Math.min(64, prev + 2))} className="p-1 sm:p-2 min-w-[32px] sm:min-w-0 min-h-[32px] sm:min-h-0 hover:bg-[#0369a1]/10 rounded-lg text-[#0369a1] transition-all focus:outline-none"><Plus size={16} /></button>
            </div>


            <button
              onClick={() => setIsFullscreen(prev => !prev)}
              className="lg:hidden p-1.5 sm:p-2.5 min-w-[32px] sm:min-w-[44px] min-h-[32px] sm:min-h-[44px] text-[#94a3b8] hover:bg-[#0369a1]/10 hover:text-[#0369a1] rounded-xl transition-all"
              title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? <Minimize2 size={18} className="sm:w-5 sm:h-5" /> : <Maximize2 size={18} className="sm:w-5 sm:h-5" />}
            </button>
            <button onClick={() => isEditing ? setIsEditing(false) : (editingPageNum !== null ? setEditingPageNum(null) : onClose())} className="p-1.5 sm:p-2.5 min-w-[32px] sm:min-w-[44px] min-h-[32px] sm:min-h-[44px] text-[#94a3b8] hover:bg-red-50 hover:text-red-500 rounded-xl transition-all"><X size={18} className="sm:w-5 sm:h-5" /></button>
          </div>
        </div>

        {/* Reading Canvas */}
        <div ref={mainScrollRef} dir="rtl" className={`flex-grow overflow-y-auto custom-scrollbar paper-background ${isEditing ? 'p-3 sm:p-4' : 'p-4 sm:p-6'} flex flex-col`}>
          {isEditing ? (
            <div className="h-full relative w-full max-w-4xl mx-auto">
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
              isFullscreen={isFullscreen}
            />
          ) : (
            <div className={`w-full max-w-4xl mx-auto ${isGuestOrReader ? 'pt-8' : 'space-y-16 pb-40'}`}>
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
      <div className={`w-full xl:w-[500px] 2xl:w-[600px] flex-col gap-4 xl:gap-6 ${isFullscreen ? 'hidden' : mobileTab === 'chat' ? 'flex flex-grow' : 'hidden xl:flex'}`}>
        <GlassPanel className={`h-full flex flex-col overflow-hidden ${mobileTab === 'chat' ? 'rounded-[24px] border' : 'rounded-none xl:rounded-[32px] border'} p-3 sm:p-4 xl:p-6 shadow-xl border-[#0369a1]/10`}>
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
        </GlassPanel>
      </div>
    </div>
  );
};
