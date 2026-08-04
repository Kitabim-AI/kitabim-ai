import React from 'react';

export const highlightText = (text: string, query: string): React.ReactNode => {
  const trimmed = query.trim();
  if (!trimmed) return text;

  try {
    const escaped = trimmed.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
    return parts.map((part, index) =>
      part.toLowerCase() === trimmed.toLowerCase() ? (
        <mark
          key={index}
          className="bg-amber-200/90 dark:bg-amber-500/30 text-[#1a1a1a] dark:text-amber-200 font-semibold px-1 py-0.5 rounded shadow-sm"
        >
          {part}
        </mark>
      ) : (
        part
      )
    );
  } catch {
    return text;
  }
};
