import React from 'react';

type MarkdownContentProps = {
  content: string;
  className?: string;
  style?: React.CSSProperties;
  onReferenceClick?: (bookId: string, pageNums: number[]) => void;
  contentPageOffset?: number;
  onTocPageClick?: (targetPhysicalPage: number) => void;
  isTocPage?: boolean;
};

export const isTocPageContent = (text: string): boolean => {
  if (!text) return false;

  // 1. Keyword check: "مۇندەرىجە" (Table of contents in Uyghur)
  if (text.includes('مۇندەرىجە')) {
    return true;
  }

  const lines = text
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean);

  if (!lines.length) return false;

  // 2. Dot/leader pattern (Standard TOC style, e.g. "Title ........ 12")
  const dotLeaderPattern = /(?:[.\u00b7\u2022\u2219\u22c5\u2024\ufe52\u3002]\s*){4,}|…{2,}|_{4,}|-{4,}/;
  const dotLeaderCount = lines.filter(line => dotLeaderPattern.test(line)).length;
  if (dotLeaderCount >= 2) {
    return true;
  }

  // 3. Pipe table TOC entries (e.g. "| Title | 12 |")
  const pipeTocPattern = /^\|.*\|\s*[\d\u0660-\u0669\u06F0-\u06F9]+\s*\|?$/;
  const pipeTocCount = lines.filter(line => pipeTocPattern.test(line)).length;
  if (pipeTocCount >= 3 && (pipeTocCount / lines.length) >= 0.3) {
    return true;
  }

  return false;
};

const ARABIC_DIACRITIC_RE = /[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]/;
const ARABIC_SCRIPT_RE = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/;

const shouldUseArabicFont = (text: string) => {
  if (!text || !ARABIC_SCRIPT_RE.test(text)) return false;
  return ARABIC_DIACRITIC_RE.test(text);
};

const applyArabicFontToPlainText = (value: string, keyPrefix: string) => {
  if (!shouldUseArabicFont(value)) return value;
  return (
    <span key={`${keyPrefix}-arabic`} className="arabic-text">
      {value}
    </span>
  );
};

