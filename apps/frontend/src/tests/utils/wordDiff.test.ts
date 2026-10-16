import { describe, expect, test } from 'vitest';
import { diffChangedWordRanges } from '@/src/utils/wordDiff';

const rangeOf = (text: string, word: string, original: string, from = 0) => {
  const start = text.indexOf(word, from);
  return { start, end: start + word.length, original };
};

describe('diffChangedWordRanges', () => {
  test('identical text has no changes', () => {
    expect(diffChangedWordRanges('مەن كىتاب ئوقۇدۇم', 'مەن كىتاب ئوقۇدۇم')).toEqual([]);
  });

  test('single substituted Uyghur word', () => {
    const current = 'مەن كىتاپ ئوقۇدۇم';
    expect(diffChangedWordRanges('مەن كىتاب ئوقۇدۇم', current)).toEqual([rangeOf(current, 'كىتاپ', 'كىتاب')]);
  });

  test('multiple substitutions across line breaks', () => {
    const baseline = 'a b\nc d\n\ne f';
    const current = 'a x\nc d\n\ny f';
    expect(diffChangedWordRanges(baseline, current)).toEqual([
      rangeOf(current, 'x', 'b'),
      rangeOf(current, 'y', 'e'),
    ]);
  });

  test('inserted word is highlighted with no original', () => {
    const current = 'one two new three';
    expect(diffChangedWordRanges('one two three', current)).toEqual([rangeOf(current, 'new', '')]);
  });

  test('deleted word produces no range', () => {
    expect(diffChangedWordRanges('one two three', 'one three')).toEqual([]);
  });

  test('punctuation attached to a word counts as part of the token', () => {
    const current = 'سۆز كىتاپ.';
    expect(diffChangedWordRanges('سۆز كىتاب.', current)).toEqual([rangeOf(current, 'كىتاپ.', 'كىتاب.')]);
  });

  test('repeated words: only the changed occurrence is highlighted', () => {
    const baseline = 'bir bir bir';
    const current = 'bir iki bir';
    expect(diffChangedWordRanges(baseline, current)).toEqual([rangeOf(current, 'iki', 'bir')]);
  });

  test('whitespace-only differences are not changes', () => {
    expect(diffChangedWordRanges('a  b', 'a b')).toEqual([]);
  });

  test('adjacent changed words share the run of original words', () => {
    const current = 'a b c d';
    expect(diffChangedWordRanges('a bx cx d', current)).toEqual([
      rangeOf(current, 'b', 'bx cx'),
      rangeOf(current, 'c', 'bx cx'),
    ]);
  });

  test('split and merged words carry the original form', () => {
    const split = 'a b c d';
    expect(diffChangedWordRanges('a bc d', split)).toEqual([
      rangeOf(split, 'b', 'bc'),
      rangeOf(split, 'c', 'bc', 3),
    ]);
    const merged = 'a bc d';
    expect(diffChangedWordRanges('a b c d', merged)).toEqual([rangeOf(merged, 'bc', 'b c')]);
  });
});
