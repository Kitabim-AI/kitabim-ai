export interface ChangedRange {
  start: number;
  end: number;
  /** The baseline words this run of changes replaced; '' for a pure insertion. */
  original: string;
}

interface Token {
  text: string;
  start: number;
  end: number;
}

const tokenize = (s: string): Token[] => {
  const tokens: Token[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s)) !== null) {
    tokens.push({ text: m[0], start: m.index, end: m.index + m[0].length });
  }
  return tokens;
};

type DiffOp = { kind: 'same' | 'del' | 'ins'; token: Token };

/**
 * Word-level LCS edit script for the part of `current` that differs from
 * `baseline` (common prefix/suffix are trimmed and not included).
 */
const diffWordOps = (baseline: string, current: string): DiffOp[] => {
  if (baseline === current) return [];
  const a = tokenize(baseline);
  const b = tokenize(current);

  // Trim the common prefix/suffix so the LCS table only covers the changed middle.
  let pre = 0;
  while (pre < a.length && pre < b.length && a[pre].text === b[pre].text) pre++;
  let suf = 0;
  while (
    suf < a.length - pre &&
    suf < b.length - pre &&
    a[a.length - 1 - suf].text === b[b.length - 1 - suf].text
  ) suf++;
  const a2 = a.slice(pre, a.length - suf);
  const b2 = b.slice(pre, b.length - suf);

  const cols = b2.length + 1;
  const dp = new Uint32Array((a2.length + 1) * cols);
  for (let i = a2.length - 1; i >= 0; i--) {
    for (let j = b2.length - 1; j >= 0; j--) {
      dp[i * cols + j] = a2[i].text === b2[j].text
        ? dp[(i + 1) * cols + j + 1] + 1
        : Math.max(dp[(i + 1) * cols + j], dp[i * cols + j + 1]);
    }
  }

  const ops: DiffOp[] = [];
  let i = 0;
  let j = 0;
  while (i < a2.length && j < b2.length) {
    if (a2[i].text === b2[j].text) {
      ops.push({ kind: 'same', token: b2[j] });
      i++;
      j++;
    } else if (dp[(i + 1) * cols + j] >= dp[i * cols + j + 1]) {
      ops.push({ kind: 'del', token: a2[i] });
      i++;
    } else {
      ops.push({ kind: 'ins', token: b2[j] });
      j++;
    }
  }
  for (; i < a2.length; i++) ops.push({ kind: 'del', token: a2[i] });
  for (; j < b2.length; j++) ops.push({ kind: 'ins', token: b2[j] });
  return ops;
};

/**
 * Character ranges in `current` of words that were inserted or changed
 * relative to `baseline` (word-level LCS), each carrying the baseline words it
 * replaced. Adjacent changed words share one run of originals. Deleted words
 * have no position in `current` and are not reported.
 */
export const diffChangedWordRanges = (baseline: string, current: string): ChangedRange[] => {
  const ranges: ChangedRange[] = [];
  let removed: string[] = [];
  let added: Token[] = [];
  const flush = () => {
    const original = removed.join(' ');
    for (const token of added) ranges.push({ start: token.start, end: token.end, original });
    removed = [];
    added = [];
  };
  for (const op of diffWordOps(baseline, current)) {
    if (op.kind === 'same') flush();
    else if (op.kind === 'del') removed.push(op.token.text);
    else added.push(op.token);
  }
  flush();
  return ranges;
};