const splitInline = (text: string, regex: RegExp, render: (match: string, group1: string, group2: string | undefined, key: number) => React.ReactNode) => {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let matchIndex = 0;

  const matches = Array.from(text.matchAll(new RegExp(regex, 'g')));

  for (const match of matches) {
    const offset = match.index!;
    if (offset > lastIndex) {
      parts.push(text.slice(lastIndex, offset));
    }
    parts.push(render(match[0], match[1], match[2], matchIndex));
    matchIndex += 1;
    lastIndex = offset + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
};

const applyInline = (
  nodes: React.ReactNode[],
  regex: RegExp,
  render: (match: string, group1: string, group2: string | undefined, key: number) => React.ReactNode
) => nodes.flatMap(node => (typeof node === 'string' ? splitInline(node, regex, render) : [node]));

const renderInline = (text: string, onReferenceClick?: (bookId: string, pageNums: number[]) => void) => {
  let nodes: React.ReactNode[] = [text];

  // Handle markdown links: [text](url)
  nodes = applyInline(nodes, /\[([^\]]+)\]\(([^)]+)\)/, (match, text, url, key) => {
    // If the captured URL is a nested markdown link like [مەنبە](ref:bookId:pages),
    // extract the actual ref: URL from inside it.
    let effectiveUrl = url || '';
    if (!effectiveUrl.startsWith('ref:') && effectiveUrl.includes('ref:')) {
      const nestedRef = effectiveUrl.match(/ref:[\w]+:(?:[\d,:]+|summary)/);
      if (nestedRef) effectiveUrl = nestedRef[0];
    }

    if (effectiveUrl.startsWith('ref:')) {
      const parts = effectiveUrl.split(':');
      const bookId = parts[1];
      let pageNums: number[] = [];
      let isSummaryRef = false;

      if (bookId === 'quran') {
        const surah = parseInt(parts[2], 10);
        if (!isNaN(surah)) {
          pageNums.push(surah);
          if (parts[3]) {
            const ayahs = parts[3].split(',').map(p => parseInt(p.trim(), 10)).filter(p => !isNaN(p));
            pageNums.push(...ayahs);
          }
        }
      } else {
        const pageNumsStr = parts[2] || '';
        isSummaryRef = pageNumsStr === 'summary';
        pageNums = isSummaryRef
          ? []
          : pageNumsStr.split(',').map(p => parseInt(p.trim(), 10)).filter(p => !isNaN(p));
      }

      // Clean up the text in case the LLM included the BookID inside the link name
      const cleanText = text.replace(/\s*\(?BookID:\s*[a-zA-Z0-9-]+\)?/gi, '');

      return (
        <button
          key={`ref-${key}`}
          onClick={(e) => {
            e.preventDefault();
            if (onReferenceClick && bookId && (pageNums.length > 0 || isSummaryRef)) {
              onReferenceClick(bookId, pageNums);
            }
          }}
          className="text-inherit hover:opacity-70 underline decoration-dotted underline-offset-4 font-normal transition-all"
        >
          {cleanText}
        </button>
      );
    }

    return (
      <a
        key={`link-${key}`}
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-inherit hover:opacity-70 underline transition-all"
      >
        {text}
      </a>
    );
  });

  nodes = applyInline(nodes, /`([^`]+)`/, (match, value, _g2, key) => (
    <code key={`code-${key}`} className="px-1 rounded bg-slate-100 text-slate-700 font-mono text-[0.95em]">
      {value}
    </code>
  ));

  nodes = applyInline(nodes, /\*\*([^*]+)\*\*/, (match, value, _g2, key) => (
    <strong key={`bold-${key}`} className="font-bold">
      {value}
    </strong>
  ));

  nodes = applyInline(nodes, /\*([^*]+)\*/, (match, value, _g2, key) => (
    <em key={`italic-${key}`} className="italic">
      {value}
    </em>
  ));

  return nodes.map((node, index) => (
    typeof node === 'string'
      ? applyArabicFontToPlainText(node, `inline-${index}`)
      : node
  ));
};

const renderParagraph = (text: string, key: string, onReferenceClick?: (bookId: string, pageNums: number[]) => void) => {
  const lines = text.split('\n');
  return (
    <p key={key}>
      {lines.map((line, idx) => (
        <React.Fragment key={`${key}-line-${idx}`}>
          {renderInline(line, onReferenceClick)}
          {idx < lines.length - 1 ? <br /> : null}
        </React.Fragment>
      ))}
    </p>
  );
};

const dotLeaderPattern = /(?:[.\u00b7\u2022\u2219\u22c5\u2024\ufe52\u3002]\s*){3,}|…{2,}/;
const isHr = (line: string) => /^(-{3,}|\*{3,}|_{3,})$/.test(line.trim());
const isHeading = (line: string) => /^#{1,6}(\s+|$|[^\s#])/.test(line.trim());
const isQuote = (line: string) => /^\s*>\s?/.test(line);
const isOrderedList = (line: string) => /^\s*\d+[.)]\s+/.test(line);
const isArabicScriptChar = (value: string) => /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/.test(value);
const isUnorderedList = (line: string) => {
  if (/^\s*•\s+/.test(line)) return true;
  if (/^\s*[*+]\s+/.test(line)) return true;
  if (/^\s*-\s+/.test(line)) {
    const afterDash = line.replace(/^\s*-\s+/, '');
    const firstChar = afterDash.trimStart().charAt(0);
    if (firstChar && isArabicScriptChar(firstChar)) return false;
    return true;
  }
  return false;
};
const isTocLine = (line: string) => {
  const trimmed = line.trim();
  if (!trimmed) return false;
  if (dotLeaderPattern.test(trimmed)) return true;

  const clean = trimmed.replace(/^\s*[*+\-•]\s*/, '');

  if (/^[\d\u0660-\u0669\u06F0-\u06F9]{1,4}\s+[\u0600-\u06FF\w]/.test(clean)) {
    return true;
  }

  if (/[\u0600-\u06FF\w].{2,}\s+[\d\u0660-\u0669\u06F0-\u06F9]{1,4}$/.test(clean)) {
    return true;
  }

  return false;
};

const parseDigitString = (str: string): number | null => {
  if (!str) return null;
  const clean = str.trim().replace(/^[\s.:\-–—]+|[\s.:\-–—]+$/g, '');
  const normalized = clean
    .replace(/[\u0660-\u0669]/g, d => String(d.charCodeAt(0) - 0x0660))
    .replace(/[\u06F0-\u06F9]/g, d => String(d.charCodeAt(0) - 0x06F0));
  if (!/^\d+$/.test(normalized)) return null;
  const num = parseInt(normalized, 10);
  return isNaN(num) || num <= 0 ? null : num;
};

const extractTocPageNumber = (line: string): number | null => {
  const clean = line.replace(/^\s*[*+\-•]\s*/, '').trim();

  const endMatch = clean.match(/([\d\u0660-\u0669\u06F0-\u06F9]+)\s*$/);
  if (endMatch) {
    const num = parseDigitString(endMatch[1]);
    if (num !== null) return num;
  }

  const afterLeaderMatch = clean.match(/(?:[.\u00b7\u2022\u2219\u22c5\u2024\ufe52\u3002…]{2,})\s*([\d\u0660-\u0669\u06F0-\u06F9]+)/);
  if (afterLeaderMatch) {
    const num = parseDigitString(afterLeaderMatch[1]);
    if (num !== null) return num;
  }

  const startMatch = clean.match(/^([\d\u0660-\u0669\u06F0-\u06F9]+)/);
  if (startMatch) {
    const rest = clean.slice(startMatch[0].length);
    if (/^\s*[.\-:،](?![.\-:،])\s*\D/.test(rest)) {
      return null;
    }
    const num = parseDigitString(startMatch[1]);
    if (num !== null) return num;
  }

  return null;
};

const extractRowPageNumber = (row: string[]): number | null => {
  if (!row || row.length === 0) return null;
  for (let idx = row.length - 1; idx >= 0; idx--) {
    const num = parseDigitString(row[idx]);
    if (num !== null && num > 0 && num < 5000) {
      return num;
    }
  }
  for (let idx = row.length - 1; idx >= 0; idx--) {
    const num = extractTocPageNumber(row[idx]);
    if (num !== null && num > 0 && num < 5000) {
      return num;
    }
  }
  return null;
};

const isTableRow = (line: string) => /^\s*\|/.test(line);
const isTableSeparator = (line: string) => /^\s*\|[\s|:=-]+\|?\s*$/.test(line);
const isBlockStart = (line: string, isToc: boolean = false) =>
  isHr(line) || isHeading(line) || isQuote(line) || (isToc && isTocLine(line)) || isOrderedList(line) || isUnorderedList(line) || isTableRow(line);

export const MarkdownContent: React.FC<MarkdownContentProps> = React.memo(({ content, className, style, onReferenceClick, contentPageOffset, onTocPageClick, isTocPage }) => {
  const effectiveIsTocPage = isTocPage !== undefined ? isTocPage : isTocPageContent(content);
  const normalized = (content || '').replace(/\\n/g, '\n').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines = normalized
    .split('\n')
    .map(line => line.replace(/\[(Header|Footer)\]/g, '').trim())
    .filter(line => {
      if (!line) return false;
      // Allow lines that contain text OR start with markdown block markers (including table rows/separators)
      return /[A-Za-z\u0600-\u06FF]/.test(line) || isBlockStart(line, effectiveIsTocPage) || isTableSeparator(line);
    });
  const blocks: React.ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (isHr(line)) {
      blocks.push(<hr key={`hr-${key++}`} className="border-slate-200" />);
      i += 1;
      continue;
    }

    if (effectiveIsTocPage && isTocLine(line)) {
      const tocLines: string[] = [];
      while (i < lines.length && lines[i].trim() && isTocLine(lines[i])) {
        tocLines.push(lines[i]);
        i += 1;
      }

      const isPageNumberLine = (value: string) => {
        const stripped = value.replace(/\s+/g, '');
        if (!stripped) return false;
        // Keep only digits and dot-leader glyphs.
        return /^[\d\u0660-\u0669]+[.\u00b7\u2022\u2219\u22c5\u2024\ufe52\u3002…]*$/.test(stripped);
      };

      const mergedLines: string[] = [];
      for (const tocLine of tocLines) {
        if (isPageNumberLine(tocLine) && mergedLines.length > 0) {
          mergedLines[mergedLines.length - 1] = `${mergedLines[mergedLines.length - 1]} ${tocLine}`.trim();
        } else {
          mergedLines.push(tocLine);
        }
      }

      const hasOffset = effectiveIsTocPage && contentPageOffset !== undefined && contentPageOffset !== null && contentPageOffset > 0;

      blocks.push(
        <div key={`toc-${key++}`} className="space-y-1 whitespace-pre-wrap tabular-nums">
          {mergedLines.map((tocLine, idx) => {
            const contentPageNum = hasOffset ? extractTocPageNumber(tocLine) : null;
            const targetPhysicalPage = (contentPageNum !== null && hasOffset && contentPageOffset) ? contentPageNum + contentPageOffset : null;
            const cleanDisplay = tocLine.replace(/^\s*[*+\-•]\s*/, '');

            if (targetPhysicalPage !== null && (onTocPageClick || onReferenceClick)) {
              return (
                <button
                  key={`toc-${key}-line-${idx}`}
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    if (onTocPageClick) {
                      onTocPageClick(targetPhysicalPage);
                    } else if (onReferenceClick) {
                      onReferenceClick('', [targetPhysicalPage]);
                    }
                  }}
                  className="w-full text-left rtl:text-right text-[#0369a1] dark:text-[#38bdf8] hover:underline cursor-pointer transition-colors block py-0.5 px-1 -mx-1 rounded hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 group"
                >
                  <span className="group-hover:opacity-90">{cleanDisplay}</span>
                </button>
              );
            }

            return <div key={`toc-${key}-line-${idx}`}>{cleanDisplay}</div>;
          })}
        </div>
      );
      continue;
    }

    const headingMatch = line.trim().match(/^(#{1,6})\s*(.*)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const Tag: any = `h${Math.min(6, level)}`;

      const headingEmSize = level === 1 ? 1.5 : level === 2 ? 1.35 : level === 3 ? 1.2 : level === 4 ? 1.1 : 1.05;
      const marginClass = level === 1 ? 'mb-6' : level === 2 ? 'mb-4' : level <= 4 ? 'mb-3' : 'mb-2';

      blocks.push(
        <Tag key={`h-${key++}`} className={`font-bold text-[#1a1a1a] dark:text-slate-100 ${marginClass}`} style={{ fontSize: `${headingEmSize}em` }}>
          {renderInline(headingMatch[2] || '', onReferenceClick)}
        </Tag>
      );
      i += 1;
      continue;
    }

    if (isQuote(line)) {
      const quoteLines: string[] = [];
      while (i < lines.length && isQuote(lines[i])) {
        quoteLines.push(lines[i].replace(/^\s*>\s?/, ''));
        i += 1;
      }
      const quoteText = quoteLines.join('\n');
      blocks.push(
        <blockquote key={`quote-${key++}`} className="border-r-2 border-slate-200 pr-4 text-slate-600">
          {renderParagraph(quoteText, `quote-${key}`, onReferenceClick)}
        </blockquote>
      );
      continue;
    }

    if (isOrderedList(line) && !(effectiveIsTocPage && isTocLine(line))) {
      const items: string[] = [];
      while (i < lines.length && isOrderedList(lines[i]) && !(effectiveIsTocPage && isTocLine(lines[i]))) {
        items.push(lines[i].replace(/^\s*\d+[.)]\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ol key={`ol-${key++}`} className="list-decimal pr-6 space-y-1">
          {items.map((item, idx) => (
            <li key={`ol-${key}-item-${idx}`}>{renderInline(item, onReferenceClick)}</li>
          ))}
        </ol>
      );
      continue;
    }

    if (isUnorderedList(line) && !(effectiveIsTocPage && isTocLine(line))) {
      const items: string[] = [];
      while (i < lines.length && isUnorderedList(lines[i]) && !(effectiveIsTocPage && isTocLine(lines[i]))) {
        items.push(lines[i].replace(/^\s*[-*+•]\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ul key={`ul-${key++}`} className="list-disc pr-6 space-y-1">
          {items.map((item, idx) => (
            <li key={`ul-${key}-item-${idx}`}>{renderInline(item, onReferenceClick)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (isTableRow(line)) {
      const tableLines: string[] = [];
      while (i < lines.length && (isTableRow(lines[i]) || isTableSeparator(lines[i]))) {
        tableLines.push(lines[i]);
        i += 1;
      }
      const parseRow = (row: string) =>
        row.split('|').slice(1, -1).map(cell => cell.trim());
      const hasSeparator = tableLines.some(l => isTableSeparator(l));
      const dataLines = tableLines.filter(l => !isTableSeparator(l));
      const hasOffset = effectiveIsTocPage && contentPageOffset !== undefined && contentPageOffset !== null && contentPageOffset > 0;

      if (dataLines.length > 0) {
        if (hasSeparator) {
          const [headerLine, ...bodyLines] = dataLines;
          const headers = parseRow(headerLine);
          const rows = bodyLines.map(parseRow);
          blocks.push(
            <div key={`table-${key++}`} className="overflow-x-auto my-2" dir="rtl">
              <table className="w-full border-collapse text-sm text-slate-800 dark:text-slate-200">
                <thead>
                  <tr>
                    {headers.map((h, idx) => (
                      <th key={idx} className="border border-slate-200 dark:border-slate-800 px-3 py-2 bg-slate-50 dark:bg-slate-900 font-bold text-right text-slate-900 dark:text-slate-100">
                        {renderInline(h, onReferenceClick)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, rowIdx) => {
                    const contentPageNum = hasOffset ? extractRowPageNumber(row) : null;
                    const targetPhysicalPage = (contentPageNum !== null && hasOffset && contentPageOffset) ? contentPageNum + contentPageOffset : null;
                    const isClickable = targetPhysicalPage !== null && (onTocPageClick || onReferenceClick);

                    return (
                      <tr
                        key={rowIdx}
                        onClick={isClickable ? (e) => {
                          e.preventDefault();
                          if (onTocPageClick) {
                            onTocPageClick(targetPhysicalPage);
                          } else if (onReferenceClick) {
                            onReferenceClick('', [targetPhysicalPage]);
                          }
                        } : undefined}
                        className={`
                          ${rowIdx % 2 === 1 ? 'bg-slate-50/50 dark:bg-slate-900/30' : ''}
                          ${isClickable ? 'cursor-pointer hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/15 text-[#0369a1] dark:text-[#38bdf8] transition-colors group' : ''}
                        `}
                      >
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx} className={`border border-slate-200 dark:border-slate-800 px-3 py-2 text-right ${isClickable ? 'group-hover:underline' : ''}`}>
                            {renderInline(cell, onReferenceClick)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        } else {
          const rows = dataLines.map(parseRow);
          blocks.push(
            <div key={`table-${key++}`} className="overflow-x-auto my-2" dir="rtl">
              <table className="w-full border-collapse text-sm text-slate-800 dark:text-slate-200">
                <tbody>
                  {rows.map((row, rowIdx) => {
                    const contentPageNum = hasOffset ? extractRowPageNumber(row) : null;
                    const targetPhysicalPage = (contentPageNum !== null && hasOffset && contentPageOffset) ? contentPageNum + contentPageOffset : null;
                    const isClickable = targetPhysicalPage !== null && (onTocPageClick || onReferenceClick);

                    return (
                      <tr
                        key={rowIdx}
                        onClick={isClickable ? (e) => {
                          e.preventDefault();
                          if (onTocPageClick) {
                            onTocPageClick(targetPhysicalPage);
                          } else if (onReferenceClick) {
                            onReferenceClick('', [targetPhysicalPage]);
                          }
                        } : undefined}
                        className={`
                          ${rowIdx % 2 === 1 ? 'bg-slate-50/50 dark:bg-slate-900/30' : ''}
                          ${isClickable ? 'cursor-pointer hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/15 text-[#0369a1] dark:text-[#38bdf8] transition-colors group' : ''}
                        `}
                      >
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx} className={`px-3 py-1.5 text-right ${isClickable ? 'group-hover:underline' : ''}`}>
                            {renderInline(cell, onReferenceClick)}
                          </td>
                        ))}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        }
      }
      continue;
    }

    const paragraphLines: string[] = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i], effectiveIsTocPage)) {
      paragraphLines.push(lines[i]);
      i += 1;
    }
    if (paragraphLines.length) {
      blocks.push(renderParagraph(paragraphLines.join('\n'), `p-${key++}`, onReferenceClick));
    }
  }

  const containerClass = [className, 'space-y-4'].filter(Boolean).join(' ');
  return (
    <div className={containerClass} style={style} dir="rtl" lang="ug">
      {blocks}
    </div>
  );
});
