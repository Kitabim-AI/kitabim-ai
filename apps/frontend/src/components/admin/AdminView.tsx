import React, { useState, useEffect, useRef } from 'react';
import { Database, ChevronUp, ChevronDown, Tag, X, Save, Trash2, BookType, User, Hash, BookOpen, Cpu, ScanText, History, RotateCcw, RefreshCw, MoreVertical, Globe, Shield } from 'lucide-react';
import { Book } from '@shared/types';
import { Pagination } from '../common/Pagination';
import { NotificationContainer } from '../common/NotificationContainer';
import { useI18n } from '../../i18n/I18nContext';

interface AdminViewProps {
  books: Book[];
  isCheckingGlobal: boolean;
  sortConfig: { key: string; direction: 'asc' | 'desc' };
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

  onToggleVisibility: (bookId: string, currentVisibility: string) => void;
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
  const { t } = useI18n();
  if (isOpen) {
    return (
      <div className="flex flex-col gap-3 min-w-[200px]" dir="rtl">
        <div className="flex flex-wrap gap-1.5 max-w-[250px]">
          {items.map((item, idx) => (
            <span key={idx} className="flex items-center gap-1.5 px-2.5 py-1 bg-[#0369a1]/10 text-[#0369a1] text-[14px] font-black rounded-lg border border-[#0369a1]/20 group/tag shadow-sm">
              {item}
              <button
                onClick={() => onRemoveItem(idx)}
                className="text-[#75C5F0]/50 hover:text-red-500 transition-colors"
              >
                <X size={12} strokeWidth={3} />
              </button>
            </span>
          ))}
        </div>
        <div className="flex gap-2 items-center">
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
            className="px-3 py-2 text-sm border-2 border-[#0369a1]/20 rounded-xl bg-white flex-grow outline-none focus:border-[#0369a1] focus:ring-4 focus:ring-[#0369a1]/5 transition-all"
          />
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => {
                if (tempValue.trim()) onAddItem(tempValue.trim());
                onSave();
              }}
              className="p-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0284c7] shadow-lg shadow-[#0369a1]/20 transition-all active:scale-95"
              title={t('common.save')}
            >
              <Save size={16} />
            </button>
            <button
              onClick={onClose}
              className="p-2.5 bg-slate-100 text-slate-400 rounded-xl hover:bg-slate-200 transition-all"
              title={t('common.cancel')}
            >
              <X size={16} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onOpen}
      className="cursor-pointer group/tags min-h-[32px] flex items-center hover:bg-[#0369a1]/5 p-1.5 rounded-xl transition-all"
    >
      {existingItems && existingItems.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {existingItems.map((t, idx) => (
            <span key={idx} className="px-2.5 py-1 bg-[#0369a1]/5 text-[#0369a1] text-[14px] font-black rounded-lg border border-[#0369a1]/10 group-hover/tags:border-[#0369a1]/30 shadow-sm">
              {t}
            </span>
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-slate-300 group-hover/tags:text-[#0369a1] transition-colors px-2">
          {icon || <Tag size={14} />}
          <span className="text-[14px] font-bold italic">{placeholder}</span>
        </div>
      )}
    </div>
  );
};


export const AdminView: React.FC<AdminViewProps> = ({
  books,
  isCheckingGlobal,
  sortConfig,
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
  editingBookVolumeId, setEditingBookVolumeId, tempVolume, setTempVolume, handleSaveVolume,
  onToggleVisibility
}) => {
  const { t } = useI18n();
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setActiveMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex items-center justify-between pb-6 border-b border-[#75C5F0]/20">
        <header>
          <h2 className="text-3xl font-black text-[#1a1a1a] flex items-center gap-3">
            <div className="p-2 bg-[#0369a1] rounded-xl text-white shadow-lg shadow-[#0369a1]/20">
              <Shield size={24} />
            </div>
            {t('admin.table.managementSystem')}
          </h2>
          <p className="text-[#94a3b8] font-bold mt-2">{t('admin.table.manageBooks')}</p>
        </header>
        <div className="flex items-center gap-2 text-[14px] font-black text-[#0369a1] bg-[#0369a1]/10 px-4 py-2 rounded-full border border-[#0369a1]/20 shadow-sm">
          <Cpu size={14} className="animate-spin" />
          {t('admin.table.systemActive')}
        </div>
      </div>

      <NotificationContainer />

      {isCheckingGlobal && (
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center animate-pulse">
          <Database className="w-16 h-16 text-[#75C5F0] mb-6 animate-bounce" />
          <h3 className="text-xl font-black text-[#1a1a1a]">{t('common.loading')}</h3>
          <p className="text-slate-500 font-bold">{t('admin.table.uploading')}</p>
        </div>
      )}

      {!isCheckingGlobal && (
        <div className="glass-panel overflow-hidden" style={{ borderRadius: '24px', padding: 0 }}>
          <div className="overflow-x-auto">
            <table className="w-full text-right min-w-[1100px]" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-sm font-black text-[#0369a1] uppercase tracking-widest">
                  <th className="px-8 py-5 text-right font-black">
                    {t('admin.table.bookName')}
                  </th>
                  <th className="px-8 py-5 w-24 text-right font-black">{t('admin.table.pageCount')}</th>
                  <th className="px-8 py-5 w-48 text-right font-black">{t('admin.table.author')}</th>
                  <th className="px-8 py-5 w-60 text-right font-black">{t('admin.table.category')}</th>
                  <th className="px-8 py-5 text-right font-black">{t('admin.table.progress')}</th>
                  <th className="px-8 py-5 text-left font-black">{t('admin.table.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5">
                {books.map(book => (
                  <tr key={book.id} className="hover:bg-[#e8f4f8]/20 transition-colors group/row">
                    <td className="px-8 py-6">
                      <div className="flex items-center gap-4">
                        <button
                          onClick={() => onOpenReader(book)}
                          disabled={book.status === 'pending'}
                          className={`p-3 rounded-xl transition-all shadow-sm active:scale-90 ${book.status === 'pending'
                            ? 'bg-slate-100 text-slate-300 cursor-not-allowed'
                            : 'bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white group-hover/row:scale-110'
                            }`}
                          title={t('admin.table.view')}
                        >
                          <BookOpen size={20} strokeWidth={2.5} />
                        </button>
                        {editingBookTitleId === book.id ? (
                          <div className="flex items-center gap-2 min-w-[250px]">
                            <input
                              autoFocus
                              type="text"
                              value={tempTitle}
                              onChange={e => setTempTitle(e.target.value)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') handleSaveTitle(book.id, tempTitle);
                                if (e.key === 'Escape') setEditingBookTitleId(null);
                              }}
                              className="px-3 py-2 text-sm border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none focus:ring-4 focus:ring-[#0369a1]/5"
                            />
                            <button
                              onClick={() => handleSaveTitle(book.id, tempTitle)}
                              className="p-2 bg-[#0369a1] text-white rounded-lg hover:bg-[#0284c7] shadow-lg transition-all active:scale-95"
                            >
                              <Save size={16} />
                            </button>
                            <button
                              onClick={() => setEditingBookTitleId(null)}
                              className="p-2 bg-slate-100 text-slate-400 rounded-lg hover:bg-slate-200 transition-colors"
                            >
                              <X size={16} />
                            </button>
                          </div>
                        ) : (
                          <div
                            onClick={() => {
                              setEditingBookTitleId(book.id);
                              setTempTitle(book.title || '');
                            }}
                            className="cursor-pointer group/title"
                          >
                            <span className="font-black text-[#1a1a1a] text-base group-hover/title:text-[#0369a1] transition-colors">
                              {book.title}
                            </span>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[14px] font-bold text-slate-400">
                                {new Date(book.uploadDate).toLocaleDateString()}
                              </span>
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-8 py-6">
                      {editingBookVolumeId === book.id ? (
                        <div className="flex items-center gap-1.5 min-w-[100px]">
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
                            className="no-spinner px-3 py-2 text-sm border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none"
                          />
                        </div>
                      ) : (
                        <div
                          onClick={() => {
                            setEditingBookVolumeId(book.id);
                            setTempVolume(book.volume !== null && book.volume !== undefined ? String(book.volume) : '');
                          }}
                          className="cursor-pointer p-2 hover:bg-[#0369a1]/5 rounded-xl transition-colors text-center"
                        >
                          {book.volume !== null && book.volume !== undefined ? (
                            <span className="text-sm font-black text-[#1a1a1a]">
                              {t('book.volume', { volume: book.volume })}
                            </span>
                          ) : (
                            <Hash size={16} className="text-slate-200 mx-auto" />
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-8 py-6">
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
                            className="px-3 py-2 text-sm border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none"
                          />
                        </div>
                      ) : (
                        <div
                          onClick={() => {
                            setEditingBookAuthorId(book.id);
                            setTempAuthor(book.author && book.author !== 'Unknown Author' ? book.author : '');
                          }}
                          className="cursor-pointer p-2 hover:bg-[#0369a1]/5 rounded-xl transition-colors"
                        >
                          {book.author && book.author !== 'Unknown Author' ? (
                            <span className="text-sm font-black text-[#1a1a1a]">
                              {book.author}
                            </span>
                          ) : (
                            <User size={16} className="text-slate-200" />
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-8 py-6">
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
                        placeholder={t('admin.categories.add')}
                        icon={<BookType size={14} />}
                      />
                    </td>
                    <td className="px-8 py-6">
                      <div className="flex flex-col gap-2 min-w-[140px]">
                        <div className="w-full bg-[#0369a1]/10 h-2 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all duration-500 ${(() => {
                              const isStale = book.status === 'processing' && book.processingLockExpiresAt && new Date(book.processingLockExpiresAt) < new Date();
                              if (book.status === 'error' || isStale) return 'bg-red-500';
                              if (book.status === 'ready') return 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]';
                              return 'bg-[#75C5F0] animate-pulse';
                            })()}`}
                            style={{ width: `${((book.completedCount ?? book.pages.filter(r => r.status === 'completed').length) / (book.totalPages || 1)) * 100}%` }}
                          />
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-[14px] font-black text-slate-400">
                            {book.completedCount ?? book.pages.filter(r => r.status === 'completed').length}/{book.totalPages || 0} {t('common.pages')}
                          </span>
                          <span className={`px-2 py-0.5 rounded-full text-[14px] font-black uppercase ${(() => {
                            const isStale = book.status === 'processing' && book.processingLockExpiresAt && new Date(book.processingLockExpiresAt) < new Date();
                            if (isStale) return 'bg-red-50 text-red-600';
                            return book.status === 'ready' ? 'bg-emerald-50 text-emerald-600' :
                              book.status === 'processing' ? 'bg-[#0369a1]/10 text-[#0369a1]' :
                                book.status === 'pending' ? 'bg-amber-50 text-amber-600' :
                                  'bg-red-50 text-red-600';
                          })()}`}>
                            {(() => {
                              const isStale = book.status === 'processing' && book.processingLockExpiresAt && new Date(book.processingLockExpiresAt) < new Date();
                              return isStale ? 'TIMEOUT' : book.status === 'ready' ? t('admin.table.active') :
                                book.status === 'processing' ? t('admin.table.recognizing') :
                                  book.status === 'pending' ? t('admin.table.waiting') : t('common.error');
                            })()}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="px-8 py-6 text-left">
                      <div className="relative inline-block" ref={activeMenuId === book.id ? menuRef : null}>
                        <button
                          onClick={() => setActiveMenuId(activeMenuId === book.id ? null : book.id)}
                          className="p-3 hover:bg-[#0369a1]/10 rounded-xl transition-all text-slate-400 hover:text-[#0369a1] hover:scale-110"
                        >
                          <MoreVertical size={20} />
                        </button>

                        {activeMenuId === book.id && (
                          <div className="absolute left-0 top-full mt-2 w-56 glass-panel shadow-2xl z-50 overflow-hidden py-2" style={{ borderRadius: '16px' }}>
                            <button
                              onClick={() => {
                                if (book.status !== 'pending') onOpenReader(book);
                                setActiveMenuId(null);
                              }}
                              disabled={book.status === 'pending'}
                              className={`w-full flex items-center gap-3 px-5 py-3 text-sm font-black transition-colors ${book.status === 'pending'
                                ? 'text-slate-300 cursor-not-allowed'
                                : 'text-[#1a1a1a] hover:bg-[#0369a1]/10 hover:text-[#0369a1]'
                                }`}
                            >
                              <BookOpen size={16} /> {t('admin.table.view')}
                            </button>

                            <button
                              onClick={() => {
                                onToggleVisibility(book.id, book.visibility || 'public');
                                setActiveMenuId(null);
                              }}
                              className="w-full flex items-center gap-3 px-5 py-3 text-sm font-black text-[#1a1a1a] hover:bg-[#0369a1]/10 hover:text-[#0369a1] transition-colors"
                            >
                              {book.visibility === 'private' ? (
                                <><Shield size={16} /> {t('admin.table.makePublic')}</>
                              ) : (
                                <><Globe size={16} /> {t('admin.table.makePrivate')}</>
                              )}
                            </button>

                            <div className="h-px bg-slate-100 my-2 mx-4" />

                            {(() => {
                              const isStale = book.status === 'processing' && book.processingLockExpiresAt && new Date(book.processingLockExpiresAt) < new Date();
                              const isActuallyProcessing = book.status === 'processing' && !isStale;
                              const hasFailedPages = (book.errorCount ?? 0) > 0 || book.pages?.some(r => r.status === 'error');
                              const isReady = book.status === 'ready';
                              const canRetry = (Boolean(hasFailedPages) || book.status === 'error' || isStale) && !isActuallyProcessing;
                              const canStartOcr = !isActuallyProcessing && !canRetry && !isReady;
                              const canReindex = book.status === 'ready';

                              return (
                                <>
                                  <button
                                    onClick={() => {
                                      if (canStartOcr) onStartOcr(book.id);
                                      setActiveMenuId(null);
                                    }}
                                    disabled={!canStartOcr}
                                    className={`w-full flex items-center gap-3 px-5 py-3 text-sm font-black transition-colors ${canStartOcr ? 'text-[#0369a1] hover:bg-[#0369a1]/10' : 'text-slate-300 cursor-not-allowed'
                                      }`}
                                  >
                                    <ScanText size={16} /> {t('admin.table.startOcr')}
                                  </button>

                                  <button
                                    onClick={() => {
                                      if (canRetry) onRetryFailedOcr(book);
                                      setActiveMenuId(null);
                                    }}
                                    disabled={!canRetry}
                                    className={`w-full flex items-center gap-3 px-5 py-3 text-sm font-black transition-colors ${canRetry ? 'text-amber-600 hover:bg-amber-50' : 'text-slate-300 cursor-not-allowed'
                                      }`}
                                  >
                                    <RotateCcw size={16} /> {t('admin.table.retryOcr')}
                                  </button>

                                  <button
                                    onClick={() => {
                                      if (canReindex) onReindex(book.id);
                                      setActiveMenuId(null);
                                    }}
                                    disabled={!canReindex}
                                    className={`w-full flex items-center gap-3 px-5 py-3 text-sm font-black transition-colors ${canReindex ? 'text-blue-600 hover:bg-blue-50' : 'text-slate-300 cursor-not-allowed'
                                      }`}
                                  >
                                    <RefreshCw size={16} /> {t('admin.table.reindex')}
                                  </button>
                                </>
                              );
                            })()}

                            <div className="h-px bg-slate-100 my-2 mx-4" />

                            <button
                              onClick={() => {
                                onDeleteBook(book.id);
                                setActiveMenuId(null);
                              }}
                              className="w-full flex items-center gap-3 px-5 py-3 text-sm font-black text-red-600 hover:bg-red-50 transition-colors"
                            >
                              <Trash2 size={16} /> {t('admin.table.delete')}
                            </button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-[#0369a1]/5 px-8 py-5">
            <Pagination
              page={page}
              pageSize={pageSize}
              totalItems={totalBooks}
              onPageChange={onPageChange}
              onPageSizeChange={onPageSizeChange}
            />
          </div>
        </div>
      )}
    </div>
  );
};
