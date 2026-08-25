/**
 * Converts a number to Eastern Arabic-Indic digits (٠, ١, ٢, ٣, ٤, ٥, ٦, ٧, ٨, ٩).
 */
export const toEasternArabicDigits = (num: number | string): string => {
  const easternDigits = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
  return String(num).replace(/\d/g, (d) => easternDigits[parseInt(d, 10)]);
};

/**
 * Formats a Quranic ayah number enclosed in traditional Quranic ornate brackets (﴿...﴾).
 */
export const formatQuranAyahNumber = (ayah: number | string): string => {
  return `\uFD3F${toEasternArabicDigits(ayah)}\uFD3E`;
};

/**
 * Normalizes Uthmanic Arabic Quran script for standard Arabic rendering.
 */
export const normalizeArabic = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/\u06E1/g, '\u0652') // Uthmanic Sukun -> Standard Sukun
    .replace(/\u0671/g, '\u0627') // Alif Wasla -> Standard Alif
    .replace(/[\u06D6-\u06DC\u06DF-\u06E0\u06E2-\u06ED]/g, ''); // Remove Uthmanic signs that disrupt cursive connections
};

/**
 * Normalizes Arabic text and appends the Quranic ayah number if provided.
 */
export const normalizeArabicWithAyah = (text: string, ayah?: number | string): string => {
  const normalized = normalizeArabic(text);
  if (!normalized) return '';
  if (ayah !== undefined && ayah !== null && ayah !== '') {
    return `${normalized} ${formatQuranAyahNumber(ayah)}`;
  }
  return normalized;
};

/**
 * Formats a Uyghur translation of a Quran ayah by:
 * 1. Removing trailing verse numbering artifacts (e.g. `(62)`).
 * 2. Trimming extra whitespace or trailing commas.
 * 3. Ensuring proper terminal punctuation (appending `.` if missing).
 */
export const formatQuranAyahUg = (text: string): string => {
  if (!text) return '';
  let t = text.trim();
  if (!t) return '';

  // Remove trailing verse numbering artifacts like (62) or (62)، or (62) .
  t = t.replace(/\s*\(\d+\)\s*[.،]?$/, '').trim();

  // If ends with comma, strip it
  if (t.endsWith('،') || t.endsWith(',')) {
    t = t.slice(0, -1).trim();
  }

  // If ends with quotation marks » or ” or " or ›
  if (/[»”"›]$/.test(t)) {
    const quote = t.slice(-1);
    const inner = t.slice(0, -1).trimEnd();
    if (inner && /[.!؟?…]$/.test(inner)) {
      return t;
    }
    return inner + '.' + quote;
  }

  // If ends with closing parenthesis )
  if (t.endsWith(')')) {
    const inner = t.slice(0, -1).trimEnd();
    if (inner && /[.!؟?…]$/.test(inner)) {
      return t;
    }
    return t + '.';
  }

  // If already ends with sentence-ending punctuation
  if (/[.!؟?…]$/.test(t)) {
    return t;
  }

  return t + '.';
};
