
import React, { useState, useRef, useEffect } from 'react';
import {
  Library, LayoutDashboard, Search, BookOpen, Send,
  Save, Edit3, Upload, FileText,
  Loader2, CheckCircle2, X, MessageSquare,
  Globe, Database, Zap, Trash2
} from 'lucide-react';
import { getPageCount, convertPageToBase64Image, generateFileHash } from './services/pdfService';
import { extractUyghurText, chatWithBook } from './services/geminiService';
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
  const [editContent, setEditContent] = useState('');
  const [isCheckingGlobal, setIsCheckingGlobal] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    refreshLibrary();
  }, []);

  const refreshLibrary = async () => {
    const globalBooks = await PersistenceService.getGlobalLibrary();
    setBooks(globalBooks);
  };

  const filteredBooks = books.filter(b =>
    b.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    b.author.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || file.type !== 'application/pdf') return;

    setIsCheckingGlobal(true);
    setView('admin');

    try {
      const hash = await generateFileHash(file);
      const existingBook = await PersistenceService.findBookByHash(hash);

      if (existingBook) {
        setIsCheckingGlobal(false);
        refreshLibrary();
        return;
      }

      setIsCheckingGlobal(false);
      const newBook: Book = {
        id: Math.random().toString(36).substr(2, 9),
        contentHash: hash,
        title: file.name.replace('.pdf', ''),
        author: 'Unknown Author',
        totalPages: 0,
        content: '',
        results: [],
        status: 'processing',
        uploadDate: new Date(),
      };

      setBooks(prev => [newBook, ...prev]);

      const totalPages = await getPageCount(file);
      const initialResults: ExtractionResult[] = Array.from({ length: totalPages }, (_, i) => ({
        pageNumber: i + 1,
        text: '',
        status: 'pending'
      }));

      setBooks(prev => prev.map(b => b.contentHash === hash ? { ...b, totalPages, results: initialResults } : b));

      let fullContent = '';
      for (let i = 0; i < totalPages; i++) {
        const base64 = await convertPageToBase64Image(file, i + 1);
        const text = await extractUyghurText(base64);
        fullContent += text + '\n\n';

        setBooks(prev => prev.map(b => {
          if (b.contentHash === hash) {
            const newRes = [...b.results];
            newRes[i] = { ...newRes[i], text, status: 'completed' };
            return { ...b, results: newRes, content: fullContent };
          }
          return b;
        }));
      }

      setBooks(prev => prev.map(b => {
        if (b.contentHash === hash) {
          const finalBook = { ...b, status: 'ready' as const };
          PersistenceService.saveBookGlobally(finalBook);
          return finalBook;
        }
        return b;
      }));
    } catch (err) {
      console.error(err);
      setIsCheckingGlobal(false);
    }
  };

  const openReader = (book: Book) => {
    setSelectedBook(book);
    setEditContent(book.content);
    setChatMessages([]);
    setView('reader');
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim() || !selectedBook) return;

    const userMsg: Message = { role: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
    setIsChatting(true);

    try {
      const aiResponse = await chatWithBook(chatInput, selectedBook.content, []);
      setChatMessages(prev => [...prev, { role: 'model', text: aiResponse }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم." }]);
    } finally {
      setIsChatting(false);
    }
  };

  const saveCorrections = () => {
    if (!selectedBook) return;
    const updatedBooks = books.map(b => b.id === selectedBook.id ? { ...b, content: editContent } : b);
    setBooks(updatedBooks);

    const fullUpdatedBook = updatedBooks.find(b => b.id === selectedBook.id);
    if (fullUpdatedBook) PersistenceService.saveBookGlobally(fullUpdatedBook);

    setSelectedBook({ ...selectedBook, content: editContent });
    setIsEditing(false);
  };

  const handleDeleteBook = async (bookId: string) => {
    if (!confirm('Are you sure you want to delete this book? This will permanently remove it from the global library.')) return;

    await PersistenceService.deleteBook(bookId);
    setBooks(prev => prev.filter(b => b.id !== bookId));
    if (selectedBook?.id === bookId) {
      setSelectedBook(null);
      setView('library');
    }
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

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {filteredBooks.map(book => (
                <div
                  key={book.id}
                  onClick={() => openReader(book)}
                  className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer group"
                >
                  <div className="aspect-[3/4] bg-slate-50 flex items-center justify-center relative overflow-hidden">
                    <FileText className="w-16 h-16 text-slate-200 group-hover:scale-110 group-hover:text-indigo-100 transition-all" />
                    <div className="absolute top-3 right-3">
                      <CheckCircle2 size={20} className="text-green-500 bg-white rounded-full shadow-sm" />
                    </div>
                  </div>
                  <div className="p-4">
                    <h3 className="font-bold text-slate-900 truncate">{book.title}</h3>
                    <p className="text-[10px] text-slate-400 font-mono mt-1">HASH: {book.contentHash.substring(0, 12)}...</p>
                    <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-wider mt-4">
                      <span className="text-slate-400">{book.totalPages} Pages</span>
                      <span className="text-indigo-600 font-black tracking-widest">KITABIM READY</span>
                    </div>
                  </div>
                </div>
              ))}
              {filteredBooks.length === 0 && (
                <div className="col-span-full py-20 text-center border-2 border-dashed border-slate-200 rounded-3xl">
                  <Library className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-500 font-medium">No books indexed in the global database yet.</p>
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
                <h3 className="font-bold text-indigo-900">Checking Kitabim Global DB...</h3>
                <p className="text-indigo-600 text-sm">Validating file signature against existing knowledge.</p>
              </div>
            )}

            {!isCheckingGlobal && (
              <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                <table className="w-full text-left">
                  <thead>
                    <tr className="bg-slate-50 border-b border-slate-200 text-xs font-bold text-slate-500 uppercase tracking-wider">
                      <th className="px-6 py-4">Document Hash</th>
                      <th className="px-6 py-4">Status</th>
                      <th className="px-6 py-4">Pipeline Progress</th>
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
                          <div className="flex items-center gap-4">
                            <button onClick={() => openReader(book)} className="text-indigo-600 font-bold text-sm hover:underline">
                              Open Reader
                            </button>
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
                  {!isEditing ? (
                    <button onClick={() => setIsEditing(true)} className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 text-slate-700 text-sm font-semibold rounded-lg hover:bg-slate-50 transition-colors">
                      <Edit3 size={16} /> Global Edit
                    </button>
                  ) : (
                    <button onClick={saveCorrections} className="flex items-center gap-2 px-3 py-1.5 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-100">
                      <Save size={16} /> Update Knowledge Base
                    </button>
                  )}
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
                  <div className="uyghur-text text-3xl text-slate-800 leading-relaxed whitespace-pre-wrap max-w-3xl mx-auto drop-shadow-sm">
                    {selectedBook.content || "Empty content"}
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
                    <p className="text-[10px] text-indigo-300 font-bold uppercase tracking-widest">Intelligent Retrieval</p>
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
      </main>
    </div>
  );
};

export default App;
