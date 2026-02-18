import React, { useState, useEffect, useRef } from 'react';
import { Database, Book as BookIcon, User, Hash, BookOpen, MoreVertical, Save, X } from 'lucide-react';
import { Pagination } from '../common/Pagination';
import { NotificationContainer } from '../common/NotificationContainer';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';
import { TagEditor } from './TagEditor';
import { ProgressBar } from './ProgressBar';
import { ActionMenu } from './ActionMenu';

export const AdminView: React.FC = () => {
  const {
    sortedBooks: books,
    totalBooks,
    page,
    pageSize,
    setPage,
    setPageSize,
    bookActions
  } = useAppContext();
  const { t } = useI18n();

  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Local editing state
  const [editingTitleId, setEditingTitleId] = useState<string | null>(null);
  const [tempTitle, setTempTitle] = useState('');

  const [editingAuthorId, setEditingAuthorId] = useState<string | null>(null);
  const [tempAuthor, setTempAuthor] = useState('');

  const [editingVolumeId, setEditingVolumeId] = useState<string | null>(null);
  const [tempVolume, setTempVolume] = useState('');

  const [editingCategoriesId, setEditingCategoriesId] = useState<string | null>(null);
  const [editingCategoriesList, setEditingCategoriesList] = useState<string[]>([]);
  const [tempCategory, setTempCategory] = useState('');

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setActiveMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSaveTitle = async (id: string, title: string) => {
    await bookActions.handleSaveTitle(id, title, setEditingTitleId, setTempTitle);
  };

  const handleSaveAuthor = async (id: string, author: string) => {
    await bookActions.handleSaveAuthor(id, author, setEditingAuthorId, setTempAuthor);
  };

  const handleSaveVolume = async (id: string, volume: string) => {
    await bookActions.handleSaveVolume(id, volume, setEditingVolumeId, setTempVolume);
  };

  const handleSaveCategories = async (id: string, list: string[]) => {
    await bookActions.handleSaveCategories(id, list, setEditingCategoriesId, setEditingCategoriesList);
  };

  return (
    <div className="space-y-8 animate-fade-in" lang="ug">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-4 group">
          <div className="p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
            <BookIcon size={24} />
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.table.managementSystem')}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <p className="text-[12px] md:text-[14px] font-normal text-[#94a3b8] uppercase">{t('admin.table.manageBooks')}</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3 px-6 py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-2xl border border-[#0369a1]/10 shadow-inner w-fit">
          <BookOpen size={18} strokeWidth={2.5} />
          <span className="text-sm font-normal uppercase">
            {t('chat.libraryBookCount', { count: totalBooks })}
          </span>
        </div>
      </div>

      <NotificationContainer />

      {bookActions.isCheckingGlobal && (
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center animate-pulse">
          <Database className="w-16 h-16 text-[#75C5F0] mb-6 animate-bounce" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
          <p className="text-slate-500 font-normal">{t('admin.table.uploading')}</p>
        </div>
      )}

      {!bookActions.isCheckingGlobal && (
        <div className="glass-panel overflow-hidden rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-right min-w-[1000px]" dir="rtl">
              <thead>
                <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-[14px] md:text-[16px] font-normal text-[#0369a1] uppercase">
                  <th className="px-6 py-5 text-right font-normal">{t('admin.table.bookName')}</th>
                  <th className="px-6 py-5 w-24 text-right font-normal">{t('admin.table.pageCount')}</th>
                  <th className="px-6 py-5 w-48 text-right font-normal">{t('admin.table.author')}</th>
                  <th className="px-6 py-5 w-60 text-right font-normal">{t('admin.table.category')}</th>
                  <th className="px-6 py-5 text-right font-normal">{t('admin.table.progress')}</th>
                  <th className="px-6 py-5 text-left font-normal">{t('admin.table.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5">
                {books.map(book => (
                  <tr key={book.id} className="hover:bg-[#e8f4f8]/20 transition-colors group/row">
                    <td className="px-6 py-6 font-uyghur">
                      <div className="flex items-center gap-4">
                        <button
                          onClick={() => bookActions.openReader(book, () => { }, () => { }, () => { })}
                          disabled={book.status === 'pending'}
                          className={`p-3 rounded-xl transition-all shadow-sm active:scale-90 ${book.status === 'pending'
                            ? 'bg-slate-100 text-slate-300 cursor-not-allowed'
                            : 'bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white group-hover/row:scale-110'
                            }`}
                          title={t('admin.table.view')}
                        >
                          <BookOpen size={20} strokeWidth={2.5} />
                        </button>
                        {editingTitleId === book.id ? (
                          <div className="flex items-center gap-2 min-w-[250px]">
                            <input
                              autoFocus
                              type="text"
                              value={tempTitle}
                              onChange={e => setTempTitle(e.target.value)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') handleSaveTitle(book.id, tempTitle);
                                if (e.key === 'Escape') setEditingTitleId(null);
                              }}
                              className="px-3 py-2 text-[16px] border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none focus:ring-4 focus:ring-[#0369a1]/5"
                            />
                            <button onClick={() => handleSaveTitle(book.id, tempTitle)} className="p-2 bg-[#0369a1] text-white rounded-lg"><Save size={16} /></button>
                            <button onClick={() => setEditingTitleId(null)} className="p-2 bg-slate-100 text-slate-400 rounded-lg"><X size={16} /></button>
                          </div>
                        ) : (
                          <div onClick={() => { setEditingTitleId(book.id); setTempTitle(book.title || ''); }} className="cursor-pointer group/title">
                            <span className="font-black text-[#1a1a1a] text-[18px] group-hover/title:text-[#0369a1] transition-colors">{book.title}</span>
                            <div className="text-[12px] font-bold text-slate-400 mt-0.5">{new Date(book.uploadDate).toLocaleDateString()}</div>
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-6 text-center">
                      {editingVolumeId === book.id ? (
                        <input
                          autoFocus
                          type="number"
                          value={tempVolume}
                          onChange={e => setTempVolume(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleSaveVolume(book.id, tempVolume);
                            if (e.key === 'Escape') setEditingVolumeId(null);
                          }}
                          className="no-spinner px-3 py-2 border-2 border-[#0369a1] rounded-xl bg-white w-20 outline-none"
                        />
                      ) : (
                        <div onClick={() => { setEditingVolumeId(book.id); setTempVolume(book.volume?.toString() || ''); }} className="cursor-pointer p-2 hover:bg-[#0369a1]/5 rounded-xl text-[16px] font-black text-[#1a1a1a]">
                          {book.volume !== null ? t('book.volume', { volume: book.volume }) : <Hash size={14} className="mx-auto text-slate-200" />}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-6">
                      {editingAuthorId === book.id ? (
                        <input
                          autoFocus
                          type="text"
                          value={tempAuthor}
                          onChange={e => setTempAuthor(e.target.value)}
                          onKeyDown={e => {
                            if (e.key === 'Enter') handleSaveAuthor(book.id, tempAuthor);
                            if (e.key === 'Escape') setEditingAuthorId(null);
                          }}
                          className="px-3 py-2 border-2 border-[#0369a1] rounded-xl bg-white w-full outline-none"
                        />
                      ) : (
                        <div onClick={() => { setEditingAuthorId(book.id); setTempAuthor(book.author || ''); }} className="cursor-pointer p-2 hover:bg-[#0369a1]/5 rounded-xl text-[16px] font-normal text-[#1a1a1a]">
                          {book.author || <User size={14} className="text-slate-200" />}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-6">
                      <TagEditor
                        isOpen={editingCategoriesId === book.id}
                        onOpen={() => { setEditingCategoriesId(book.id); setEditingCategoriesList(book.categories || []); setTempCategory(''); }}
                        onClose={() => setEditingCategoriesId(null)}
                        onSave={() => handleSaveCategories(book.id, editingCategoriesList)}
                        items={editingCategoriesList}
                        tempValue={tempCategory}
                        onTempValueChange={setTempCategory}
                        onAddItem={(val) => { if (val && !editingCategoriesList.includes(val)) setEditingCategoriesList(prev => [...prev, val]); setTempCategory(''); }}
                        onRemoveItem={(idx) => setEditingCategoriesList(prev => prev.filter((_, i) => i !== idx))}
                        existingItems={book.categories || []}
                        placeholder={t('admin.categories.add')}
                      />
                    </td>
                    <td className="px-6 py-6">
                      <div className="flex flex-col gap-2 min-w-[120px]">
                        <ProgressBar book={book} />
                        <div className="flex justify-between text-[12px] text-slate-400">
                          <span>{book.completedCount || book.pages.filter(p => p.status === 'completed').length}/{book.totalPages}</span>
                          <span className="uppercase">{book.status}</span>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-6 text-left">
                      <div className="relative" ref={activeMenuId === book.id ? menuRef : null}>
                        <button onClick={() => setActiveMenuId(activeMenuId === book.id ? null : book.id)} className="p-2 hover:bg-[#0369a1]/10 rounded-lg text-slate-400 transition-all"><MoreVertical size={20} /></button>
                        {activeMenuId === book.id && <ActionMenu book={book} close={() => setActiveMenuId(null)} />}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="bg-[#0369a1]/5 px-6 py-4">
            <Pagination page={page} pageSize={pageSize} totalItems={totalBooks} onPageChange={setPage} onPageSizeChange={setPageSize} />
          </div>
        </div>
      )}
    </div>
  );
};
