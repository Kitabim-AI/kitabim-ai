import React from 'react';
import { Book } from '@shared/types';

interface ProgressBarProps {
  book: Book;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ book }) => {
  // Count pages that have completed OCR (either ocr_done or fully indexed)
  const completedPages = book.ocrDoneCount || book.pages?.filter(p => p.status === 'ocr_done' || p.status === 'chunked' || p.status === 'indexed').length || 0;
  const percent = (completedPages / (book.totalPages || 1)) * 100;

  // Use v2 pipeline step for color when available, fall back to v1 status
  let color: string;
  let bgColor: string = 'bg-[#0369a1]/20';

  if (book.v2PipelineStep) {
    if (book.v2PipelineStep === 'ready') {
      color = 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]';
      bgColor = 'bg-emerald-100/80';
    } else if (book.v2PipelineStep === 'embedding') {
      color = 'bg-purple-500 animate-pulse shadow-[0_0_6px_rgba(168,85,247,0.3)]';
      bgColor = 'bg-purple-100/80';
    } else if (book.v2PipelineStep === 'chunking') {
      color = 'bg-indigo-500 animate-pulse shadow-[0_0_6px_rgba(99,102,241,0.3)]';
      bgColor = 'bg-indigo-100/80';
    } else if (book.v2PipelineStep === 'ocr') {
      color = 'bg-blue-500 animate-pulse shadow-[0_0_6px_rgba(59,130,246,0.3)]';
      bgColor = 'bg-blue-100/80';
    } else {
      color = 'bg-slate-400';
      bgColor = 'bg-slate-200';
    }
  } else if (book.status === 'error') {
    color = 'bg-red-500';
    bgColor = 'bg-red-100/80';
  } else if (book.status === 'ready') {
    color = 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]';
    bgColor = 'bg-emerald-100/80';
  } else if (book.status === 'ocr_done') {
    color = 'bg-indigo-500 shadow-[0_0_6px_rgba(99,102,241,0.3)]';
    bgColor = 'bg-indigo-100/80';
  } else if (book.status === 'indexing') {
    color = 'bg-purple-500 animate-pulse shadow-[0_0_6px_rgba(168,85,247,0.3)]';
    bgColor = 'bg-purple-100/80';
  } else if (book.status === 'ocr_processing') {
    color = 'bg-blue-500 animate-pulse shadow-[0_0_6px_rgba(59,130,246,0.3)]';
    bgColor = 'bg-blue-100/80';
  } else if (book.status === 'pending') {
    color = 'bg-yellow-500';
    bgColor = 'bg-yellow-100/80';
  } else {
    color = 'bg-slate-400';
    bgColor = 'bg-slate-200';
  }

  return (
    <div className={`w-full h-1.5 rounded-full overflow-hidden ${bgColor}`}>
      <div className={`h-full transition-all duration-500 ${color}`} style={{ width: `${percent}%` }} />
    </div>
  );
};
