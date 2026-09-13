import { describe, expect, it } from 'vitest';
import { formatAnswerCost } from '../../utils/costUtils';

describe('formatAnswerCost', () => {
  it('formats cost and token counts correctly in default Uyghur', () => {
    expect(formatAnswerCost(0.0122, 73100)).toBe('جاۋاب تەننەرقى: \u200E$0.0122\u200E، \u200E73.1K\u200E توكېن');
  });

  it('formats small token counts without K suffix', () => {
    expect(formatAnswerCost(0.0005, 450)).toBe('جاۋاب تەننەرقى: \u200E$0.0005\u200E، \u200E450\u200E توكېن');
  });

  it('formats sub-millicent cost accurately', () => {
    expect(formatAnswerCost(0.00004, 120)).toBe('جاۋاب تەننەرقى: \u200E<$0.0001\u200E، \u200E120\u200E توكېن');
  });

  it('handles zero cost and tokens', () => {
    expect(formatAnswerCost(0, 0)).toBe('جاۋاب تەننەرقى: \u200E$0.0000\u200E، \u200E0\u200E توكېن');
  });

  it('formats using translation function when provided (English)', () => {
    const mockT = (key: string, params?: Record<string, string | number>) => {
      if (key === 'chat.answerCost') {
        return `Answer cost: ${params?.cost}, ${params?.tokens} tokens`;
      }
      return key;
    };
    expect(formatAnswerCost(0.0122, 73100, mockT)).toBe('Answer cost: \u200E$0.0122\u200E, \u200E73.1K\u200E tokens');
  });
});
