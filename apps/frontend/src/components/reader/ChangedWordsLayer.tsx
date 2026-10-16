import React from 'react';
import { ChangedRange } from '../../utils/wordDiff';

interface ChangedWordsLayerProps {
  text: string;
  ranges: ChangedRange[];
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Renders `text` invisibly, with a background behind each changed word, so it
 * can sit underneath a transparent textarea with identical typography and
 * show which words an LLM spell check changed.
 */
export const ChangedWordsLayer = React.forwardRef<HTMLDivElement, ChangedWordsLayerProps>(
  ({ text, ranges, className = '', style }, ref) => {
    const segments: React.ReactNode[] = [];
    let last = 0;
    ranges.forEach((r, idx) => {
      if (r.start > last) segments.push(<span key={`t${idx}`}>{text.slice(last, r.start)}</span>);
      segments.push(
        <mark
          key={`m${idx}`}
          data-testid="llm-changed-word"
          className="bg-amber-300/70 dark:bg-amber-500/40 text-transparent rounded-sm"
        >
          {text.slice(r.start, r.end)}
        </mark>
      );
      last = r.end;
    });
    if (last < text.length) segments.push(<span key="tail">{text.slice(last)}</span>);

    return (
      <div
        ref={ref}
        aria-hidden="true"
        dir="rtl"
        className={`absolute inset-0 overflow-hidden whitespace-pre-wrap break-words text-transparent pointer-events-none select-none ${className}`}
        style={style}
      >
        {segments}
        {'\n'}
      </div>
    );
  }
);
ChangedWordsLayer.displayName = 'ChangedWordsLayer';
