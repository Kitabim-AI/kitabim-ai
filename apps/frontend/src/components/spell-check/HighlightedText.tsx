import React from 'react';
import { SpellCorrection } from './SpellCheckPanel';

interface HighlightedTextProps {
  text: string;
  corrections: SpellCorrection[];
  className?: string;
  style?: React.CSSProperties;
  isLayer?: boolean;
}

export const HighlightedText: React.FC<HighlightedTextProps> = ({
  text,
  corrections,
  className = '',
  style = {},
  isLayer = false,
}) => {
  if (!corrections || corrections.length === 0) {
    return (
      <div className={`${className} ${isLayer ? 'text-transparent select-none' : ''}`} style={style} dir="rtl">
        {text}
      </div>
    );
  }

  // Create a map of positions where errors occur
  const errorPositions: { start: number; end: number; correction: SpellCorrection }[] = [];

  corrections.forEach((correction) => {
    let searchPos = 0;
    while (searchPos < text.length) {
      const pos = text.indexOf(correction.original, searchPos);
      if (pos === -1) break;

      errorPositions.push({
        start: pos,
        end: pos + correction.original.length,
        correction,
      });

      searchPos = pos + 1;
    }
  });

  // Sort by start position
  errorPositions.sort((a, b) => a.start - b.start);

  // Build segments
  const segments: Array<{ text: string; isError: boolean; correction?: SpellCorrection }> = [];
  let lastPos = 0;

  errorPositions.forEach(({ start, end, correction }) => {
    // Add normal text before error
    if (start > lastPos) {
      segments.push({
        text: text.substring(lastPos, start),
        isError: false,
      });
    }

    // Add error text
    segments.push({
      text: text.substring(start, end),
      isError: true,
      correction,
    });

    lastPos = end;
  });

  // Add remaining text
  if (lastPos < text.length) {
    segments.push({
      text: text.substring(lastPos),
      isError: false,
    });
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
          title={segment.correction?.reason}
        >
          {segment.text}
        </span>
      ))}
    </div>
  );
};
