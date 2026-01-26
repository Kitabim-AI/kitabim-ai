import React from 'react';
import { Database, ChevronUp, ChevronDown, Tag, X, Save, RotateCcw, Trash2 } from 'lucide-react';
import { Book } from '../../types';
import { Pagination } from '../common/Pagination';

interface AdminViewProps {
  books: Book[];
  isCheckingGlobal: boolean;
  sortConfig: { key: string; direction: 'asc' | 'desc' };
  toggleSort: (key: any) => void;
  page: number;
  pageSize: number;
  totalBooks: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onOpenReader: (book: Book) => void;
  onReprocess: (bookId: string) => void;
  onDeleteBook: (bookId: string) => void;
  editingBookTagsId: string | null;
  setEditingBookTagsId: (id: string | null) => void;
  editingTagsList: string[];
  setEditingTagsList: (tags: string[] | ((prev: string[]) => string[])) => void;
  tempTags: string;
  setTempTags: (tags: string) => void;
  handleSaveTags: (bookId: string, tags: string[]) => void;
}

export const AdminView: React.FC<AdminViewProps> = ({
  books,
  isCheckingGlobal,
  sortConfig,
  toggleSort,
  page,
  pageSize,
  totalBooks,
  onPageChange,
  onPageSizeChange,
  onOpenReader,
  onReprocess,
  onDeleteBook,
  editingBookTagsId,
  setEditingBookTagsId,
  editingTagsList,
  setEditingTagsList,
  tempTags,
  setTempTags,
  handleSaveTags,
}) => {
  return (
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
                <th
                  className="px-6 py-4 cursor-pointer hover:bg-slate-100 transition-colors group"
                  onClick={() => toggleSort('title')}
                >
                  <div className="flex items-center gap-2">
                    Document
                    <div className={`transition-opacity ${sortConfig.key === 'title' ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                      {sortConfig.key === 'title' && sortConfig.direction === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>
                </th>
                <th
                  className="px-6 py-4 cursor-pointer hover:bg-slate-100 transition-colors group"
                  onClick={() => toggleSort('uploadDate')}
                >
                  <div className="flex items-center gap-2">
                    Uploaded Date
                    <div className={`transition-opacity ${sortConfig.key === 'uploadDate' ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                      {sortConfig.key === 'uploadDate' && sortConfig.direction === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>
                </th>
                <th
                  className="px-6 py-4 cursor-pointer hover:bg-slate-100 transition-colors group"
                  onClick={() => toggleSort('status')}
                >
                  <div className="flex items-center gap-2">
                    Status
                    <div className={`transition-opacity ${sortConfig.key === 'status' ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'}`}>
                      {sortConfig.key === 'status' && sortConfig.direction === 'asc' ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </div>
                  </div>
                </th>
                <th className="px-6 py-4">Pipeline Progress</th>
                <th className="px-6 py-4">Tags (Series)</th>
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
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm font-medium text-slate-700">
                      {new Date(book.uploadDate).toLocaleDateString()}
                    </div>
                    <div className="text-[10px] text-slate-400">
                      {new Date(book.uploadDate).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-1 rounded-full text-[10px] font-bold uppercase ${book.status === 'ready' ? 'bg-green-100 text-green-700' :
                        book.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                          'bg-red-100 text-red-700'
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
                    {editingBookTagsId === book.id ? (
                      <div className="flex flex-col gap-2 min-w-[200px]">
                        <div className="flex flex-wrap gap-1 max-w-[250px]">
                          {editingTagsList.map((tag, idx) => (
                            <span key={idx} className="flex items-center gap-1.5 px-2 py-0.5 bg-indigo-50 text-indigo-700 text-[10px] font-bold rounded-md border border-indigo-100 group/tag">
                              {tag}
                              <button
                                onClick={() => setEditingTagsList(prev => prev.filter((_, i) => i !== idx))}
                                className="text-indigo-300 hover:text-red-500 transition-colors"
                              >
                                <X size={10} />
                              </button>
                            </span>
                          ))}
                        </div>
                        <div className="flex gap-1.5 items-center">
                          <input
                            autoFocus
                            type="text"
                            value={tempTags}
                            onChange={e => {
                              if (e.target.value.endsWith(',')) {
                                const newTag = e.target.value.slice(0, -1).trim();
                                if (newTag && !editingTagsList.includes(newTag)) {
                                  setEditingTagsList(prev => [...prev, newTag]);
                                }
                                setTempTags('');
                              } else {
                                setTempTags(e.target.value);
                              }
                            }}
                            onKeyDown={e => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                const newTag = tempTags.trim();
                                if (newTag) {
                                  if (!editingTagsList.includes(newTag)) {
                                    setEditingTagsList(prev => [...prev, newTag]);
                                    setTempTags('');
                                  }
                                } else {
                                  handleSaveTags(book.id, editingTagsList);
                                }
                              } else if (e.key === 'Backspace' && !tempTags && editingTagsList.length > 0) {
                                setEditingTagsList(prev => prev.slice(0, -1));
                              }
                            }}
                            placeholder="Add tag..."
                            className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white flex-grow outline-none focus:ring-2 focus:ring-indigo-500/20"
                          />
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => {
                                const finalTags = [...editingTagsList];
                                const pendingTag = tempTags.trim();
                                if (pendingTag && !finalTags.includes(pendingTag)) {
                                  finalTags.push(pendingTag);
                                }
                                handleSaveTags(book.id, finalTags);
                              }}
                              className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
                              title="Save Tags"
                            >
                              <Save size={14} />
                            </button>
                            <button
                              onClick={() => {
                                setEditingBookTagsId(null);
                                setEditingTagsList([]);
                              }}
                              className="p-2 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors"
                              title="Cancel"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div
                        onClick={() => {
                          setEditingBookTagsId(book.id);
                          setEditingTagsList([...(book.tags || [])]);
                          setTempTags('');
                        }}
                        className="cursor-pointer group/tags min-h-[24px] flex items-center hover:bg-slate-50 p-1 rounded-md transition-colors"
                      >
                        {book.tags && book.tags.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {book.tags.map((t, idx) => (
                              <span key={idx} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 text-[10px] font-bold rounded-md border border-indigo-100 group-hover/tags:border-indigo-200">
                                {t}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 text-slate-300 group-hover/tags:text-indigo-400 transition-colors">
                            <Tag size={12} />
                            <span className="text-[10px] italic">Add tags...</span>
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-4">
                      <button
                        onClick={() => onOpenReader(book)}
                        className="text-indigo-600 font-bold text-sm hover:underline"
                      >
                        Open Reader
                      </button>
                      {book.status !== 'processing' && (
                        <button
                          onClick={() => onReprocess(book.id)}
                          className="text-amber-600 hover:text-amber-700 transition-colors p-1 rounded-md hover:bg-amber-50 flex items-center gap-1"
                          title="Reprocess Failed Pages"
                        >
                          <RotateCcw size={16} />
                          <span className="text-xs font-bold font-mono">FIX</span>
                        </button>
                      )}
                      <button
                        onClick={() => onDeleteBook(book.id)}
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

          <Pagination
            page={page}
            pageSize={pageSize}
            totalItems={totalBooks}
            onPageChange={onPageChange}
            onPageSizeChange={onPageSizeChange}
          />
        </div>
      )}
    </div>
  );
};
