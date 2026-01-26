import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

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
  const totalPages = Math.ceil(totalItems / pageSize);

  return (
    <div className="px-6 py-4 bg-slate-50 border-t border-slate-200 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500">Show</span>
        <select
          value={pageSize}
          onChange={(e) => {
            onPageSizeChange(Number(e.target.value));
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
          Showing <span className="text-slate-900">{((page - 1) * pageSize) + 1}</span> to <span className="text-slate-900">{Math.min(page * pageSize, totalItems)}</span> of <span className="text-slate-900">{totalItems}</span>
        </span>
        <div className="flex items-center gap-1">
          <button
            disabled={page === 1}
            onClick={() => onPageChange(page - 1)}
            className="p-1.5 rounded-lg hover:bg-slate-200 disabled:opacity-30 transition-colors text-slate-600"
            title="Previous Page"
          >
            <ChevronLeft size={20} />
          </button>

          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
              .map((p, i, arr) => (
                <React.Fragment key={p}>
                  {i > 0 && arr[i - 1] !== p - 1 && <span className="px-1 text-slate-400">...</span>}
                  <button
                    onClick={() => onPageChange(p)}
                    className={`min-w-[32px] h-8 rounded-lg text-sm font-bold transition-all ${page === p ? 'bg-indigo-600 text-white shadow-md shadow-indigo-100' : 'text-slate-600 hover:bg-slate-100'}`}
                  >
                    {p}
                  </button>
                </React.Fragment>
              ))}
          </div>

          <button
            disabled={page * pageSize >= totalItems}
            onClick={() => onPageChange(page + 1)}
            className="p-1.5 rounded-lg hover:bg-slate-200 disabled:opacity-30 transition-colors text-slate-600"
            title="Next Page"
          >
            <ChevronRight size={20} />
          </button>
        </div>
      </div>
    </div>
  );
};
