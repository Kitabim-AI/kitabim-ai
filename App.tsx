
import React, { useState, useRef, useEffect } from 'react';
import {
  Library, LayoutDashboard, Search, BookOpen, Send,
  Settings, Save, Edit3, Trash2, Upload, FileText,
  Loader2, CheckCircle2, AlertCircle, ChevronRight, X, MessageSquare,
  Globe, Database, Zap
} from 'lucide-react';
import { PersistenceService } from './services/persistenceService';
import { Book, ExtractionResult, Message } from './types';

const App: React.FC = () => {
  const [view, setView] = useState<'library' | 'admin' | 'reader'>('library');
  const [books, setBooks] = useState<Book[]>([]);
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatting, setIsChatting] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingPage, setEditingPage] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [isCheckingGlobal, setIsCheckingGlobal] = useState(false);

  // Pagination for Global Library
  const [libraryPage, setLibraryPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [totalBooks, setTotalBooks] = useState(0);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const loaderRef = useRef<HTMLDivElement>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load public library on mount
  useEffect(() => {
    refreshLibrary();
  }, []);

  // Poll for updates if any book is processing
  useEffect(() => {
    const hasProcessing = books.some(b => b.status === 'processing');
    if (!hasProcessing) return;

    const interval = setInterval(async () => {
      // Poll only the first page for broad updates, or we could fetch the specific book status
      const result = await PersistenceService.getGlobalLibrary(1, 12, searchQuery);

      // We only want to update statuses of existing books, not replace the whole list if we are on page 2+
      // But for simplicity, let's just update the books that were in the first page
      setBooks(prev => {
        const updated = [...prev];
        result.books.forEach(nb => {
          const idx = updated.findIndex(ub => ub.id === nb.id);
          if (idx !== -1) updated[idx] = nb;
        });
        return updated;
      });

      // Also update selected book if it's processing
      if (selectedBook && selectedBook.status === 'processing') {
        // Fetch specific book status reliably
        const updatedSelected = await PersistenceService.getBook(selectedBook.id);
        if (updatedSelected) setSelectedBook(updatedSelected);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [books, selectedBook, searchQuery]);

  const refreshLibrary = async () => {
    setIsLoadingMore(true);
    const result = await PersistenceService.getGlobalLibrary(1, 12, searchQuery);
    setBooks(result.books);
    setTotalBooks(result.total);
    setLibraryPage(1);
    setHasMore(result.books.length < result.total);
    setIsLoadingMore(false);
  };

  const loadMoreBooks = async () => {
    if (isLoadingMore || !hasMore) return;

    setIsLoadingMore(true);
    const nextPage = libraryPage + 1;
    const result = await PersistenceService.getGlobalLibrary(nextPage, 12, searchQuery);

    if (result.books.length > 0) {
      setBooks(prev => [...prev, ...result.books]);
      setLibraryPage(nextPage);
      setHasMore(books.length + result.books.length < result.total);
    } else {
      setHasMore(false);
    }
    setIsLoadingMore(false);
  };

  // Intersection Observer for Infinite Scroll
  useEffect(() => {
    if (view !== 'library') return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore && !isLoadingMore) {
          loadMoreBooks();
        }
      },
      { threshold: 0.1 }
    );

    if (loaderRef.current) {
      observer.observe(loaderRef.current);
    }

    return () => observer.disconnect();
  }, [view, hasMore, isLoadingMore, libraryPage, searchQuery]);

  // Handle Search Input Change
  useEffect(() => {
    const timer = setTimeout(() => {
      refreshLibrary();
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const filteredBooks = books; // Since filtering is now done on backend

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || file.type !== 'application/pdf') return;

    setIsCheckingGlobal(true);
    setView('admin');

    try {
      const result = await PersistenceService.uploadFile(file);
      setIsCheckingGlobal(false);

      if (result.status === 'existing') {
        refreshLibrary();
        return;
      }

      // Refresh to see the new processing book
      refreshLibrary();
    } catch (err) {
      console.error(err);
      setIsCheckingGlobal(false);
      alert("Error uploading document. Check console for details.");
    }
  };

  const openReader = async (book: Book) => {
    try {
      // Fetch full book content including pages/results
      const fullBook = await PersistenceService.getBook(book.id);
      if (fullBook) {
        setSelectedBook(fullBook);
        setEditContent(fullBook.content);
        setChatMessages([]);
        setView('reader');
      } else {
        alert("Failed to load book content.");
      }
    } catch (err) {
      console.error("Error opening reader:", err);
      alert("Error loading book.");
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim() || !selectedBook) return;

    const userMsg: Message = { role: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsChatting(true);

    try {
      const aiResponse = await PersistenceService.chatWithBook(selectedBook.id, chatInput, currentPage);
      setChatMessages(prev => [...prev, { role: 'model', text: aiResponse }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم." }]);
    } finally {
      setIsChatting(false);
    }
  };

  const saveCorrections = async () => {
    if (!selectedBook || editingPage === null) return;

    try {
      const response = await fetch(`/api/books/${selectedBook.id}/pages/${editingPage}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: editContent }),
      });

      if (!response.ok) throw new Error("Failed to save");

      // Update local state
      const updatedResults = selectedBook.results.map(r =>
        r.pageNumber === editingPage ? { ...r, text: editContent } : r
      );

      const updatedBook = { ...selectedBook, results: updatedResults };
      setSelectedBook(updatedBook);
      setBooks(prev => prev.map(b => b.id === selectedBook.id ? updatedBook : b));

      setIsEditing(false);
      setEditingPage(null);
    } catch (err) {
      alert("Failed to save corrections.");
    }
  };

  const startEditingPage = (pageNumber: number, text: string) => {
    setEditingPage(pageNumber);
    setEditContent(text);
    setIsEditing(true);
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      <nav className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => setView('library')}>
            <div className="bg-indigo-600 p-1.5 rounded-lg shadow-sm shadow-indigo-100">
              <BookOpen className="text-white w-5 h-5" />
            </div>
            <span className="font-bold text-slate-900 tracking-tight">Uyghur Digital Library</span>
          </div>
          <div className="hidden md:flex items-center gap-1">
            <button
              onClick={() => setView('library')}
              className={`px-4 py-2 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${view === 'library' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}
            >
              <Globe size={18} /> Global Library
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
              placeholder="Search library..."
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
                <p className="text-slate-500">Shared collection of pre-processed Uyghur literature.</p>
              </header>
              <div className="flex items-center gap-2 text-xs font-bold text-slate-400 bg-slate-100 px-3 py-1.5 rounded-full">
                <Zap size={14} className="text-amber-500" />
                ZERO-REPROCESS ENABLED
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {filteredBooks.map(book => (
                <div
                  key={book.id}
                  onClick={() => openReader(book)}
                  className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer group"
                >
                  <div className="aspect-[3/4] bg-slate-50 flex items-center justify-center relative overflow-hidden">
                    <FileText className={`w-16 h-16 ${book.status === 'ready' ? 'text-slate-200' : 'text-indigo-200'} group-hover:scale-110 transition-all`} />
                    <div className="absolute top-3 right-3">
                      {book.status === 'ready' ? (
                        <CheckCircle2 size={20} className="text-green-500 bg-white rounded-full shadow-sm" />
                      ) : (
                        <div className="p-1 bg-white rounded-full shadow-sm">
                          <Loader2 size={16} className="text-indigo-600 animate-spin" />
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="p-4">
                    <h3 className="font-bold text-slate-900 truncate">{book.title}</h3>
                    <p className="text-[10px] text-slate-400 font-mono mt-1">HASH: {book.contentHash.substring(0, 12)}...</p>
                    <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider mt-4">
                      <span className="text-slate-400">{book.totalPages} Pages</span>
                      <span className={`${book.status === 'ready' ? 'text-indigo-600' : 'text-amber-600'} font-black`}>
                        {book.status === 'ready' ? 'READY' : 'PROCESSING'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
              {filteredBooks.length === 0 && !isLoadingMore && (
                <div className="col-span-full py-20 text-center border-2 border-dashed border-slate-200 rounded-3xl">
                  <Library className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-500 font-medium">No books in the persistent storage yet.</p>
                </div>
              )}
            </div>

            {/* Infinite Scroll Trigger */}
            <div ref={loaderRef} className="h-20 flex items-center justify-center">
              {isLoadingMore && (
                <div className="flex items-center gap-2 text-indigo-600 font-medium bg-white px-4 py-2 rounded-full shadow-sm border border-slate-100 animate-in fade-in zoom-in duration-300">
                  <Loader2 className="w-5 h-5 animate-spin" />
                  <span>Loading more treasures...</span>
                </div>
              )}
              {!hasMore && filteredBooks.length > 0 && (
                <p className="text-slate-400 text-sm font-medium">You've reached the end of the collection.</p>
              )}
            </div>
          </div>
        )}

        {view === 'admin' && (
          <div className="space-y-6">
            <header>
              <h2 className="text-2xl font-bold text-slate-800">Processing Pipeline</h2>
              <p className="text-slate-500">Managing global document indexing.</p>
            </header>

            {isCheckingGlobal && (
              <div className="bg-indigo-50 border border-indigo-100 p-8 rounded-2xl flex flex-col items-center justify-center text-center animate-pulse">
                <Database className="w-12 h-12 text-indigo-400 mb-4 animate-bounce" />
                <h3 className="font-bold text-indigo-900">Checking Global Document DB...</h3>
                <p className="text-indigo-600 text-sm">Identifying unique content signature to avoid duplicate processing costs.</p>
              </div>
            )}

            {!isCheckingGlobal && (
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-500 uppercase tracking-wider">
                      <th className="px-6 py-4">Document Hash</th>
                      <th className="px-6 py-4">Status</th>
                      <th className="px-6 py-4">Global Progress</th>
                      <th className="px-6 py-4">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {books.map(book => (
                      <tr key={book.id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div className="bg-indigo-50 p-2 rounded-lg text-indigo-600">
                              <Database size={18} />
                            </div>
                            <div>
                              <div className="font-bold text-slate-900 text-sm truncate max-w-[200px]">{book.title}</div>
                              <div className="text-[10px] font-mono text-slate-400">{book.contentHash}</div>
                            </div>
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
                          <div className="flex items-center gap-3">
                            <div className="w-full max-w-[150px] bg-slate-100 h-1.5 rounded-full overflow-hidden">
                              <div
                                className="bg-indigo-600 h-full transition-all duration-500"
                                style={{ width: `${(book.results.filter(r => r.status === 'completed').length / (book.totalPages || 1)) * 100}%` }}
                              />
                            </div>
                            <span className="text-[10px] font-bold text-slate-400">
                              {Math.round((book.results.filter(r => r.status === 'completed').length / (book.totalPages || 1)) * 100)}%
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <button onClick={() => openReader(book)} className="text-indigo-600 font-bold text-sm hover:underline">
                            Details
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
                  <p className="text-[10px] font-mono text-slate-400">{selectedBook.contentHash}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => setView('library')} className="p-2 text-slate-400 hover:bg-slate-200 rounded-lg transition-colors">
                    <X size={20} />
                  </button>
                </div>
              </div>

              <div className="flex-grow p-10 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/paper-fibers.png')] scroll-smooth">
                <div className="max-w-3xl mx-auto space-y-12">
                  {(selectedBook.results || []).sort((a, b) => a.pageNumber - b.pageNumber).map((page, idx) => (
                    <div
                      key={idx}
                      id={`page-${page.pageNumber}`}
                      className={`relative p-8 rounded-xl transition-all ${editingPage === page.pageNumber ? 'bg-indigo-50 border-2 border-indigo-200' : 'bg-transparent border border-transparent hover:border-slate-100'}`}
                      onMouseEnter={() => setCurrentPage(page.pageNumber)}
                    >
                      <div className="absolute -left-12 top-8 text-slate-300 font-mono text-sm tracking-tighter transform -rotate-90">
                        PAGE {page.pageNumber}
                      </div>

                      {isEditing && editingPage === page.pageNumber ? (
                        <div className="space-y-4">
                          <textarea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            className="w-full h-80 p-6 uyghur-text text-2xl border-none ring-2 ring-indigo-500 rounded-xl outline-none resize-none bg-white shadow-xl"
                            dir="rtl"
                            autoFocus
                          />
                          <div className="flex justify-end gap-2">
                            <button onClick={() => { setIsEditing(false); setEditingPage(null); }} className="px-4 py-2 text-slate-500 font-bold text-sm">Cancel</button>
                            <button onClick={saveCorrections} className="px-6 py-2 bg-indigo-600 text-white font-bold rounded-lg shadow-lg">Save Changes</button>
                          </div>
                        </div>
                      ) : (
                        <div className="group relative">
                          <button
                            onClick={() => startEditingPage(page.pageNumber, page.text)}
                            className="absolute -right-4 top-0 p-2 text-slate-300 hover:text-indigo-600 opacity-0 group-hover:opacity-100 transition-all bg-white rounded-full shadow-sm border border-slate-100"
                          >
                            <Edit3 size={16} />
                          </button>
                          <div className="uyghur-text text-3xl text-slate-800 leading-relaxed whitespace-pre-wrap drop-shadow-sm">
                            {page.text || (
                              <div className="flex items-center gap-2 text-slate-300 italic text-lg">
                                <Loader2 size={18} className="animate-spin text-indigo-400" />
                                Processing page content...
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                  {selectedBook.results?.length === 0 && (
                    <div className="py-20 text-center text-slate-400 italic">No pages extracted yet.</div>
                  )}
                </div>
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
                    <h3 className="font-bold text-sm">Contextual Assistant</h3>
                    <p className="text-[10px] text-indigo-300 font-bold uppercase tracking-widest">Global RAG Engine</p>
                  </div>
                </div>

                <div className="flex-grow overflow-y-auto space-y-4 pr-2 mb-4 scroll-smooth scrollbar-thin scrollbar-thumb-white/10">
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
                        ? 'bg-indigo-600 text-white rounded-tr-none shadow-lg shadow-indigo-900/40'
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
                    placeholder="Ask about this book..."
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
                    className="w-full bg-white/5 border border-white/10 rounded-xl py-3.5 pl-5 pr-12 text-sm text-white placeholder:text-white/20 focus:bg-white/10 focus:ring-2 focus:ring-indigo-500/50 transition-all outline-none"
                  />
                  <button
                    onClick={handleSendMessage}
                    disabled={isChatting}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-400 active:scale-90 transition-all disabled:opacity-50"
                  >
                    <Send size={18} />
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
