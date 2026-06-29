export const UYGHUR_ALPHABET = [
  'ئا', 'ئە', 'ب', 'پ', 'ت', 'ج', 'چ', 'خ', 'د', 'ر', 'ز', 'ژ', 'س', 'ش',
  'غ', 'ف', 'ق', 'ك', 'گ', 'ڭ', 'ل', 'م', 'ن', 'ھ', 'ئو', 'ئۇ', 'ئۆ', 'ئۈ',
  'ۋ', 'ئې', 'ئى', 'ي'
];

export function sortByUyghurAlphabet(letters: string[]): string[] {
  return [...letters].sort((a, b) => {
    const ia = UYGHUR_ALPHABET.indexOf(a);
    const ib = UYGHUR_ALPHABET.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}

export interface ParsedChunk {
  type: 'text' | 'metadata' | 'br';
  content: string;
}

/**
 * Parses a dictionary definition, identifying [CRLF] for breaks and [...] for metadata tags.
 */
export function parseDefinition(text: string): ParsedChunk[] {
  if (!text) return [];
  
  const lines = text.split(/\[CRLF\]/g);
  const chunks: ParsedChunk[] = [];
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (i > 0) {
      chunks.push({ type: 'br', content: '' });
    }
    
    // Split the line while capturing bracketed segments, e.g. [metadata]
    const parts = line.split(/(\[[^\]]+\])/g);
    for (const part of parts) {
      if (!part) continue;
      if (part.startsWith('[') && part.endsWith(']')) {
        chunks.push({ type: 'metadata', content: part });
      } else {
        chunks.push({ type: 'text', content: part });
      }
    }
  }
  
  return chunks;
}

