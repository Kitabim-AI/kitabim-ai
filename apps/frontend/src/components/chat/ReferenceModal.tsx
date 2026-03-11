import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, BookOpen, Clock, User, HardDrive, Loader2 } from 'lucide-react';
import { PersistenceService } from '../../services/persistenceService';
import { MarkdownContent } from '../common/MarkdownContent';
import { useI18n } from '../../i18n/I18nContext';

interface ReferenceModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookId: string;
  pageNumbers: number[];
}

export const ReferenceModal: React.FC<ReferenceModalProps> = ({
  isOpen,
  onClose,
  bookId,
  pageNumbers,
}) => {
  const { t } = useI18n();
  const [pagesData, setPagesData] = useState<any[]>([]);
  const [bookData, setBookData] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && bookId && pageNumbers?.length > 0) {
      setLoading(true);
      Promise.all([
        ...pageNumbers.map(pageNum => PersistenceService.getPage(bookId, pageNum)),
        PersistenceService.getBookById(bookId)
      ]).then(results => {
        const pages = results.slice(0, -1);
        const book = results[results.length - 1];
        setPagesData(pages);
        setBookData(book);
        setLoading(false);
      }).catch(err => {
        console.error("Failed to fetch reference data:", err);
        setLoading(false);
      });
    }
  }, [isOpen, bookId, pageNumbers]);

  if (!isOpen) return null;

  const modalContent = (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-2 sm:p-4 md:p-8" dir="rtl" lang="ug">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl animate-fade-in transition-all duration-500"
        onClick={onClose}
      />

      {/* Modal Container */}
      <div className="bg-white/90 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] md:rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.3)] w-full max-w-4xl max-h-[95vh] sm:max-h-[90vh] relative z-10 overflow-hidden animate-scale-up border border-white/40 flex flex-col">

        {/* Header */}
        <div className="p-4 pb-3 sm:p-6 sm:pb-4 md:p-8 md:pb-6 border-b border-slate-100 flex items-start justify-between bg-white/50">
          <div className="flex items-center gap-3 sm:gap-4 md:gap-6">
            <div className="p-2.5 sm:p-3 md:p-4 bg-[#0369a1] text-white rounded-2xl sm:rounded-[24px] shadow-xl shadow-[#0369a1]/20 shrink-0">
              <BookOpen size={20} strokeWidth={2.5} className="sm:hidden" />
              <BookOpen size={28} strokeWidth={2.5} className="hidden sm:block" />
            </div>
            <div>
              <h3 className="text-xl sm:text-2xl font-normal text-[#1a1a1a] mb-2 leading-tight flex items-center flex-wrap gap-2 text-right">
                {loading ? t('common.loading') : (
                  <>
                    <span>{bookData?.title || t('chat.referenceTitle')}</span>
                    {bookData?.author && (
                      <span className="text-base sm:text-lg text-slate-400 font-normal">
                        ({bookData.author})
                      </span>
                    )}
                  </>
                )}
              </h3>
              <div className="flex items-center gap-4 text-[#94a3b8] text-sm font-normal uppercase tracking-wider">
                <span className="flex items-center gap-1.5 px-3 py-1 bg-[#0369a1]/10 text-[#0369a1] rounded-full">
                  {pageNumbers?.map(p => t('chat.pageNumber', { page: p })).join('، ')}
                </span>
                {bookData?.volume && (
                  <span className="flex items-center gap-1.5 px-3 py-1 bg-slate-100 text-slate-600 rounded-full text-xs">
                    {t('book.volume', { volume: bookData.volume })}
                  </span>
                )}
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 sm:p-3 hover:bg-red-50 text-slate-300 hover:text-red-500 rounded-2xl transition-all active:scale-95 group shrink-0"
          >
            <X size={20} strokeWidth={3} className="sm:hidden" />
            <X size={28} strokeWidth={3} className="hidden sm:block" />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-grow overflow-y-auto p-4 sm:p-6 md:p-10 custom-scrollbar bg-[#f8fafc]/30">
          {loading ? (
            <div className="h-64 flex flex-col items-center justify-center gap-6 opacity-40">
              <Loader2 size={48} className="animate-spin text-[#0369a1]" />
              <p className="text-sm text-slate-400 font-normal uppercase tracking-widest">{t('common.loading')}</p>
            </div>
          ) : pagesData.length > 0 && pagesData.some(p => p?.text) ? (
            <div className="max-w-3xl mx-auto space-y-6">
              {pagesData.map((pageData, index) => {
                const pageNum = pageNumbers[index];
                if (!pageData?.text) return null;
                return (
                  <div key={`page-${pageNum}`} className="bg-white/80 p-4 pt-8 sm:p-6 sm:pt-10 md:p-10 md:pt-12 rounded-[20px] sm:rounded-[24px] md:rounded-[32px] shadow-sm border border-white relative overflow-hidden group">
                    {pageNumbers.length > 1 && (
                      <div className="absolute top-0 right-0 bg-[#0369a1] text-white px-4 py-1.5 rounded-bl-[24px] text-sm font-normal shadow-sm z-20 opacity-80 backdrop-blur-md">
                        {t('chat.pageNumber', { page: pageNum })}
                      </div>
                    )}
                    {/* Cultural motif background */}
                    <div className="absolute top-0 right-0 w-32 h-32 bg-[#0369a1]/5 rounded-bl-[100px] -mr-10 -mt-10 transition-transform group-hover:scale-110 duration-700" />

                    <MarkdownContent
                      content={pageData.text}
                      className="text-base sm:text-lg leading-[2] text-[#1e293b] relative z-10"
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="h-64 flex flex-col items-center justify-center text-center gap-4 opacity-40">
              <HardDrive size={48} className="text-slate-300" />
              <p className="text-sm sm:text-base text-slate-400 font-normal">{t('chat.noContentFound')}</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 px-4 sm:p-4 sm:px-6 md:p-6 md:px-10 bg-white/50 border-t border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3 sm:gap-6 text-xs text-slate-400 font-normal">
            <div className="flex items-center gap-2">
              <Clock size={14} />
              {t('common.lastUpdated')}: {bookData?.lastUpdated ? new Date(bookData.lastUpdated).toLocaleDateString() : '-'}
            </div>
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 sm:px-6 sm:py-2.5 md:px-8 md:py-3 bg-slate-900 hover:bg-slate-800 text-white rounded-2xl text-sm font-normal transition-all active:scale-95 shadow-lg shadow-black/10 uppercase tracking-widest"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};
