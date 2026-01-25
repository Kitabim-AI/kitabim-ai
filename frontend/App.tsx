
import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Library, LayoutDashboard, Search, BookOpen, Send,
  Save, Edit3, Upload, FileText,
  Loader2, CheckCircle2, X, MessageSquare,
  Globe, Database, Zap, Trash2, AlertCircle, RotateCcw,
  ChevronUp, ChevronDown, ChevronLeft, ChevronRight,
  Minus, Plus, Type
} from 'lucide-react';
import { chatWithBook } from './services/geminiService';
import { PersistenceService } from './services/persistenceService';
import { Book, ExtractionResult, Message } from './types';

const sleep = (ms: number) => new Promise(res => setTimeout(res, ms));
const SHELF_PAGE_SIZE = 12;

const App: React.FC = () => {
  const [view, setView] = useState<'library' | 'admin' | 'reader' | 'global-chat'>('library');
  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatting, setIsChatting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [currentPage, setCurrentPage] = useState<number | null>(null);
  const [editingPageNum, setEditingPageNum] = useState<number | null>(null);
  const [tempPageText, setTempPageText] = useState('');
  const [isCheckingGlobal, setIsCheckingGlobal] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [totalBooks, setTotalBooks] = useState(0);
  const [fontSize, setFontSize] = useState(24); // Default font size in px
  const [sortConfig, setSortConfig] = useState<{ key: 'title' | 'lastUpdated' | 'status' | 'uploadDate'; direction: 'asc' | 'desc' }>(() => {
    const saved = sessionStorage.getItem('kitabim_sort_config');
    return saved ? JSON.parse(saved) : { key: 'lastUpdated', direction: 'desc' };
  });

  // Shelf (Global Library) Pagination
  const [shelfPage, setShelfPage] = useState(1);
  const [hasMoreShelf, setHasMoreShelf] = useState(true);
  const [isLoadingMoreShelf, setIsLoadingMoreShelf] = useState(false);
  const loaderRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionStorage.setItem('kitabim_sort_config', JSON.stringify(sortConfig));
  }, [sortConfig]);
  const [modal, setModal] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    type: 'alert' | 'confirm';
    onConfirm?: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    type: 'alert',
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const refreshLibrary = useCallback(async () => {
    try {
      const isShelf = view === 'library';
      const currentViewSize = isShelf ? SHELF_PAGE_SIZE : pageSize;
      const currentViewPage = isShelf ? 1 : page;

      const sortBy = isShelf ? 'title' : sortConfig.key;
      const order = isShelf ? 1 : (sortConfig.direction === 'asc' ? 1 : -1);

      const response = await PersistenceService.getGlobalLibrary(currentViewPage, currentViewSize, searchQuery, sortBy, order);
      setBooks(response.books);
      setTotalBooks(response.total);

      // Also reset shelf when search changes or filter changes
      if (isShelf) {
        setShelfPage(1);
        setHasMoreShelf(response.books.length < response.total);
      }
    } catch (err) {
      console.error("Manual refresh failed", err);
    }
  }, [view, page, pageSize, searchQuery, sortConfig]);

  const loadMoreShelf = useCallback(async () => {
    if (isLoadingMoreShelf || !hasMoreShelf || view !== 'library') return;

    setIsLoadingMoreShelf(true);
    const nextPage = shelfPage + 1;
    try {
      // Shelf is ALWAYS sorted by title ASC on server
      const response = await PersistenceService.getGlobalLibrary(nextPage, SHELF_PAGE_SIZE, searchQuery, 'title', 1);
      if (response.books.length > 0) {
        setBooks(prev => {
          // Avoid duplicates
          const existingIds = prev.map(b => b.id);
          const newBooks = response.books.filter(b => !existingIds.includes(b.id));
          const updated = [...prev, ...newBooks];

          // Update hasMore based on the newly formed list
          setHasMoreShelf(updated.length < response.total);
          return updated;
        });
        setShelfPage(nextPage);
      } else {
        setHasMoreShelf(false);
      }
    } catch (err) {
      console.error("Failed to load more shelf items", err);
    } finally {
      setIsLoadingMoreShelf(false);
    }
  }, [shelfPage, hasMoreShelf, isLoadingMoreShelf, view, searchQuery]);

  // Intersection Observer for Shelf
  useEffect(() => {
    if (view !== 'library') return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMoreShelf && !isLoadingMoreShelf) {
          loadMoreShelf();
        }
      },
      { threshold: 0.1 }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [view, hasMoreShelf, isLoadingMoreShelf, loadMoreShelf]);

  // Reset page to 1 when search query changes
  useEffect(() => {
    setPage(1);
  }, [searchQuery]);

  // Sync selectedBook with fresh data from the books list
  useEffect(() => {
    if (selectedBook) {
      const updated = books.find(b => b.id === selectedBook.id);
      // Only update if the object actually changed or status changed
      if (updated && (updated.status !== selectedBook.status || updated.lastUpdated !== selectedBook.lastUpdated)) {
        setSelectedBook(prev => {
          if (!prev) return updated;
          // Preserve heavy data (content & results with text) from the current selectedBook
          // 'updated' comes from the list API which excludes text content
          return {
            ...updated,
            content: prev.content || updated.content,
            results: (prev.results && prev.results.some(r => r.text)) ? prev.results : updated.results
          };
        });
      }
    }
  }, [books, selectedBook]);

  useEffect(() => {
    refreshLibrary();
  }, [refreshLibrary]);

  // Poll for updates if books are processing (Strict 10s)
  useEffect(() => {
    const hasProcessing = books.some(b => b.status === 'processing');
    if (hasProcessing) {
      const interval = setInterval(refreshLibrary, 10000);
      return () => clearInterval(interval);
    }
  }, [books, refreshLibrary]);

  // Sort Logic for view consistency
  const sortedBooks = useMemo(() => {
    // If we're on the library shelf, ALWAYS sort by title ASC locally for extra safety
    if (view === 'library') {
      return [...books].sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    }

    // For other views (Admin), use the sortConfig
    return [...books].sort((a, b) => {
      const aVal = a[sortConfig.key] || '';
      const bVal = b[sortConfig.key] || '';
      if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
      if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }, [books, sortConfig, view]);

  const toggleSort = (key: 'title' | 'lastUpdated' | 'status' | 'uploadDate') => {
    setSortConfig(prev => ({
      key,
      direction: prev.key === key && prev.direction === 'desc' ? 'asc' : 'desc'
    }));
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || file.type !== 'application/pdf') return;

    setIsCheckingGlobal(true);
    setView('admin');

    try {
      // 1. Upload to server for background processing
      await PersistenceService.uploadPdf(file);

      // 2. Refresh library to see the new record
      await refreshLibrary();
      setIsCheckingGlobal(false);

    } catch (err) {
      setIsCheckingGlobal(false);
      const errorMsg = err instanceof Error ? err.message : "An unknown error occurred.";
      setModal({
        isOpen: true,
        title: "Upload Error",
        message: `Error uploading document: ${errorMsg}`,
        type: 'alert'
      });
    }
  };

  const handleReprocess = async (bookId: string) => {
    try {
      // Optimistic update
      setBooks(prev => prev.map(b => b.id === bookId ? { ...b, status: 'processing', processingStep: 'ocr' } : b));
      await PersistenceService.reprocessBook(bookId);
      refreshLibrary();
    } catch (err) {
      setModal({
        isOpen: true,
        title: "Process Error",
        message: "Failed to start reprocessing. Please try again.",
        type: 'alert'
      });
    }
  };

  const handleReProcessPage = async (bookId: string, pageNum: number) => {
    try {
      await fetch(`/api/books/${bookId}/pages/${pageNum}/reset`, { method: 'POST' });
      refreshLibrary();
    } catch (err) {
      console.error("Failed to reset page", err);
    }
  };

  const handleUpdatePage = async (bookId: string, pageNum: number, newText: string) => {
    try {
      await fetch(`/api/books/${bookId}/pages/${pageNum}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newText })
      });
      setEditingPageNum(null);
      refreshLibrary();
    } catch (err) {
      console.error("Failed to update page", err);
    }
  };

  const openReader = async (book: Book) => {
    try {
      // Show loader or something? For now just fetch
      const fullBook = await PersistenceService.getBookById(book.id);
      if (!fullBook) throw new Error("Could not load book content");

      setSelectedBook(fullBook);
      setEditContent(fullBook.content);
      setChatMessages([]);
      setView('reader');
      setCurrentPage(1);
    } catch (err) {
      setModal({
        isOpen: true,
        title: "Load Error",
        message: "Failed to load book content. Please try again.",
        type: 'alert'
      });
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    if (view !== 'global-chat' && !selectedBook) return;

    const userMsg: Message = { role: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsChatting(true);

    try {
      const bookId = (view === 'global-chat') ? 'global' : selectedBook!.id;
      const aiResponse = await chatWithBook(chatInput, bookId, view === 'reader' ? (currentPage || undefined) : undefined);
      setChatMessages(prev => [...prev, { role: 'model', text: aiResponse }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم." }]);
    } finally {
      setIsChatting(false);
    }
  };

  const saveCorrections = async () => {
    if (!selectedBook) return;
    try {
      // 1. SMART SPLIT: Distribute edited content back into pages to keep the Reader UI in sync
      const lines = editContent.split('\n');
      const linesPerPage = Math.max(1, Math.ceil(lines.length / (selectedBook.results.length || 1)));

      const updatedResults = selectedBook.results.map((res, i) => {
        const start = i * linesPerPage;
        const end = start + linesPerPage;
        const pageLines = lines.slice(start, end);
        return {
          ...res,
          text: pageLines.join('\n').trim(),
          status: 'completed' as const
        };
      });

      // 2. Clear old embeddings from the results we send to force RAG update
      const cleanResults = updatedResults.map(({ embedding, ...rest }) => rest);

      const updatedBook = {
        ...selectedBook,
        content: editContent,
        results: cleanResults as any,
        lastUpdated: new Date()
      };

      await PersistenceService.saveBookGlobally(updatedBook);
      await refreshLibrary();
      setIsEditing(false);
    } catch (err) {
      console.error("Failed to save global corrections", err);
      setModal({
        isOpen: true,
        title: "Save Error",
        message: "Failed to save global changes. Please try again.",
        type: 'alert'
      });
    }
  };

  const cancelledBooks = useRef<Set<string>>(new Set());

  const handleDeleteBook = (bookId: string) => {
    setModal({
      isOpen: true,
      title: "Confirm Deletion",
      message: "Are you sure you want to delete this book? This will permanently remove it from the global library platform.",
      type: 'confirm',
      onConfirm: async () => {
        cancelledBooks.current.add(bookId);
        await PersistenceService.deleteBook(bookId);
        setBooks(prev => prev.filter(b => b.id !== bookId));
        if (selectedBook?.id === bookId) {
          setSelectedBook(null);
          setView('library');
        }
        setModal(prev => ({ ...prev, isOpen: false }));
      }
    });
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <nav className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => setView('library')}>
            <div className="bg-indigo-600 p-1.5 rounded-lg shadow-sm shadow-indigo-100">
              <BookOpen className="text-white w-5 h-5" />
            </div>
            <span className="font-bold text-slate-900 tracking-tight text-xl">Kitabim<span className="text-indigo-600">.AI</span></span>
          </div>
          <div className="hidden md:flex items-center gap-1">
            <button
              onClick={() => setView('library')}
              className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'library' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
            >
              <Globe size={18} /> Global Library
            </button>
            <button
              onClick={() => { setView('global-chat'); setChatMessages([]); }}
              className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'global-chat' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
            >
              <MessageSquare size={18} /> Global Assistant
            </button>
            <button
              onClick={() => setView('admin')}
              className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'admin' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
            >
              <LayoutDashboard size={18} /> Management
            </button>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="relative hidden sm:block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 pr-4 py-1.5 bg-slate-100 border-none rounded-full text-sm focus:ring-2 focus:ring-indigo-500 transition-all w-64"
            />
          </div>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="bg-indigo-600 text-white px-4 py-1.5 rounded-lg text-sm font-semibold shadow-md shadow-indigo-100 flex items-center gap-2 hover:bg-indigo-700 active:scale-95 transition-transform"
          >
            <Upload size={16} /> Process PDF
          </button>
          <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept="application/pdf" className="hidden" />
        </div>
      </nav>

      <main className="flex-grow p-6 max-w-7xl mx-auto w-full">
        {view === 'library' && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <header>
                <h2 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                  <Database className="text-indigo-600 w-6 h-6" />
                  Global Knowledge Base
                </h2>
                <p className="text-slate-500">Shared collection of pre-processed Uyghur literature on Kitabim.AI</p>
              </header>
              <div className="flex items-center gap-2 text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">
                <Zap size={14} className="text-amber-500" />
                DEDUPLICATION ACTIVE
              </div>
            </div>

            <div className="book-shelf-row">
              {sortedBooks.map(book => (
                <div
                  key={book.id}
                  onClick={() => openReader(book)}
                  className="flex flex-col gap-3 cursor-pointer group"
                >
                  <div className="book-cover aspect-[3/4] bg-slate-100 relative shadow-lg">
                    {book.coverUrl ? (
                      <img
                        src={book.coverUrl}
                        alt={book.title}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full flex flex-col items-center justify-center bg-indigo-50 border-l-[6px] border-indigo-200 p-4 text-center">
                        <FileText className={`w-8 h-8 mb-2 ${book.status === 'ready' ? 'text-slate-300' : 'text-indigo-300'}`} />
                        <span className="text-[10px] font-bold text-indigo-300 break-words leading-tight uppercase opacity-50">{book.title.substring(0, 20)}</span>
                      </div>
                    )}
                    <div className="book-spine-line" />

                    {/* Hover Controls */}
                    <div className="absolute top-2 left-2 opacity-0 group-hover:opacity-100 transition-all transform -translate-x-2 group-hover:translate-x-0 z-20">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteBook(book.id);
                        }}
                        className="p-1.5 bg-white/90 hover:bg-red-500 hover:text-white text-slate-500 rounded-lg shadow-xl backdrop-blur-md transition-all"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>

                    <div className="absolute top-2 right-2 flex flex-col gap-1.5 z-20">
                      {book.status !== 'ready' ? (
                        <div className="p-1.5 bg-white/90 rounded-full shadow-lg backdrop-blur-sm">
                          <Loader2 size={12} className="text-indigo-600 animate-spin" />
                        </div>
                      ) : (
                        <div className="p-1.5 bg-green-500/90 text-white rounded-full shadow-lg backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-all scale-75 group-hover:scale-100">
                          <CheckCircle2 size={12} />
                        </div>
                      )}
                    </div>

                    {/* Quick Info Overlay on Hover */}
                    <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2 pointer-events-none">
                      <span className="text-[9px] text-white font-black uppercase tracking-tighter bg-indigo-600/80 px-1.5 py-0.5 rounded">
                        {book.status === 'ready' ? 'OPEN READER' : 'PROCESSING'}
                      </span>
                    </div>
                  </div>

                  <div className="px-1 mt-1">
                    <h3 className="font-bold text-slate-900 text-sm leading-tight line-clamp-2 text-right transition-colors group-hover:text-indigo-600" dir="rtl">
                      {book.title}
                    </h3>
                    <div className="flex items-center justify-end gap-1.5 mt-1 opacity-70">
                      <span className="text-xs font-bold text-slate-500">{book.totalPages} Pages</span>
                      <div className="w-1 h-1 rounded-full bg-slate-300" />
                      <span className="text-xs font-bold text-indigo-600">READY</span>
                    </div>
                  </div>
                </div>
              ))}
              {sortedBooks.length === 0 && !isLoadingMoreShelf && (
                <div className="col-span-full py-20 text-center border-2 border-dashed border-slate-200 rounded-3xl">
                  <Library className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-500 font-medium">{searchQuery ? 'No books match your search.' : 'No books indexed in the global database yet.'}</p>
                </div>
              )}
            </div>

            {/* Infinite Scroll Trigger */}
            <div ref={loaderRef} className="h-32 flex items-center justify-center">
              {isLoadingMoreShelf && (
                <div className="flex flex-col items-center gap-3 animate-in fade-in slide-in-from-bottom-2">
                  <div className="relative">
                    <div className="w-10 h-10 border-4 border-indigo-100 border-t-indigo-600 rounded-full animate-spin"></div>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Zap size={14} className="text-amber-500 animate-pulse" />
                    </div>
                  </div>
                  <span className="text-xs font-bold text-indigo-600 uppercase tracking-widest">Loading more treasures...</span>
                </div>
              )}
              {!hasMoreShelf && sortedBooks.length > 0 && (
                <div className="flex flex-col items-center gap-2 opacity-40">
                  <Library size={24} className="text-slate-400" />
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">End of the collection</p>
                </div>
              )}
            </div>
          </div>
        )}

        {view === 'admin' && (
          <div className="space-y-6">
            <header>
              <h2 className="text-2xl font-bold text-slate-800">Kitabim Processing Pipeline</h2>
              <p className="text-slate-500">Managing global document indexing and OCR extraction.</p>
            </header>

            {isCheckingGlobal && (
              <div className="bg-indigo-50 border border-indigo-100 p-8 rounded-2xl flex flex-col items-center justify-center text-center animate-pulse">
                <Database className="w-12 h-12 text-indigo-400 mb-4 animate-bounce" />
                <h3 className="font-bold text-indigo-900">Uploadding to Server...</h3>
                <p className="text-indigo-600 text-sm">Transferring document for background processing.</p>
              </div>
            )}

            {!isCheckingGlobal && (
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-500 uppercase tracking-wider">
                      <th className="px-6 py-4 cursor-pointer hover:bg-slate-100 transition-colors group" onClick={() => toggleSort('title')}>
                        <div className="flex items-center gap-2">
                          Document
                          <div className={`transition-opacity ${sortConfig.key === 'title' ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                            {sortConfig.key === 'title' && sortConfig.direction === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </div>
                        </div>
                      </th>
                      <th className="px-6 py-4 cursor-pointer hover:bg-slate-100 transition-colors group" onClick={() => toggleSort('lastUpdated')}>
                        <div className="flex items-center gap-2">
                          Last Updated
                          <div className={`transition-opacity ${sortConfig.key === 'lastUpdated' ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                            {sortConfig.key === 'lastUpdated' && sortConfig.direction === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </div>
                        </div>
                      </th>
                      <th className="px-6 py-4 cursor-pointer hover:bg-slate-100 transition-colors group" onClick={() => toggleSort('status')}>
                        <div className="flex items-center gap-2">
                          Status
                          <div className={`transition-opacity ${sortConfig.key === 'status' ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                            {sortConfig.key === 'status' && sortConfig.direction === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                          </div>
                        </div>
                      </th>
                      <th className="px-6 py-4">Pipeline Progress</th>
                      <th className="px-6 py-4">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {sortedBooks.map(book => (
                      <tr key={book.id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div className="bg-indigo-50 p-2 rounded-lg text-indigo-600">
                              <Database size={18} />
                            </div>
                            <div>
                              <div className="font-bold text-slate-900 text-sm truncate max-w-[200px]">{book.title}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm font-medium text-slate-700">
                            {new Date(book.lastUpdated || book.uploadDate).toLocaleDateString()}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            {new Date(book.lastUpdated || book.uploadDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase ${book.status === 'ready' ? 'bg-green-100 text-green-700' :
                            book.status === 'processing' ? 'bg-blue-100 text-blue-700' : 'bg-red-100 text-red-700'
                            }`}>
                            {book.status}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-col gap-1.5">
                            <div className="flex items-center gap-2">
                              <div className="w-full max-w-[150px] bg-slate-100 h-1.5 rounded-full overflow-hidden">
                                <div
                                  className={`h-full transition-all duration-500 ${book.processingStep === 'rag' ? 'bg-amber-500 animate-pulse' : 'bg-indigo-600'}`}
                                  style={{ width: `${(book.results.filter(r => r.status === 'completed').length / (book.totalPages || 1)) * 100}%` }}
                                />
                              </div>
                              <span className="text-[10px] font-bold text-slate-400">
                                {book.results.filter(r => r.status === 'completed').length}/{book.totalPages || 0}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5">
                              {book.status === 'processing' && (
                                <>
                                  <div className={`w-1.5 h-1.5 rounded-full animate-ping ${book.processingStep === 'rag' ? 'bg-amber-400' : 'bg-indigo-400'}`} />
                                  <span className="text-[9px] font-bold text-slate-500 uppercase tracking-tighter">
                                    {book.processingStep === 'rag' ? 'Indexing RAG Content...' : 'Extracting Book Text...'}
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-4">
                            <button onClick={() => openReader(book)} className="text-indigo-600 font-bold text-sm hover:underline">
                              Open Reader
                            </button>
                            {book.status !== 'processing' && (
                              <button
                                onClick={() => handleReprocess(book.id)}
                                className="text-amber-600 hover:text-amber-700 transition-colors p-1 rounded-md hover:bg-amber-50 flex items-center gap-1"
                                title="Reprocess Failed Pages"
                              >
                                <RotateCcw size={16} />
                                <span className="text-xs font-bold font-mono">FIX</span>
                              </button>
                            )}
                            <button
                              onClick={() => handleDeleteBook(book.id)}
                              className="text-red-500 hover:text-red-700 transition-colors p-1 rounded-md hover:bg-red-50"
                              title="Delete Book"
                            >
                              <Trash2 size={16} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Pagination Controls */}
                <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-500">Show</span>
                    <select
                      value={pageSize}
                      onChange={(e) => {
                        setPageSize(Number(e.target.value));
                        setPage(1);
                      }}
                      className="bg-white border border-slate-200 rounded px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-indigo-500 font-medium text-slate-700"
                    >
                      <option value={5}>5</option>
                      <option value={10}>10</option>
                      <option value={20}>20</option>
                      <option value={50}>50</option>
                    </select>
                    <span className="text-sm text-slate-500">per page</span>
                  </div>

                  <div className="flex items-center gap-6">
                    <span className="text-sm text-slate-500 font-medium">
                      Showing <span className="text-slate-900">{((page - 1) * pageSize) + 1}</span> to <span className="text-slate-900">{Math.min(page * pageSize, totalBooks)}</span> of <span className="text-slate-900">{totalBooks}</span>
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        disabled={page === 1}
                        onClick={() => setPage(p => p - 1)}
                        className="p-1.5 rounded-lg hover:bg-slate-200 disabled:opacity-30 transition-colors text-slate-600"
                        title="Previous Page"
                      >
                        <ChevronLeft size={20} />
                      </button>

                      <div className="flex items-center gap-1">
                        {Array.from({ length: Math.ceil(totalBooks / pageSize) }, (_, i) => i + 1)
                          .filter(p => p === 1 || p === Math.ceil(totalBooks / pageSize) || Math.abs(p - page) <= 1)
                          .map((p, i, arr) => (
                            <React.Fragment key={p}>
                              {i > 0 && arr[i - 1] !== p - 1 && <span className="px-1 text-slate-400">...</span>}
                              <button
                                onClick={() => setPage(p)}
                                className={`min-w-[32px] h-8 rounded-lg text-sm font-bold transition-all ${page === p ? 'bg-indigo-600 text-white shadow-md shadow-indigo-100' : 'text-slate-600 hover:bg-slate-100'}`}
                              >
                                {p}
                              </button>
                            </React.Fragment>
                          ))}
                      </div>

                      <button
                        disabled={page * pageSize >= totalBooks}
                        onClick={() => setPage(p => p + 1)}
                        className="p-1.5 rounded-lg hover:bg-slate-200 disabled:opacity-30 transition-colors text-slate-600"
                        title="Next Page"
                      >
                        <ChevronRight size={20} />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {view === 'reader' && selectedBook && (
          <div className="h-[calc(100vh-140px)] flex gap-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <div className="flex-grow bg-white border border-slate-200 rounded-2xl shadow-sm flex flex-col overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                <div>
                  <h2 className="font-bold text-slate-900">{selectedBook.title}</h2>
                </div>
                <div className="flex items-center gap-2">
                  {selectedBook.status !== 'processing' && (
                    <button
                      onClick={() => handleReprocess(selectedBook.id)}
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
                    <button onClick={saveCorrections} className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-100">
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

                  <button onClick={() => setView('library')} className="p-2 text-slate-400 hover:bg-slate-200 rounded-lg transition-colors">
                    <X size={20} />
                  </button>
                </div>
              </div>

              <div className="flex-grow p-10 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/paper-fibers.png')]">
                {isEditing ? (
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    className="w-full h-full p-6 uyghur-text text-2xl border border-indigo-200 rounded-xl focus:ring-4 focus:ring-indigo-500/10 outline-none resize-none bg-white shadow-inner"
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
                            onClick={() => handleReProcessPage(selectedBook.id, page.pageNumber)}
                            className="p-1 px-2 bg-indigo-50 text-indigo-600 rounded text-[9px] font-bold hover:bg-indigo-600 hover:text-white transition-all opacity-0 group-hover:opacity-100 flex items-center gap-1 shadow-sm"
                          >
                            <RotateCcw size={10} /> RE-OCR PAGE
                          </button>
                          <button
                            onClick={() => { setEditingPageNum(page.pageNumber); setTempPageText(page.text); }}
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
                              className="w-full h-64 p-4 uyghur-text text-2xl border border-indigo-200 rounded-xl focus:ring-4 focus:ring-indigo-500/10 outline-none resize-none bg-white font-medium"
                              dir="rtl"
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleUpdatePage(selectedBook.id, page.pageNumber, tempPageText)}
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
              <div className="bg-indigo-950 text-white p-6 rounded-2xl shadow-2xl flex flex-col h-full border border-white/5 relative overflow-hidden">
                <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/10 rounded-full -mr-16 -mt-16 blur-3xl pointer-events-none"></div>

                <div className="flex items-center gap-3 mb-6 relative">
                  <div className="bg-indigo-500/20 p-2.5 rounded-xl border border-indigo-500/30">
                    <MessageSquare className="w-5 h-5 text-indigo-300" />
                  </div>
                  <div>
                    <h3 className="font-bold text-sm">Kitabim AI Assistant</h3>
                    <div className="flex items-center gap-2">
                      <p className="text-[10px] text-indigo-300 font-bold uppercase tracking-widest">Intelligent Retrieval</p>
                      {currentPage && (
                        <div className="px-1.5 py-0.5 bg-indigo-500/30 text-[9px] rounded-md border border-indigo-500/20 text-indigo-200">
                          FOCUS: PAGE {currentPage}
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex-grow overflow-y-auto space-y-4 pr-2 mb-4 scroll-smooth">
                  {chatMessages.length === 0 && (
                    <div className="bg-white/5 border border-white/5 rounded-2xl p-6 text-center">
                      <p className="text-sm text-white/60 leading-relaxed uyghur-text">
                        مەن سىزگە بۇ كىتابتىكى مەزمۇنلارنى تېپىشقا ياردەم بېرەلەيمەن. خالىغان سوئالنى سورىسىڭىز بولىدۇ.
                      </p>
                    </div>
                  )}
                  {chatMessages.map((msg, idx) => (
                    <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[85%] px-4 py-3 rounded-2xl text-sm ${msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-none shadow-lg'
                        : 'bg-white/10 text-white rounded-tl-none border border-white/5 uyghur-text text-right leading-loose'
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
                    placeholder="Ask a question..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                    className="w-full bg-white/5 border border-white/10 rounded-xl py-3.5 pl-5 pr-12 text-sm text-white focus:ring-2 focus:ring-indigo-500 transition-all outline-none"
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={isChatting}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-indigo-50 text-indigo-600 rounded-lg hover:bg-white transition-all disabled:opacity-50"
                  >
                    <Send size={18} />
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {view === 'global-chat' && (
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
                    <h3 className="text-xl font-bold">Kitabim Global Mind</h3>
                    <p className="text-xs text-indigo-300 font-bold uppercase tracking-widest">Searching across {books.filter(b => b.status === 'ready').length} processed books</p>
                  </div>
                </div>
                <button onClick={() => setView('library')} className="p-2 hover:bg-white/10 rounded-xl transition-colors text-indigo-300 hover:text-white">
                  <X size={20} />
                </button>
              </div>

              <div className="flex-grow overflow-y-auto mb-6 space-y-6 pr-2 scrollbar-hide">
                {chatMessages.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center px-10">
                    <div className="w-20 h-20 bg-indigo-500/10 rounded-full flex items-center justify-center mb-6 border border-white/5 animate-bounce">
                      <MessageSquare className="text-indigo-400 w-10 h-10" />
                    </div>
                    <h4 className="text-lg font-bold text-white mb-2">ئەلئامان كىتابخانىسىغا خۇش كەپسىز!</h4>
                    <p className="text-indigo-300 text-sm max-w-sm leading-relaxed">
                      كۈتۈپخانىڭىزدىكى بارلىق كىتابلارنى بىراقلا ئوقۇپ، سىزگە جاۋاب بېرىش تەييار. خالىغان سوئالنى سورىسىڭىز بولىدۇ.
                    </p>
                  </div>
                ) : (
                  chatMessages.map((msg, idx) => (
                    <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[85%] p-5 rounded-3xl text-sm leading-relaxed shadow-sm ${msg.role === 'user'
                        ? 'bg-indigo-600 text-white rounded-tr-none'
                        : 'bg-white/5 text-indigo-50 border border-white/5 rounded-tl-none uyghur-text text-lg'
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
                  onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
                  placeholder="كۈتۈپخانىدىكى بارلىق كىتابلاردىن سوئال سوراش..."
                  className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-6 pr-14 text-white focus:ring-4 focus:ring-indigo-500/20 outline-none transition-all uyghur-text text-lg"
                  dir="rtl"
                />
                <button
                  onClick={handleSendMessage}
                  disabled={isChatting}
                  className="absolute left-2 top-1/2 -translate-y-1/2 p-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-500 transition-all shadow-lg active:scale-95 disabled:opacity-50"
                >
                  <Send size={20} />
                </button>
              </div>
            </div>
          </div>
        )}
        {modal.isOpen && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300" onClick={() => modal.type === 'alert' && setModal(prev => ({ ...prev, isOpen: false }))}></div>
            <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-in zoom-in-95 duration-200 border border-slate-100">
              <div className="p-8">
                <div className="flex items-center gap-3 mb-4">
                  <div className={`p-2 rounded-xl ${modal.type === 'confirm' ? 'bg-amber-100 text-amber-600' : 'bg-red-100 text-red-600'}`}>
                    <AlertCircle size={24} />
                  </div>
                  <h3 className="text-xl font-bold text-slate-900">{modal.title}</h3>
                </div>
                <p className="text-slate-600 leading-relaxed mb-8">
                  {modal.message}
                </p>
                <div className="flex items-center gap-3">
                  {modal.type === 'confirm' && (
                    <button
                      onClick={() => setModal(prev => ({ ...prev, isOpen: false }))}
                      className="flex-1 py-3 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-2xl transition-colors"
                    >
                      Cancel
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (modal.onConfirm) {
                        modal.onConfirm();
                      } else {
                        setModal(prev => ({ ...prev, isOpen: false }));
                      }
                    }}
                    className={`flex-1 py-3 px-4 text-white font-bold rounded-2xl transition-all shadow-lg active:scale-95 ${modal.type === 'confirm' ? 'bg-red-500 hover:bg-red-600 shadow-red-100' : 'bg-indigo-600 hover:bg-indigo-700 shadow-indigo-100'}`}
                  >
                    {modal.type === 'confirm' ? 'Delete Permanently' : 'Understood'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
