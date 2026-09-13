/**
 * Utility for formatting LLM answer cost and token count information.
 * Output format:
 *   - ug: جاۋاب تەننەرقى: ‎$xxx‎، ‎yyy‎ توكېن
 *   - en: Answer cost: $xxx, yyy tokens
 */

export function formatAnswerCost(
  costUsd: number,
  totalTokens: number,
  t?: (key: string, params?: Record<string, string | number>) => string
): string {
  const tokenLabel =
    totalTokens >= 1000
      ? `${(totalTokens / 1000).toFixed(1)}K`
      : `${totalTokens}`;
  const costNum = Number(costUsd) || 0;
  const rawCost =
    costNum > 0 && costNum < 0.0001
      ? '<$0.0001'
      : `$${costNum.toFixed(4)}`;
  // Wrap numbers with Left-to-Right Mark (\u200E) to preserve LTR currency/number
  // ordering in both RTL (Uyghur) and LTR (English) rendering contexts.
  const costLabel = `\u200E${rawCost}\u200E`;
  const tokenVal = `\u200E${tokenLabel}\u200E`;

  if (t) {
    const res = t('chat.answerCost', { cost: costLabel, tokens: tokenVal });
    if (res && res !== 'chat.answerCost') {
      return res;
    }
  }
  return `جاۋاب تەننەرقى: ${costLabel}، ${tokenVal} توكېن`;
}
