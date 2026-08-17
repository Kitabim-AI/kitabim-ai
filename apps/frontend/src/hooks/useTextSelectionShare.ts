import { RefObject, useEffect, useState } from 'react';

export interface TextSelectionShare {
  text: string;
  top: number;
  left: number;
}

/**
 * Tracks the current text selection, returning its trimmed text and viewport
 * coordinates whenever the selection is non-empty and fully contained within
 * containerRef — used to show a "share this quote" popover near the
 * selection. Returns null otherwise (no selection, or selection outside the
 * container).
 */
export function useTextSelectionShare(
  containerRef: RefObject<HTMLElement | null>
): TextSelectionShare | null {
  const [selection, setSelection] = useState<TextSelectionShare | null>(null);

  useEffect(() => {
    const handleSelectionChange = () => {
      const sel = window.getSelection();
      const container = containerRef.current;

      if (!sel || sel.isCollapsed || sel.rangeCount === 0 || !container) {
        setSelection(null);
        return;
      }

      const range = sel.getRangeAt(0);
      if (!container.contains(range.commonAncestorContainer)) {
        setSelection(null);
        return;
      }

      const text = sel.toString().trim();
      if (!text) {
        setSelection(null);
        return;
      }

      const rect = range.getBoundingClientRect();
      setSelection({ text, top: rect.top, left: rect.left + rect.width / 2 });
    };

    document.addEventListener('selectionchange', handleSelectionChange);
    return () => document.removeEventListener('selectionchange', handleSelectionChange);
  }, [containerRef]);

  return selection;
}
