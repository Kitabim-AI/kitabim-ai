import React from 'react';
import { SpellIssue } from '../../hooks/useSpellCheck';

interface HighlightedTextProps {
  text: string;
  issues: SpellIssue[];
  className?: string;
  style?: React.CSSProperties;
  isLayer?: boolean;
}

export const HighlightedText: React.FC<HighlightedTextProps> = ({
  text,
  issues,
  className = '',
  style = {},
  isLayer = false,
}) => {
  if (!issues || issues.length === 0) {
    return (
      <div className={`${className} ${isLayer ? 'text-transparent select-none' : ''}`} style={style} dir="rtl">
        {text}
      </div>
    );
  }

  // Find all occurrences of each unknown word in the text (word-based search,
  // since text may have been edited after offsets were computed)
  const errorPositions: { start: number; end: number; word: string }[] = [];

  issues.forEach((issue) => {
    let searchPos = 0;
    while (searchPos < text.length) {
      const pos = text.indexOf(issue.word, searchPos);
      if (pos === -1) break;
      errorPositions.push({ start: pos, end: pos + issue.word.length, word: issue.word });
      searchPos = pos + 1;
    }
  });

  errorPositions.sort((a, b) => a.start - b.start);

  const segments: Array<{ text: string; isError: boolean; word?: string }> = [];
  let lastPos = 0;

  errorPositions.forEach(({ start, end, word }) => {
    if (start > lastPos) {
      segments.push({ text: text.substring(lastPos, start), isError: false });
    }
    segments.push({ text: text.substring(start, end), isError: true, word });
    lastPos = end;
  });

  if (lastPos < text.length) {
    segments.push({ text: text.substring(lastPos), isError: false });
  }

  return (
    <div className={`${className} ${isLayer ? 'text-transparent select-none' : ''}`} style={style} dir="rtl">
      {segments.map((segment, idx) => (
        <span
          key={idx}
          className={
            segment.isError
              ? 'underline decoration-wavy decoration-red-500 decoration-2 cursor-pointer hover:bg-red-50 rounded px-0.5'
              : ''
          }
          style={segment.isError && isLayer ? { color: 'transparent', textDecorationColor: '#ef4444' } : {}}
          title={segment.word}
        >
          {segment.text}
        </span>
      ))}
    </div>
  );
};
