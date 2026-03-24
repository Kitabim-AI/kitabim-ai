import React from 'react';

type MarkdownContentProps = {
  content: string;
  className?: string;
  style?: React.CSSProperties;
  onReferenceClick?: (bookId: string, pageNums: number[]) => void;
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
      const nestedRef = effectiveUrl.match(/ref:[\w]+:[\d,]+/);
      if (nestedRef) effectiveUrl = nestedRef[0];
    }

    if (effectiveUrl.startsWith('ref:')) {
      const parts = effectiveUrl.split(':');
      const bookId = parts[1];
      const pageNumsStr = parts[2] || '';
      const pageNums = pageNumsStr.split(',').map(p => parseInt(p.trim(), 10)).filter(p => !isNaN(p));

      // Clean up the text in case the LLM included the BookID inside the link name
      const cleanText = text.replace(/\s*\(?BookID:\s*[a-zA-Z0-9-]+\)?/gi, '');

      return (
        <button
          key={`ref-${key}`}
          onClick={(e) => {
            e.preventDefault();
            console.log('Reference clicked:', { bookId, pageNums });
            if (onReferenceClick && bookId && pageNums.length > 0) {
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
const isTocLine = (line: string) => dotLeaderPattern.test(line);
const isTableRow = (line: string) => /^\s*\|/.test(line);
const isTableSeparator = (line: string) => /^\s*\|[\s|:=-]+\|?\s*$/.test(line);
const isBlockStart = (line: string) =>
  isHr(line) || isHeading(line) || isQuote(line) || isOrderedList(line) || isUnorderedList(line) || isTocLine(line) || isTableRow(line);

export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, className, style, onReferenceClick }) => {
  const normalized = (content || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const lines = normalized
    .split('\n')
    .map(line => line.replace(/\[(Header|Footer)\]/g, '').trim())
    .filter(line => {
      if (!line) return false;
      // Allow lines that contain text OR start with markdown block markers (including table rows/separators)
      return /[A-Za-z\u0600-\u06FF]/.test(line) || isBlockStart(line) || isTableSeparator(line);
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

    if (isTocLine(line)) {
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

      blocks.push(
        <div key={`toc-${key++}`} className="space-y-1 whitespace-pre-wrap tabular-nums">
          {mergedLines.map((tocLine, idx) => (
            <div key={`toc-${key}-line-${idx}`}>{tocLine}</div>
          ))}
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
        <Tag key={`h-${key++}`} className={`font-bold text-[#1a1a1a] ${marginClass}`} style={{ fontSize: `${headingEmSize}em` }}>
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

    if (isOrderedList(line) && !isTocLine(line)) {
      const items: string[] = [];
      while (i < lines.length && isOrderedList(lines[i]) && !isTocLine(lines[i])) {
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

    if (isUnorderedList(line) && !isTocLine(line)) {
      const items: string[] = [];
      while (i < lines.length && isUnorderedList(lines[i]) && !isTocLine(lines[i])) {
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
      if (dataLines.length > 0) {
        if (hasSeparator) {
          const [headerLine, ...bodyLines] = dataLines;
          const headers = parseRow(headerLine);
          const rows = bodyLines.map(parseRow);
          blocks.push(
            <div key={`table-${key++}`} className="overflow-x-auto my-2" dir="rtl">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr>
                    {headers.map((h, idx) => (
                      <th key={idx} className="border border-slate-200 px-3 py-2 bg-slate-50 font-bold text-right">
                        {renderInline(h, onReferenceClick)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, rowIdx) => (
                    <tr key={rowIdx} className={rowIdx % 2 === 1 ? 'bg-slate-50/50' : ''}>
                      {row.map((cell, cellIdx) => (
                        <td key={cellIdx} className="border border-slate-200 px-3 py-2 text-right">
                          {renderInline(cell, onReferenceClick)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        } else {
          const rows = dataLines.map(parseRow);
          blocks.push(
            <div key={`table-${key++}`} className="overflow-x-auto my-2" dir="rtl">
              <table className="w-full border-collapse text-sm">
                <tbody>
                  {rows.map((row, rowIdx) => (
                    <tr key={rowIdx} className={rowIdx % 2 === 1 ? 'bg-slate-50/50' : ''}>
                      {row.map((cell, cellIdx) => (
                        <td key={cellIdx} className="px-3 py-1.5 text-right">
                          {renderInline(cell, onReferenceClick)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
      }
      continue;
    }

    const paragraphLines: string[] = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
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
};
