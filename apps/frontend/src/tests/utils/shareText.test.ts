import { describe, expect, test } from 'vitest';
import { cleanShareText, buildSafeTweetText } from '@/src/utils/shareText';

describe('cleanShareText', () => {
  test('strips markdown ref links, leaving the link text', () => {
    expect(cleanShareText('ئەلۋەتتە **مەنبە:** [باھادىرنامە](ref:427a5621d325:summary)')).toBe(
      'ئەلۋەتتە **مەنبە:** باھادىرنامە'
    );
  });

  test('strips bare (ref:...) fragments', () => {
    expect(cleanShareText('some text (ref:abc123:1,2,3) more text')).toBe('some text  more text');
  });

  test('strips BookID fragments', () => {
    expect(cleanShareText('answer text (BookID: abc-123)')).toBe('answer text');
  });

  test('trims surrounding whitespace', () => {
    expect(cleanShareText('  hello world  ')).toBe('hello world');
  });

  test('returns empty string for falsy input', () => {
    expect(cleanShareText('')).toBe('');
  });
});

describe('buildSafeTweetText', () => {
  test('returns the full untruncated join when it already fits', () => {
    const result = buildSafeTweetText({
      headLines: ['سوئال: What is the key takeaway?'],
      contentPrefix: 'زېرەكچاق: ',
      contentText: 'Knowledge is power.',
      tailLines: ['— Source: Sample Book', '-- كىتابىم تورى\nhttps://kitabim.ai'],
    });

    expect(result).toBe(
      'سوئال: What is the key takeaway?\n\nزېرەكچاق: Knowledge is power.\n\n— Source: Sample Book\n\n-- كىتابىم تورى\nhttps://kitabim.ai'
    );
  });

  test('omits the content line entirely when contentText is empty (no stray prefix/suffix)', () => {
    const result = buildSafeTweetText({
      headLines: ['📌 A Proverb'],
      contentPrefix: '"',
      contentText: '',
      contentSuffix: '"',
      tailLines: ['https://kitabim.ai'],
    });

    expect(result).toBe('📌 A Proverb\n\nhttps://kitabim.ai');
  });

  test('does not truncate long Uyghur content that still fits the real (single-encoded) URL budget — regression test for the double-encoding bug', () => {
    // 1500 Uyghur characters encode to ~9000 chars in a real single-encodeURIComponent
    // pass, comfortably under the default 10000 maxUrlLength. A buggy implementation
    // that measures a SECOND encodeURIComponent pass over the already-encoded URL would
    // inflate this by ~1.6x and truncate it unnecessarily — this test fails on that bug.
    const longContent = 'پەرزەنت تەربىيەسىدە ئائىلە، ئەخلاق ۋە مىللىي كىملىك ئاساسىي ئورۇندا تورىدۇ. '.repeat(20);
    const result = buildSafeTweetText({
      headLines: ['سوئال: قىسقا سوئال'],
      contentPrefix: 'زېرەكچاق: ',
      contentText: longContent,
      tailLines: ['https://kitabim.ai'],
    });

    expect(result).toContain(longContent.trim());
    expect(result).not.toContain('…');
  });

  test('truncates content that exceeds the real URL budget, preserving head/tail lines', () => {
    const veryLongContent = 'پەرزەنت تەربىيەسىدە ئائىلە، ئەخلاق ۋە مىللىي كىملىك ئاساسىي ئورۇندا تورىدۇ. '.repeat(120);
    const result = buildSafeTweetText({
      headLines: ['سوئال: قىسقا سوئال'],
      contentPrefix: 'زېرەكچاق: ',
      contentText: veryLongContent,
      tailLines: ['https://kitabim.ai'],
      maxUrlLength: 2000,
    });

    expect(result).toContain('سوئال: قىسقا سوئال');
    expect(result).toContain('https://kitabim.ai');
    expect(result).toContain('…');
    expect(result.length).toBeLessThan(veryLongContent.length);

    const realUrl = `https://x.com/intent/tweet?text=${encodeURIComponent(result)}`;
    expect(realUrl.length).toBeLessThanOrEqual(2000);
  });

  test('caps an overly long head line to 80 chars when truncation is triggered', () => {
    const longHead = 'سوئال: ' + 'ئۇيغۇرچە سوئال سۆزى '.repeat(20);
    const veryLongContent = 'جاۋاب مەزمۇنى '.repeat(200);
    const result = buildSafeTweetText({
      headLines: [longHead],
      contentPrefix: 'زېرەكچاق: ',
      contentText: veryLongContent,
      tailLines: ['https://kitabim.ai'],
      maxUrlLength: 1500,
    });

    const headLineInResult = result.split('\n\n')[0];
    expect(headLineInResult.length).toBeLessThanOrEqual(81); // 80 chars + ellipsis
  });
});
