/** Strips markdown ref-links, bare (ref:...) fragments, and BookID fragments from
 * shareable text — keeps the visible label of `[text](ref:...)` links, drops
 * everything else that's an internal reference artifact, not meant for readers. */
export const cleanShareText = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/\[([^\]]+)\]\(ref:[^)]+\)/g, '$1')
    .replace(/\(ref:[^)]+\)/g, '')
    .replace(/\s*\(?BookID:\s*[a-zA-Z0-9-]+\)?/gi, '')
    .trim();
};

export interface SafeTweetInput {
  /** Fixed short lines before the content line (already formatted, e.g. `سوئال: ${q}`);
   * '' entries are dropped. Capped to 80 chars (last-space-safe) if truncation is needed. */
  headLines: string[];
  /** Prepended to the (possibly truncated) content text, e.g. 'زېرەكچاق: ' or '"'. */
  contentPrefix: string;
  /** The long free-text line that gets binary-searched down when the tweet doesn't fit. */
  contentText: string;
  /** Appended after the (possibly truncated) content text, e.g. closing '"'. */
  contentSuffix?: string;
  /** Fixed lines after the content line (source, footer); '' entries dropped, never shrunk. */
  tailLines: string[];
  /** Real single-encoded URL length budget. Default 10000 — comfortably under
   * browser/server URL-length limits, generous enough for multi-citation RAG answers. */
  maxUrlLength?: number;
}

const capHeadLine = (line: string): string => {
  if (line.length <= 80) return line;
  const truncated = line.slice(0, 80);
  const lastSpace = truncated.lastIndexOf(' ');
  return (lastSpace > 50 ? truncated.slice(0, lastSpace) : truncated).trim() + '…';
};

export const buildSafeTweetText = ({
  headLines,
  contentPrefix,
  contentText,
  contentSuffix = '',
  tailLines,
  maxUrlLength = 10000,
}: SafeTweetInput): string => {
  const join = (head: string[], content: string) => {
    const contentLine = content ? `${contentPrefix}${content}${contentSuffix}` : '';
    return [...head, contentLine, ...tailLines].filter(Boolean).join('\n\n');
  };

  const fullText = join(headLines, contentText);
  const fullUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(fullText)}`;
  if (fullUrl.length <= maxUrlLength) {
    return fullText;
  }

  const cappedHeadLines = headLines.map(capHeadLine);

  let low = 0;
  let high = contentText.length;
  let bestText = join(cappedHeadLines, contentText);

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const rawSub = contentText.slice(0, mid);
    const lastSpace = rawSub.lastIndexOf(' ');
    const candContent =
      (lastSpace > mid * 0.6 ? rawSub.slice(0, lastSpace) : rawSub).trim() +
      (mid < contentText.length ? '…' : '');

    const candText = join(cappedHeadLines, candContent);
    const candUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(candText)}`;

    if (candUrl.length <= maxUrlLength) {
      bestText = candText;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return bestText;
};
