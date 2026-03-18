import React from 'react';
import { Book } from '@shared/types';
import { PIPELINE_STEP } from '../../constants/milestones';

interface ProgressBarProps {
  book: Book;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({ book }) => {
  // Count pages that have completed the current pipeline step
  const getCompletedCount = () => {
    if (book.pipelineStep && book.pipelineStats) {
      return book.pipelineStep === 'ready'
        ? (book.totalPages || (book as any).total_pages || 0)
        : (book.pipelineStats[book.pipelineStep] || 0);
    }
    return 0;
  };

  const completedPages = getCompletedCount();
  const percent = (completedPages / (book.totalPages || 1)) * 100;

  // Determine status and colors
  const step = book.pipelineStep || (book.status === PIPELINE_STEP.READY ? PIPELINE_STEP.READY : (book.status === PIPELINE_STEP.ERROR ? PIPELINE_STEP.ERROR : null));

  let color: string;
  let bgColor: string = 'bg-[#0369a1]/20';

  if (step === PIPELINE_STEP.READY) {
    color = 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]';
    bgColor = 'bg-emerald-100/80';
  } else if (step === PIPELINE_STEP.EMBEDDING) {
    color = 'bg-orange-500 animate-pulse shadow-[0_0_8px_rgba(249,115,22,0.4)]';
    bgColor = 'bg-orange-100/80';
  } else if (step === PIPELINE_STEP.CHUNKING) {
    color = 'bg-indigo-500 animate-pulse shadow-[0_0_6px_rgba(99,102,241,0.3)]';
    bgColor = 'bg-indigo-100/80';
  } else if (step === PIPELINE_STEP.OCR) {
    color = 'bg-blue-500 animate-pulse shadow-[0_0_6px_rgba(59,130,246,0.3)]';
    bgColor = 'bg-blue-100/80';
  } else if (step === PIPELINE_STEP.ERROR) {
    color = 'bg-red-500';
    bgColor = 'bg-red-100/80';
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
