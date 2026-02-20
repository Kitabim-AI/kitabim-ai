import React, { useEffect, useState } from 'react';
import { X, BookOpen, Clock, User, HardDrive, Loader2 } from 'lucide-react';
import { PersistenceService } from '../../services/persistenceService';
import { MarkdownContent } from '../common/MarkdownContent';
import { useI18n } from '../../i18n/I18nContext';

interface ReferenceModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookId: string;
  pageNumber: number;
}

export const ReferenceModal: React.FC<ReferenceModalProps> = ({
  isOpen,
  onClose,
  bookId,
  pageNumber,
}) => {
  const { t } = useI18n();
  const [pageData, setPageData] = useState<any | null>(null);
  const [bookData, setBookData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen && bookId && pageNumber) {
      setLoading(true);
      Promise.all([
        PersistenceService.getPage(bookId, pageNumber),
        PersistenceService.getBookById(bookId)
      ]).then(([page, book]) => {
        setPageData(page);
        setBookData(book);
        setLoading(false);
      }).catch(err => {
        console.error("Failed to fetch reference data:", err);
        setLoading(false);
      });
    }
  }, [isOpen, bookId, pageNumber]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center p-4 md:p-8" dir="rtl" lang="ug">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in transition-all duration-500"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="bg-white/90 backdrop-blur-2xl rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.3)] w-full max-w-4xl max-h-[90vh] relative z-10 overflow-hidden animate-scale-up border border-white/40 flex flex-col">

        {/* Header */}
        <div className="p-8 pb-6 border-b border-slate-100 flex items-start justify-between bg-white/50">
          <div className="flex items-center gap-6">
            <div className="p-4 bg-[#0369a1] text-white rounded-[24px] shadow-xl shadow-[#0369a1]/20">
              <BookOpen size={28} strokeWidth={2.5} />
            </div>
            <div>
              <h3 className="text-2xl font-normal text-[#1a1a1a] mb-2 leading-tight">
                {loading ? t('common.loading') : (bookData?.title || t('chat.referenceTitle'))}
              </h3>
              <div className="flex items-center gap-4 text-[#94a3b8] text-sm font-normal uppercase tracking-wider">
                <span className="flex items-center gap-1.5 px-3 py-1 bg-[#0369a1]/10 text-[#0369a1] rounded-full">
                  {t('chat.pageNumber', { page: pageNumber })}
                </span>
                {bookData?.author && (
                  <span className="flex items-center gap-1.5">
                    <User size={14} />
                    {bookData.author}
                  </span>
                )}
                {bookData?.volume && (
                  <span className="flex items-center gap-1.5">
                    {t('common.volume')}: {bookData.volume}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-3 hover:bg-red-50 text-slate-300 hover:text-red-500 rounded-2xl transition-all active:scale-95 group"
          >
            <X size={28} strokeWidth={3} />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-grow overflow-y-auto p-10 custom-scrollbar bg-[#f8fafc]/30">
          {loading ? (
            <div className="h-64 flex flex-col items-center justify-center gap-6 opacity-40">
              <Loader2 size={48} className="animate-spin text-[#0369a1]" />
              <p className="text-lg text-slate-400 font-normal uppercase tracking-widest">{t('common.loading')}</p>
            </div>
          ) : pageData?.text ? (
            <div className="max-w-3xl mx-auto">
              <div className="bg-white/80 p-10 rounded-[32px] shadow-sm border border-white relative overflow-hidden group">
                {/* Cultural motif background */}
                <div className="absolute top-0 right-0 w-32 h-32 bg-[#0369a1]/5 rounded-bl-[100px] -mr-10 -mt-10 transition-transform group-hover:scale-110 duration-700" />

                <MarkdownContent
                  content={pageData.text}
                  className="text-lg leading-[2] text-[#1e293b] relative z-10"
                />
              </div>
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center gap-4 opacity-40">
              <HardDrive size={48} className="text-slate-300" />
              <p className="text-lg text-slate-400 font-normal">{t('chat.noContentFound')}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 px-10 bg-white/50 border-t border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-6 text-[13px] text-slate-400 font-normal">
            <div className="flex items-center gap-2">
              <Clock size={14} />
              {t('common.lastUpdated')}: {bookData?.lastUpdated ? new Date(bookData.lastUpdated).toLocaleDateString() : '-'}
            </div>
          </div>
          <button
            onClick={onClose}
            className="px-8 py-3 bg-slate-900 hover:bg-slate-800 text-white rounded-2xl text-sm font-normal transition-all active:scale-95 shadow-lg shadow-black/10 uppercase tracking-widest"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );
};
