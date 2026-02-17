import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

interface PaginationProps {
  page: number;
  pageSize: number;
  totalItems: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
  page,
  pageSize,
  totalItems,
  onPageChange,
  onPageSizeChange,
}) => {
  const { t } = useI18n();
  const totalPages = Math.ceil(totalItems / pageSize);

  return (
    <div className="px-8 py-5 border-t border-[#75C5F0]/10 flex items-center justify-between" dir="rtl">
      <div className="flex items-center gap-3">
        <span className="text-[14px] font-black text-slate-400 uppercase tracking-widest">{t('pagination.showingLabel')}</span>
        <select
          value={pageSize}
          onChange={(e) => {
            onPageSizeChange(Number(e.target.value));
          }}
          className="bg-white/50 backdrop-blur-md border border-[#75C5F0]/20 rounded-xl px-3 py-1.5 text-sm font-black outline-none focus:ring-4 focus:ring-[#75C5F0]/5 text-[#1a1a1a] cursor-pointer hover:bg-white transition-all shadow-sm"
        >
          <option value={5}>5</option>
          <option value={10}>10</option>
          <option value={20}>20</option>
          <option value={50}>50</option>
        </select>
      </div>

      <div className="flex items-center gap-8">
        <span className="text-[14px] font-black text-slate-400 uppercase tracking-widest">
          {t('admin.users.pagination', {
            total: totalItems,
            start: ((page - 1) * pageSize) + 1,
            end: Math.min(page * pageSize, totalItems)
          })}
        </span>
        <div className="flex items-center gap-2">
          <button
            disabled={page === 1}
            onClick={() => onPageChange(page - 1)}
            className="p-2 rounded-xl bg-white/50 border border-[#75C5F0]/10 hover:bg-[#e8f4f8] hover:text-[#75C5F0] disabled:opacity-20 transition-all text-[#1a1a1a] shadow-sm active:scale-95"
          >
            <ChevronRight size={18} strokeWidth={3} />
          </button>

          <div className="flex items-center gap-1.5">
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
              .map((p, i, arr) => (
                <React.Fragment key={p}>
                  {i > 0 && arr[i - 1] !== p - 1 && <span className="px-2 text-slate-300 font-black">...</span>}
                  <button
                    onClick={() => onPageChange(p)}
                    className={`min-w-[36px] h-9 rounded-xl text-sm font-black transition-all active:scale-90 ${page === p ? 'bg-[#75C5F0] text-white shadow-lg shadow-[#75C5F0]/30' : 'bg-white/50 text-[#1a1a1a] hover:bg-[#e8f4f8] border border-[#75C5F0]/10'}`}
                  >
                    {p}
                  </button>
                </React.Fragment>
              ))}
          </div>

          <button
            disabled={page * pageSize >= totalItems}
            onClick={() => onPageChange(page + 1)}
            className="p-2 rounded-xl bg-white/50 border border-[#75C5F0]/10 hover:bg-[#e8f4f8] hover:text-[#75C5F0] disabled:opacity-20 transition-all text-[#1a1a1a] shadow-sm active:scale-95"
          >
            <ChevronLeft size={18} strokeWidth={3} />
          </button>
        </div>
      </div>
    </div>
  );
};
