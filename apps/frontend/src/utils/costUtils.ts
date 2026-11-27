/**
 * Utility for formatting LLM answer cost and token count information.
 * Output format:
 *   - ug: جاۋاب تەننەرقى: ‎$xxx‎، ‎yyy‎ توكېن
 *   - en: Answer cost: $xxx, yyy tokens
 */

function formatUsdLabel(costUsd: number): string {
  const costNum = Number(costUsd) || 0;
  const rawCost =
    costNum > 0 && costNum < 0.0001
      ? '<$0.0001'
      : `$${costNum.toFixed(4)}`;
  return `\u200E${rawCost}\u200E`;
}

export function formatAnswerCost(
  costUsd: number,
  totalTokens: number,
  t?: (key: string, params?: Record<string, string | number>) => string
): string {
  const tokenLabel =
    totalTokens >= 1000
      ? `${(totalTokens / 1000).toFixed(1)}K`
      : `${totalTokens}`;
  // Wrap numbers with Left-to-Right Mark (\u200E) to preserve LTR currency/number
  // ordering in both RTL (Uyghur) and LTR (English) rendering contexts.
  const costLabel = formatUsdLabel(costUsd);
  const tokenVal = `\u200E${tokenLabel}\u200E`;

  if (t) {
    const res = t('chat.answerCost', { cost: costLabel, tokens: tokenVal });
    if (res && res !== 'chat.answerCost') {
      return res;
    }
  }
  return `جاۋاب تەننەرقى: ${costLabel}، ${tokenVal} توكېن`;
}

export function formatCostBreakdownTooltip(
  chatCostUsd: number,
  ttsCostUsd: number,
  t?: (key: string, params?: Record<string, string | number>) => string
): string {
  const chatLabel = formatUsdLabel(chatCostUsd);
  const ttsLabel = formatUsdLabel(ttsCostUsd);
  if (t) {
    const res = t('chat.costBreakdownTooltip', {
      chatCost: chatLabel,
      ttsCost: ttsLabel,
    });
    if (res && res !== 'chat.costBreakdownTooltip') {
      return res;
    }
  }
  return `سۆھبەت: ${chatLabel} + ئاۋاز: ${ttsLabel}`;
}
