import { RefObject, useEffect } from 'react';

const HIGHLIGHT_CLASS = 'bg-[#0369a1]/20 dark:bg-[#38bdf8]/30 rounded px-0.5';

interface TextNodeEntry {
  node: Text;
  start: number;
}

const collectTextNodes = (container: HTMLElement): TextNodeEntry[] => {
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  const entries: TextNodeEntry[] = [];
  let offset = 0;
  let node: Node | null;
  while ((node = walker.nextNode())) {
    const textNode = node as Text;
    entries.push({ node: textNode, start: offset });
    offset += textNode.data.length;
  }
  return entries;
};

const findNodeAtOffset = (
  entries: TextNodeEntry[],
  offset: number
): { node: Text; localOffset: number } | null => {
  for (const entry of entries) {
    const end = entry.start + entry.node.data.length;
    if (offset >= entry.start && offset <= end) {
      return { node: entry.node, localOffset: offset - entry.start };
    }
  }
  return null;
};

const wrapMatch = (
  entries: TextNodeEntry[],
  start: { node: Text; localOffset: number },
  end: { node: Text; localOffset: number }
): HTMLElement | null => {
  if (start.node === end.node) {
    const range = document.createRange();
    range.setStart(start.node, start.localOffset);
    range.setEnd(end.node, end.localOffset);
    const mark = document.createElement('mark');
    mark.className = HIGHLIGHT_CLASS;
    range.surroundContents(mark);
    return mark;
  }

  const startIdx = entries.findIndex(e => e.node === start.node);
  const endIdx = entries.findIndex(e => e.node === end.node);
  if (startIdx === -1 || endIdx === -1) return null;

  const firstFragment =
    start.localOffset > 0 ? start.node.splitText(start.localOffset) : start.node;
  if (end.localOffset < end.node.data.length) {
    end.node.splitText(end.localOffset);
  }

  const toWrap: Text[] = [firstFragment];
  for (let i = startIdx + 1; i <= endIdx; i++) {
    toWrap.push(entries[i].node);
  }

  let firstWrapper: HTMLElement | null = null;
  toWrap.forEach(textNode => {
    const wrapper = document.createElement('mark');
    wrapper.className = HIGHLIGHT_CLASS;
    textNode.parentNode?.insertBefore(wrapper, textNode);
    wrapper.appendChild(textNode);
    if (!firstWrapper) firstWrapper = wrapper;
  });

  return firstWrapper;
};

/**
 * Finds an exact substring match of `quote` within `containerRef`'s rendered
 * text and wraps it in a <mark>, scrolling it into view. No-ops (without
 * calling onApplied) until the container is mounted and renderedText is
 * non-empty, so a caller using this to clear "pending highlight" state
 * doesn't clear it before the target page has actually rendered.
 */
export function useQuoteHighlight(
  containerRef: RefObject<HTMLElement | null>,
  quote: string | null | undefined,
  renderedText: string,
  onApplied?: () => void
): void {
  useEffect(() => {
    if (!quote) return;
    const container = containerRef.current;
    if (!container || !renderedText) return;

    const entries = collectTextNodes(container);
    const fullText = entries.map(e => e.node.data).join('');
    const matchIndex = fullText.indexOf(quote);

    if (matchIndex === -1) {
      onApplied?.();
      return;
    }

    const start = findNodeAtOffset(entries, matchIndex);
    const end = findNodeAtOffset(entries, matchIndex + quote.length);
    if (!start || !end) {
      onApplied?.();
      return;
    }

    const mark = wrapMatch(entries, start, end);
    mark?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    onApplied?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef, quote, renderedText, onApplied]);
}
