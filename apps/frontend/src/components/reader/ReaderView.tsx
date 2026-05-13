import {
  ALargeSmall,
  BookOpen,
  Bot,
  Download,
  Edit3,
  Loader2,
  Maximize2, Minimize2,
  Save,
  X
} from 'lucide-react';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useAppContext } from '../../context/AppContext';
import { useAuth, useIsEditor } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { PersistenceService } from '../../services/persistenceService';
import { ChatInterface } from '../chat/ChatInterface';
import { GlassPanel } from '../ui/GlassPanel';
import { PageItem } from './PageItem';
import VirtualScrollReader from './VirtualScrollReader';

const normalizeReaderCategory = (category: string) =>
  category
    .normalize('NFKC')
    .replace(/[\u200B-\u200D\uFEFF]/g, '')
    .replace(/^['"\s]+|['"\s]+$/g, '');

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
  const usesArabicReaderFont = (selectedBook.categories || []).some(
    (category) => normalizeReaderCategory(category) === 'ئەرەبچە'
  );
  const readerContentFontFamily = usesArabicReaderFont ? '"Adobe Arabic", serif' : undefined;
  const readerContentFontClassName = usesArabicReaderFont ? 'reader-font-adobe' : undefined;

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
  const [loadedPages, setLoadedPages] = useState<any[]>(selectedBook.pages || []);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMorePages, setHasMorePages] = useState(true);
  const [isFetchingContent, setIsFetchingContent] = useState(false);
  const [mobileTab, setMobileTab] = useState<'reader' | 'chat'>('reader');
  const [showFontSlider, setShowFontSlider] = useState(false);
  const [sliderPos, setSliderPos] = useState({ top: 0, left: 0 });
  const fontButtonRef = useRef<HTMLButtonElement>(null);
  const fontSliderRef = useRef<HTMLDivElement>(null);

  const pageTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const globalTextAreaRef = useRef<HTMLTextAreaElement>(null);
  const observerTarget = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const mainScrollRef = useRef<HTMLDivElement>(null);
  const lastEditedPageRef = useRef<number | null>(null);

  useEffect(() => {
    if (!showFontSlider) return;
    const close = (e: MouseEvent | TouchEvent) => {
      if (
        fontSliderRef.current && !fontSliderRef.current.contains(e.target as Node) &&
        fontButtonRef.current && !fontButtonRef.current.contains(e.target as Node)
      ) {
        setShowFontSlider(false);
      }
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('touchstart', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('touchstart', close);
    };
  }, [showFontSlider]);

  const onClose = () => setView(previousView);

  // Prevent body-level scrollbar while reader is open (reader manages its own scroll).
  useEffect(() => {
    document.body.style.overflowY = 'hidden';
    return () => { document.body.style.overflowY = ''; };
  }, []);

  useEffect(() => {
    setFontSize(usesArabicReaderFont ? 24 : 18);
  }, [selectedBook.id, usesArabicReaderFont, setFontSize]);

  useEffect(() => {
    setMobileTab('reader');
    document.querySelector('main')?.scrollTo({ top: 0, behavior: 'instant' });
  }, [selectedBook.id]);

  useEffect(() => {
    document.querySelector('main')?.scrollTo({ top: 0, behavior: 'instant' });
  }, [mobileTab]);

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

  // When editing ends, scroll back to the page that was being edited.
  useEffect(() => {
    if (editingPageNum !== null) {
      lastEditedPageRef.current = editingPageNum;
    } else if (lastEditedPageRef.current !== null) {
      const target = lastEditedPageRef.current;
      lastEditedPageRef.current = null;
      setTimeout(() => {
        // Enforce root scroll lock first (iOS Safari / Chromium textarea focus push prevention)
        window.scrollTo(0, 0);
        document.body.scrollTop = 0;
        document.documentElement.scrollTop = 0;

        const el = pageRefs.current.get(target);
        const container = mainScrollRef.current;
        if (el && container) {
          // scrollIntoView dynamically forces the window to scroll as well if there 
          // are nested scrollbars or hidden overflow. This forcefully breaks the fixed/sticky 
          // navbar by displacing the document. Calculating exactly where to scroll manually 
          // completely isolates the scroll action boundaries.
          const containerTop = container.getBoundingClientRect().top;
          const elTop = el.getBoundingClientRect().top;
          
          container.scrollTo({
             top: container.scrollTop + (elTop - containerTop) - 24,
             behavior: 'instant'
          });
        }
      }, 50);
    }
  }, [editingPageNum]);

  // Track current page from scrolling (admin/editor path)
  useEffect(() => {
    if (isGuestOrReader || !mainScrollRef.current) return;

    const observer = new IntersectionObserver((entries) => {
      let mostVisiblePage = -1;
      let maxRatio = 0;
      entries.forEach(entry => {
        if (entry.isIntersecting && entry.intersectionRatio > maxRatio) {
          const pageNum = parseInt(entry.target.getAttribute('data-page-number') || '0');
          if (pageNum > 0) { maxRatio = entry.intersectionRatio; mostVisiblePage = pageNum; }
        }
      });
      if (mostVisiblePage !== -1) setCurrentPage(mostVisiblePage);
    }, { root: mainScrollRef.current, rootMargin: '-45% 0px -45% 0px', threshold: [0, 0.5, 1] });

    pageRefs.current.forEach(el => { if (el) observer.observe(el); });
    return () => observer.disconnect();
  }, [loadedPages.length, isGuestOrReader]);

  // Sync scroll position when switching tabs (not on every currentPage change)
  const currentPageRef = useRef(currentPage);
  currentPageRef.current = currentPage;

  useEffect(() => {
    const page = currentPageRef.current;
    if (page !== null && !isEditing && editingPageNum === null) {
      const el = pageRefs.current.get(page);
      const container = mainScrollRef.current;
      if (el && container) {
        const timer = setTimeout(() => {
          const containerTop = container.getBoundingClientRect().top;
          const elTop = el.getBoundingClientRect().top;
          container.scrollTo({ top: container.scrollTop + (elTop - containerTop) - 24, behavior: 'instant' });
        }, 50);
        return () => clearTimeout(timer);
      }
    }
  }, [mobileTab, isEditing, editingPageNum]);

  useEffect(() => {
    if (pageTextAreaRef.current) {
      pageTextAreaRef.current.style.height = 'auto';
      pageTextAreaRef.current.style.height = `${pageTextAreaRef.current.scrollHeight}px`;
    }
  }, [tempPageText, editingPageNum]);

  useEffect(() => {
    if (!showFontSlider) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (
        fontButtonRef.current && !fontButtonRef.current.contains(e.target as Node) &&
        fontSliderRef.current && !fontSliderRef.current.contains(e.target as Node)
      ) {
        setShowFontSlider(false);
      }
    };
    const updatePos = () => {
      if (fontButtonRef.current) {
        const r = fontButtonRef.current.getBoundingClientRect();
        setSliderPos({ top: r.bottom + 8, left: r.left });
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    window.addEventListener('resize', updatePos);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('resize', updatePos);
    };
  }, [showFontSlider]);

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
      { threshold: 0.1, rootMargin: '1200px' }
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
              if (existing.text !== p.text ||
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
      : `h-[calc(100dvh-72px)] sm:h-[calc(100dvh-88px)] md:h-[calc(100dvh-120px)] xl:h-[calc(100dvh-96px)] flex flex-col xl:flex-row-reverse ${mobileTab === 'chat' ? 'gap-3' : 'gap-4'} xl:gap-6 py-0 md:py-4 notranslate`
    } lang="ug" translate="no">

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
                style={{ fontSize: '18px' }}
              >
                {selectedBook.title}
                {selectedBook.volume ? ` (${t('book.volume', { volume: selectedBook.volume })})` : ''}
              </h2>
              {selectedBook.author && (
                <p
                  className="text-[#64748b] mt-0.5 truncate hidden sm:block"
                  style={{ fontSize: '14px' }}
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
                    {selectedBook.fileType === 'pdf' && (
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
                    )}
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

            <div className="relative flex items-center">
              <button
                ref={fontButtonRef}
                onClick={() => {
                  if (!showFontSlider && fontButtonRef.current) {
                    const r = fontButtonRef.current.getBoundingClientRect();
                    setSliderPos({ top: r.bottom + 8, left: r.left });
                  }
                  setShowFontSlider(prev => !prev);
                }}
                className={`p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all focus:outline-none ${showFontSlider ? 'bg-[#0369a1] text-white shadow-md' : 'bg-white/60 border border-[#0369a1]/20 text-[#0369a1] hover:bg-[#0369a1]/10'}`}
              >
                <ALargeSmall size={21} className="sm:w-[23px] sm:h-[23px] -translate-x-[1px]" />
              </button>
              {showFontSlider && createPortal(
                <div
                  ref={fontSliderRef}
                  className="fixed flex flex-col items-center gap-2 bg-white/95 backdrop-blur-xl border border-[#0369a1]/20 rounded-2xl shadow-2xl px-3 py-4 z-[9999]"
                  style={{ top: sliderPos.top, left: sliderPos.left }}
                >
                  <button onClick={() => setFontSize(f => Math.max(14, f - 2))} className="text-[11px] font-bold text-[#94a3b8] select-none px-2 py-1 rounded-lg hover:bg-[#0369a1]/10 active:scale-90 transition-all">A-</button>
                  <div style={{ height: '120px', width: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'visible' }}>
                    <input
                      type="range"
                      min={14}
                      max={64}
                      step={2}
                      value={fontSize}
                      onChange={(e) => setFontSize(Number(e.target.value))}
                      style={{ width: '120px', transform: 'rotate(-90deg)', cursor: 'pointer', accentColor: '#0369a1', flexShrink: 0 }}
                    />
                  </div>
                  <button onClick={() => setFontSize(f => Math.min(64, f + 2))} className="text-[11px] font-bold text-[#0369a1] select-none px-2 py-1 rounded-lg hover:bg-[#0369a1]/10 active:scale-90 transition-all">A+</button>
                  <span className="text-[11px] font-mono font-bold text-[#0369a1] select-none">{fontSize}</span>
                </div>,
                document.body
              )}
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
              <textarea value={editContent} onChange={(e) => setEditContent(e.target.value)} className={`w-full h-full p-6 uyghur-text border-2 border-[#0369a1]/10 rounded-3xl outline-none resize-none bg-white shadow-inner ${readerContentFontClassName || ''}`} style={{ fontSize: `${fontSize}px`, fontFamily: readerContentFontFamily }} placeholder={t('common.enterContent')} />
            </div>
          ) : isGuestOrReader ? (
            <VirtualScrollReader
              bookId={selectedBook.id}
              totalPages={selectedBook.totalPages || (selectedBook as any).total_pages || 0}
              fontSize={fontSize}
              contentFontFamily={readerContentFontFamily}
              contentFontClassName={readerContentFontClassName}
              initialPage={currentPage || 1}
              onPageChange={setCurrentPage}
              scrollParentRef={mainScrollRef}
              isFullscreen={isFullscreen}
            />
          ) : (
            <div className={`w-full max-w-4xl mx-auto ${editingPageNum !== null ? 'h-full flex flex-col' : isGuestOrReader ? 'pt-8' : 'space-y-4 pb-40'}`}>
              {[...loadedPages]
                .sort((a, b) => a.pageNumber - b.pageNumber)
                .filter(page => isGuestOrReader ? Number(page.pageNumber) === Number(currentPage) : (editingPageNum === null || Number(page.pageNumber) === Number(editingPageNum)))
                .map(page => (
                  <div
                    key={page.pageNumber}
                    ref={el => { if (el) pageRefs.current.set(page.pageNumber, el); else pageRefs.current.delete(page.pageNumber); }}
                    data-page-number={page.pageNumber}
                    className={editingPageNum === page.pageNumber ? 'h-full flex flex-col' : ''}
                  >
                    <PageItem
                      key={page.pageNumber}
                      page={page}
                      isActive={currentPage === page.pageNumber}
                      isEditing={editingPageNum === page.pageNumber}
                      fontSize={fontSize}
                      contentFontFamily={readerContentFontFamily}
                      contentFontClassName={readerContentFontClassName}
                      onSetActive={() => !isGuestOrReader && setCurrentPage(page.pageNumber)}
                      onEdit={() => { setEditingPageNum(page.pageNumber); setTempPageText(page.text || ''); }}
                      onReprocess={() => bookActions.handleReProcessPage(selectedBook.id, page.pageNumber)}
                      tempText={tempPageText}
                      onTempTextChange={setTempPageText}
                      onSave={() => {
                        handleUpdatePage(selectedBook.id, page.pageNumber, tempPageText);
                        window.scrollTo(0, 0);
                      }}
                      onCancel={() => {
                        setEditingPageNum(null);
                        window.scrollTo(0, 0);
                      }}
                      isLoading={!page.text && ((!page.pipelineStep && (page.status === 'ocr_processing' || page.status === 'indexing' || page.status === 'pending')) || (page.pipelineStep === 'ocr' && page.milestone !== 'succeeded'))}
                      isSaving={isSaving}
                      isFullscreen={isFullscreen}
                    />
                  </div>
                ))}
              {!isEditing && !isGuestOrReader && hasMorePages && <div ref={observerTarget} className="h-20 flex items-center justify-center">{isLoadingMore && <Loader2 className="animate-spin text-[#0369a1]" />}</div>}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar Area */}
      <div className={`w-full xl:w-[500px] 2xl:w-[600px] flex-col gap-4 xl:gap-6 min-h-0 ${isFullscreen ? 'hidden' : mobileTab === 'chat' ? 'flex flex-grow' : 'hidden xl:flex'}`}>
        <GlassPanel className={`flex-1 min-h-0 flex flex-col ${mobileTab === 'chat' ? 'rounded-[24px] border' : 'rounded-none xl:rounded-[32px] border'} shadow-xl border-[#0369a1]/10 overflow-hidden`}>
          {/* Chat tab header — mobile only, mirrors reader header without edit button */}
          {mobileTab === 'chat' && (
            <div className="xl:hidden flex-shrink-0 px-3 sm:px-6 py-2 sm:py-4 border-b border-[#0369a1]/10 flex flex-row items-center justify-between gap-1 sm:gap-4 bg-white/80 backdrop-blur-sm mb-0">
              {/* Book title — left in RTL */}
              <div className="flex items-center gap-2 sm:gap-4 min-w-0 flex-shrink">
                <div className="hidden sm:flex p-2 bg-[#0369a1] text-white rounded-xl shadow-lg shrink-0">
                  <BookOpen size={20} />
                </div>
                <div className="min-w-0 flex flex-col justify-center">
                  <h2 className="font-bold text-[#1a1a1a] truncate" style={{ fontSize: '18px' }}>
                    {selectedBook.title}
                    {selectedBook.volume ? ` (${t('book.volume', { volume: selectedBook.volume })})` : ''}
                  </h2>
                  {selectedBook.author && (
                    <p className="text-[#64748b] mt-0.5 truncate hidden sm:block" style={{ fontSize: '14px' }}>
                      {selectedBook.author}
                    </p>
                  )}
                </div>
              </div>
              {/* Controls — right in RTL */}
              <div className="flex items-center gap-0.5 sm:gap-2 shrink-0">
                {isEditor && selectedBook.fileType === 'pdf' && (
                  <button
                    onClick={handleDownload}
                    disabled={isDownloading}
                    className="flex items-center gap-2 px-2 sm:px-4 py-2 min-h-[36px] sm:min-h-[44px] bg-white border border-[#0369a1]/20 text-[#0369a1] text-xs sm:text-sm rounded-xl sm:rounded-2xl hover:bg-[#0369a1]/10 transition-all font-bold disabled:opacity-50"
                  >
                    {isDownloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                    <span className="hidden sm:inline">{t('common.download')}</span>
                  </button>
                )}
                <button
                  ref={fontButtonRef}
                  onClick={() => {
                    if (!showFontSlider && fontButtonRef.current) {
                      const r = fontButtonRef.current.getBoundingClientRect();
                      setSliderPos({ top: r.bottom + 8, left: r.left });
                    }
                    setShowFontSlider(prev => !prev);
                  }}
                  className={`p-1.5 sm:p-2 min-w-[32px] sm:min-w-[40px] min-h-[32px] sm:min-h-[40px] rounded-xl transition-all focus:outline-none ${showFontSlider ? 'bg-[#0369a1] text-white shadow-md' : 'bg-white/60 border border-[#0369a1]/20 text-[#0369a1] hover:bg-[#0369a1]/10'}`}
                >
                  <ALargeSmall size={21} className="sm:w-[23px] sm:h-[23px] -translate-x-[1px]" />
                </button>
                <button onClick={onClose} className="p-1.5 sm:p-2.5 min-w-[32px] sm:min-w-[44px] min-h-[32px] sm:min-h-[44px] text-[#94a3b8] hover:bg-red-50 hover:text-red-500 rounded-xl transition-all">
                  <X size={18} className="sm:w-5 sm:h-5" />
                </button>
              </div>
            </div>
          )}
          {/* Panel content */}
          <div className="flex-1 min-h-0 p-3 sm:p-4 xl:p-6 overflow-hidden flex flex-col">
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
          </div>
        </GlassPanel>
      </div>

      {/* Floating reader/chat toggle — mobile only */}
      {!isFullscreen && createPortal(
        <button
          className="xl:hidden fixed bottom-[112px] left-6 z-50 transition-all active:scale-90 hover:opacity-70 text-[#FF9800] animate-[bob_10s_ease-in-out_infinite]"
          onClick={() => setMobileTab(prev => prev === 'reader' ? 'chat' : 'reader')}
        >
          {mobileTab === 'reader' ? <Bot size={38} strokeWidth={2} /> : <BookOpen size={38} strokeWidth={2} />}
        </button>,
        document.body
      )}
    </div>
  );
};
