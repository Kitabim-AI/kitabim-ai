export interface ChangedRange {
  start: number;
  end: number;
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

/**
 * Character ranges in `current` of words that were inserted or changed
 * relative to `baseline` (word-level LCS). Deleted words have no position in
 * `current` and are not reported.
 */
export const diffChangedWordRanges = (baseline: string, current: string): ChangedRange[] => {
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

  const ranges: ChangedRange[] = [];
  let i = 0;
  let j = 0;
  while (i < a2.length && j < b2.length) {
    if (a2[i].text === b2[j].text) {
      i++;
      j++;
    } else if (dp[(i + 1) * cols + j] >= dp[i * cols + j + 1]) {
      i++;
    } else {
      ranges.push({ start: b2[j].start, end: b2[j].end });
      j++;
    }
  }
  for (; j < b2.length; j++) ranges.push({ start: b2[j].start, end: b2[j].end });
  return ranges;
};
