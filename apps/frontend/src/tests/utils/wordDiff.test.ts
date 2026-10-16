import { describe, expect, test } from 'vitest';
import { diffChangedWordRanges } from '@/src/utils/wordDiff';

const rangeOf = (text: string, word: string, from = 0) => {
  const start = text.indexOf(word, from);
  return { start, end: start + word.length };
};

describe('diffChangedWordRanges', () => {
  test('identical text has no changes', () => {
    expect(diffChangedWordRanges('مەن كىتاب ئوقۇدۇم', 'مەن كىتاب ئوقۇدۇم')).toEqual([]);
  });

  test('single substituted Uyghur word', () => {
    const current = 'مەن كىتاپ ئوقۇدۇم';
    expect(diffChangedWordRanges('مەن كىتاب ئوقۇدۇم', current)).toEqual([rangeOf(current, 'كىتاپ')]);
  });

  test('multiple substitutions across line breaks', () => {
    const baseline = 'a b\nc d\n\ne f';
    const current = 'a x\nc d\n\ny f';
    expect(diffChangedWordRanges(baseline, current)).toEqual([
      rangeOf(current, 'x'),
      rangeOf(current, 'y'),
    ]);
  });

  test('inserted word is highlighted', () => {
    const current = 'one two new three';
    expect(diffChangedWordRanges('one two three', current)).toEqual([rangeOf(current, 'new')]);
  });

  test('deleted word produces no range', () => {
    expect(diffChangedWordRanges('one two three', 'one three')).toEqual([]);
  });

  test('punctuation attached to a word counts as part of the token', () => {
    const current = 'سۆز كىتاپ.';
    expect(diffChangedWordRanges('سۆز كىتاب.', current)).toEqual([rangeOf(current, 'كىتاپ.')]);
  });

  test('repeated words: only the changed occurrence is highlighted', () => {
    const baseline = 'bir bir bir';
    const current = 'bir iki bir';
    expect(diffChangedWordRanges(baseline, current)).toEqual([rangeOf(current, 'iki')]);
  });

  test('whitespace-only differences are not changes', () => {
    expect(diffChangedWordRanges('a  b', 'a b')).toEqual([]);
  });
});
