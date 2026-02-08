import React from 'react';
import { Database, ChevronUp, ChevronDown, Tag, X, Save, Trash2, BookType, User, Hash, BookOpen, Cpu, ScanText, History, RotateCcw, RefreshCw } from 'lucide-react';
import { Book } from '@shared/types';
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
  onStartOcr: (bookId: string) => void;
  onRetryFailedOcr: (book: Book) => void;

  onReindex: (bookId: string) => void;
  onDeleteBook: (bookId: string) => void;

  editingBookTitleId: string | null;
  setEditingBookTitleId: (id: string | null) => void;
  tempTitle: string;
  setTempTitle: (val: string) => void;
  handleSaveTitle: (bookId: string, title: string) => void;

  editingBookCategoriesId: string | null;
  setEditingBookCategoriesId: (id: string | null) => void;
  editingCategoriesList: string[];
  setEditingCategoriesList: (items: string[] | ((prev: string[]) => string[])) => void;
  tempCategories: string;
  setTempCategories: (val: string) => void;
  handleSaveCategories: (bookId: string, items: string[]) => void;

  editingBookAuthorId: string | null;
  setEditingBookAuthorId: (id: string | null) => void;
  tempAuthor: string;
  setTempAuthor: (val: string) => void;
  handleSaveAuthor: (bookId: string, author: string) => void;

  editingBookVolumeId: string | null;
  setEditingBookVolumeId: (id: string | null) => void;
  tempVolume: string;
  setTempVolume: (val: string) => void;
  handleSaveVolume: (bookId: string, volume: string) => void;
}

const TagEditor: React.FC<{
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
  onSave: () => void;
  items: string[];
  tempValue: string;
  onTempValueChange: (val: string) => void;
  onAddItem: (val: string) => void;
  onRemoveItem: (index: number) => void;
  existingItems: string[];
  placeholder?: string;
  icon?: React.ReactNode;
}> = ({ isOpen, onOpen, onClose, onSave, items, tempValue, onTempValueChange, onAddItem, onRemoveItem, existingItems, placeholder, icon }) => {
  if (isOpen) {
    return (
      <div className="flex flex-col gap-2 min-w-[200px]">
        <div className="flex flex-wrap gap-1 max-w-[250px]">
          {items.map((item, idx) => (
            <span key={idx} className="flex items-center gap-1.5 px-2 py-0.5 bg-indigo-50 text-indigo-700 text-[10px] font-bold rounded-md border border-indigo-100 group/tag">
              {item}
              <button
                onClick={() => onRemoveItem(idx)}
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
            value={tempValue}
            onChange={e => {
              if (e.target.value.endsWith(',')) {
                onAddItem(e.target.value.slice(0, -1).trim());
              } else {
                onTempValueChange(e.target.value);
              }
            }}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                e.preventDefault();
                if (tempValue.trim()) {
                  onAddItem(tempValue.trim());
                } else {
                  onSave();
                }
              } else if (e.key === 'Backspace' && !tempValue && items.length > 0) {
                onRemoveItem(items.length - 1);
              }
            }}
            placeholder={placeholder}
            className="px-2 py-1.5 text-xs border border-slate-200 rounded-lg bg-white flex-grow outline-none focus:ring-2 focus:ring-indigo-500/20"
          />
          <div className="flex items-center gap-1">
            <button
              onClick={() => {
                if (tempValue.trim()) onAddItem(tempValue.trim());
                onSave();
              }}
              className="p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
              title="Save"
            >
              <Save size={14} />
            </button>
            <button
              onClick={onClose}
              className="p-2 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors"
              title="Cancel"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onOpen}
      className="cursor-pointer group/tags min-h-[24px] flex items-center hover:bg-slate-50 p-1 rounded-md transition-colors"
    >
      {existingItems && existingItems.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {existingItems.map((t, idx) => (
            <span key={idx} className="px-1.5 py-0.5 bg-indigo-50 text-indigo-700 text-[10px] font-bold rounded-md border border-indigo-100 group-hover/tags:border-indigo-200">
              {t}
            </span>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-1 text-slate-300 group-hover/tags:text-indigo-400 transition-colors">
          {icon || <Tag size={12} />}
          <span className="text-[10px] italic">{placeholder}</span>
        </div>
      )}
    </div>
  );
};

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
  onStartOcr,
  onRetryFailedOcr,

  onReindex,
  onDeleteBook,

  editingBookCategoriesId, setEditingBookCategoriesId, editingCategoriesList, setEditingCategoriesList, tempCategories, setTempCategories, handleSaveCategories,
  editingBookAuthorId, setEditingBookAuthorId, tempAuthor, setTempAuthor, handleSaveAuthor,
  editingBookTitleId, setEditingBookTitleId, tempTitle, setTempTitle, handleSaveTitle,
  editingBookVolumeId, setEditingBookVolumeId, tempVolume, setTempVolume, handleSaveVolume
}) => {
  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold text-slate-800">Kitabim Processing Pipeline</h2>
        <p className="text-slate-500">Managing global document indexing and OCR extraction.</p>
        <p className="text-xs text-slate-400 mt-1">Uploads stay pending until you start Gemini OCR.</p>
      </header>

      {isCheckingGlobal && (
        <div className="bg-indigo-50 border border-indigo-100 p-8 rounded-2xl flex flex-col items-center justify-center text-center animate-pulse">
          <Database className="w-12 h-12 text-indigo-400 mb-4 animate-bounce" />
          <h3 className="font-bold text-indigo-900">Uploading to Server...</h3>
          <p className="text-indigo-600 text-sm">Transferring document for background processing.</p>
        </div>
      )}

      {!isCheckingGlobal && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm overflow-x-auto">
          <table className="w-full text-left min-w-[1100px]">
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
                <th className="px-6 py-4 w-28">Volume</th>
                <th className="px-6 py-4 w-48">Author</th>
                <th className="px-6 py-4 w-40">Categories</th>
                <th className="px-6 py-4">Pipeline</th>
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
                      {editingBookTitleId === book.id ? (
                        <div className="flex items-center gap-1.5 min-w-[200px]">
                          <input
                            autoFocus
                            type="text"
                            value={tempTitle}
                            onChange={e => setTempTitle(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleSaveTitle(book.id, tempTitle);
                              if (e.key === 'Escape') setEditingBookTitleId(null);
                            }}
                            className="px-2 py-1 text-xs border border-slate-200 rounded-lg bg-white w-full outline-none focus:ring-2 focus:ring-indigo-500/20"
                          />
                          <button
                            onClick={() => handleSaveTitle(book.id, tempTitle)}
                            className="p-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
                            title="Save"
                          >
                            <Save size={12} />
                          </button>
                          <button
                            onClick={() => setEditingBookTitleId(null)}
                            className="p-1.5 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors"
                            title="Cancel"
                          >
                            <X size={12} />
                          </button>
                        </div>
                      ) : (
                        <div
                          onClick={() => {
                            setEditingBookTitleId(book.id);
                            setTempTitle(book.title || '');
                          }}
                          className="cursor-pointer group/title min-h-[24px] flex flex-col justify-center hover:bg-slate-50 p-1 rounded-md transition-colors"
                        >
                          <span className="font-bold text-slate-900 text-sm truncate max-w-[200px] group-hover/title:text-indigo-600">
                            {book.title}
                          </span>
                          <span className="text-[10px] text-slate-400 mt-0.5">
                            {new Date(book.uploadDate).toLocaleDateString()}
                          </span>
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    {editingBookVolumeId === book.id ? (
                      <div className="flex items-center gap-1.5 min-w-[90px]">
                        <input
                          autoFocus
                          type="number"
                          min={0}
                          step={1}
                          value={tempVolume}
                          onChange={e => setTempVolume(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleSaveVolume(book.id, tempVolume);
                            if (e.key === 'Escape') setEditingBookVolumeId(null);
                          }}
                          className="no-spinner px-2 py-1 text-xs border border-slate-200 rounded-lg bg-white w-full outline-none focus:ring-2 focus:ring-indigo-500/20"
                        />
                        <button
                          onClick={() => handleSaveVolume(book.id, tempVolume)}
                          className="p-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
                          title="Save"
                        >
                          <Save size={12} />
                        </button>
                        <button
                          onClick={() => setEditingBookVolumeId(null)}
                          className="p-1.5 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors"
                          title="Cancel"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ) : (
                      <div
                        onClick={() => {
                          setEditingBookVolumeId(book.id);
                          setTempVolume(book.volume !== null && book.volume !== undefined ? String(book.volume) : '');
                        }}
                        className="cursor-pointer group/volume min-h-[24px] flex items-center hover:bg-slate-50 p-1 rounded-md transition-colors"
                      >
                        {book.volume !== null && book.volume !== undefined ? (
                          <span className="text-sm font-medium text-slate-600 group-hover/volume:text-indigo-600">
                            {book.volume}
                          </span>
                        ) : (
                          <div className="flex items-center gap-1 text-slate-300 group-hover/volume:text-indigo-400 transition-colors">
                            <Hash size={12} />
                            <span className="text-[10px] italic">Add volume...</span>
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {editingBookAuthorId === book.id ? (
                      <div className="flex items-center gap-1.5 min-w-[150px]">
                        <input
                          autoFocus
                          type="text"
                          value={tempAuthor}
                          onChange={e => setTempAuthor(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleSaveAuthor(book.id, tempAuthor);
                            if (e.key === 'Escape') setEditingBookAuthorId(null);
                          }}
                          className="px-2 py-1 text-xs border border-slate-200 rounded-lg bg-white flex-grow outline-none focus:ring-2 focus:ring-indigo-500/20"
                        />
                        <button
                          onClick={() => handleSaveAuthor(book.id, tempAuthor)}
                          className="p-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 shadow-sm transition-all active:scale-95"
                          title="Save"
                        >
                          <Save size={12} />
                        </button>
                        <button
                          onClick={() => setEditingBookAuthorId(null)}
                          className="p-1.5 bg-slate-100 text-slate-500 rounded-lg hover:bg-slate-200 transition-colors"
                          title="Cancel"
                        >
                          <X size={12} />
                        </button>
                      </div>
                    ) : (
                      <div
                        onClick={() => {
                          setEditingBookAuthorId(book.id);
                          setTempAuthor(book.author || '');
                        }}
                        className="cursor-pointer group/author min-h-[24px] flex items-center hover:bg-slate-50 p-1 rounded-md transition-colors"
                      >
                        {book.author && book.author !== 'Unknown Author' ? (
                          <span className="text-sm font-medium text-slate-600 group-hover/author:text-indigo-600 truncate max-w-[180px]">
                            {book.author}
                          </span>
                        ) : (
                          <div className="flex items-center gap-1 text-slate-300 group-hover/author:text-indigo-400 transition-colors">
                            <User size={12} />
                            <span className="text-[10px] italic">Add author...</span>
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <TagEditor
                      isOpen={editingBookCategoriesId === book.id}
                      onOpen={() => {
                        setEditingBookCategoriesId(book.id);
                        setEditingCategoriesList([...(book.categories || [])]);
                        setTempCategories('');
                      }}
                      onClose={() => {
                        setEditingBookCategoriesId(null);
                        setEditingCategoriesList([]);
                      }}
                      onSave={() => {
                        let list = [...editingCategoriesList];
                        if (tempCategories.trim() && !list.includes(tempCategories.trim())) list.push(tempCategories.trim());
                        handleSaveCategories(book.id, list);
                      }}
                      items={editingCategoriesList}
                      tempValue={tempCategories}
                      onTempValueChange={setTempCategories}
                      onAddItem={(val) => {
                        if (val && !editingCategoriesList.includes(val)) setEditingCategoriesList(prev => [...prev, val]);
                        setTempCategories('');
                      }}
                      onRemoveItem={(idx) => setEditingCategoriesList(prev => prev.filter((_, i) => i !== idx))}
                      existingItems={book.categories || []}
                      placeholder="Add category..."
                      icon={<BookType size={12} />}
                    />
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col gap-1.5 min-w-[120px]">
                      <div className="flex items-center gap-2">
                        <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-500 ${book.processingStep === 'rag' ? 'bg-amber-500 animate-pulse' : 'bg-indigo-600'}`}
                            style={{ width: `${((book.completedCount ?? book.pages.filter(r => r.status === 'completed').length) / (book.totalPages || 1)) * 100}%` }}
                          />
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-bold text-slate-400">
                          {book.completedCount ?? book.pages.filter(r => r.status === 'completed').length}/{book.totalPages || 0} pages
                        </span>
                        <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase ${book.status === 'ready' ? 'bg-green-100 text-green-700' :
                          book.status === 'processing' ? 'bg-blue-100 text-blue-700' :
                            book.status === 'pending' ? 'bg-amber-100 text-amber-700' :
                              'bg-red-100 text-red-700'
                          }`}>
                          {book.status}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => {
                          if (book.status !== 'pending') onOpenReader(book);
                        }}
                        disabled={book.status === 'pending'}
                        className={`p-2 rounded-lg transition-all shadow-sm ${book.status === 'pending'
                          ? 'bg-slate-50 text-slate-300 cursor-not-allowed opacity-60'
                          : 'bg-emerald-50 text-emerald-600 hover:bg-emerald-600 hover:text-white active:scale-95 shadow-emerald-100/50'
                          }`}
                        title={book.status === 'pending' ? 'NO CONTENT' : 'VIEW'}
                      >
                        <BookOpen size={14} className="stroke-[2.5]" />
                      </button>
                      <>

                        {(() => {
                          const isProcessing = book.status === 'processing';
                          const hasFailedPages = (book.errorCount ?? 0) > 0 || book.pages?.some(r => r.status === 'error');
                          const isReady = book.status === 'ready';

                          // Retry is available if we have errors/failures and are not currently processing
                          const canRetry = (Boolean(hasFailedPages) || book.status === 'error') && !isProcessing;

                          // Start OCR (Reset) is available only if we are NOT processing AND NOT in a state where Retry is preferred AND NOT Ready
                          // We disable Start OCR for Ready books to prevent accidental resets.
                          const canStartOcr = !isProcessing && !canRetry && !isReady;

                          return (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => {
                                  if (canStartOcr) onStartOcr(book.id);
                                }}
                                disabled={!canStartOcr}
                                className={`p-2 rounded-lg transition-all shadow-sm shadow-indigo-100/50 ${canStartOcr
                                  ? 'bg-indigo-50 text-indigo-600 hover:bg-indigo-600 hover:text-white active:scale-95'
                                  : 'bg-indigo-50 text-indigo-200 cursor-not-allowed opacity-60'
                                  }`}
                                title={canStartOcr ? 'START GEMINI OCR' : (canRetry ? 'USE RETRY INSTEAD' : (isReady ? 'ALREADY COMPLETED' : 'OCR IN PROGRESS'))}
                              >
                                <ScanText size={14} className="stroke-[2.5]" />
                              </button>
                              <button
                                onClick={() => {
                                  if (canRetry) onRetryFailedOcr(book);
                                }}
                                disabled={!canRetry}
                                className={`p-2 rounded-lg transition-all shadow-sm shadow-amber-100/50 ${canRetry
                                  ? 'bg-amber-50 text-amber-700 hover:bg-amber-500 hover:text-white active:scale-95'
                                  : 'bg-amber-50 text-amber-200 cursor-not-allowed opacity-60'
                                  }`}
                                title={canRetry ? 'RETRY FAILED PAGES (RESUME)' : 'NO FAILED PAGES'}
                              >
                                <RotateCcw size={12} className="stroke-[2.5]" />
                              </button>
                            </div>
                          );
                        })()}
                        {(() => {
                          const canReindex = book.status === 'ready';
                          return (
                            <button
                              onClick={() => {
                                if (canReindex) onReindex(book.id);
                              }}
                              disabled={!canReindex}
                              className={`p-2 rounded-lg transition-all shadow-sm shadow-blue-100/50 ${canReindex
                                ? 'bg-blue-50 text-blue-600 hover:bg-blue-600 hover:text-white active:scale-95'
                                : 'bg-blue-50 text-blue-200 cursor-not-allowed opacity-60'
                                }`}
                              title={canReindex ? 'RE-INDEX (SEMANTIC CHUNKING)' : 'PROCESSING'}
                            >
                              <RefreshCw size={14} className="stroke-[2.5]" />
                            </button>
                          );
                        })()}
                      </>
                      <button
                        onClick={() => onDeleteBook(book.id)}
                        className="p-2 bg-red-50 text-red-500 rounded-lg hover:bg-red-500 hover:text-white transition-all active:scale-95 shadow-sm shadow-red-100/50"
                        title="DELETE"
                      >
                        <Trash2 size={14} />
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
