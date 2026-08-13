import { Book, PaginatedBooks } from '@shared/types';
import { authFetch } from './authService';

const API_BASE = '/api';

export interface DictionaryEntry {
  id: number;
  word: string;
  definition?: string | null;
  audio?: string | null;
}

export interface NameEntry {
  id: number;
  name: string;
  letterGroup: string;
}

export interface HistoryTermEntry {
  id: number;
  term: string;
  transliteration?: string | null;
  definition?: string | null;
  letterGroup: string;
  isAiGenerated?: boolean;
}

export interface ProverbEntry {
  id: number;
  text: string;
  volume?: number | null;
  pageNumber?: number | null;
}

export interface EnglishUyghurEntry {
  id: number;
  english: string;
  uyghur: string;
  letterGroup: string;
}

export interface SynonymEntry {
  id: number;
  word: string;
  letterGroup: string;
  synonyms: string[];
}

export interface QuranAyah {
  id: number;
  surah: number;
  surahNameEn: string;
  surahNameAr: string;
  surahNameUg: string;
  ayah: number;
  textAr: string;
  textEn: string;
  textUg: string;
}

export interface SpellingSuggestion {
  id: number;
  word: string;
  score?: number | null;
}

export interface SpellingCheckResult {
  isKnown: boolean;
  word?: string | null;
  suggestions: SpellingSuggestion[];
}

export interface ContentSearchHit {
  id: string;
  bookId: string;
  bookTitle: string;
  bookAuthor?: string | null;
  bookVolume?: number | null;
  bookCoverUrl?: string | null;
  pageNumber: number;
  snippet: string;
  rank?: number | null;
}

export interface PaginatedContentHits {
  hits: ContentSearchHit[];
  total: number;
  page: number;
  pageSize: number;
}

async function getJson<T>(url: string, fallback: T): Promise<T> {
  try {
    const response = await authFetch(url);
    if (!response.ok) return fallback;
    return await response.json();
  } catch {
    return fallback;
  }
}

export const SearchTabsService = {
  async searchDictionary(q: string, limit: number = 20): Promise<DictionaryEntry[]> {
    return getJson(`${API_BASE}/dictionary/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
  },

  async searchNames(q: string, limit: number = 20): Promise<NameEntry[]> {
    const raw = await getJson<any[]>(`${API_BASE}/names-dictionary/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
    return raw.map((r) => ({ id: r.id, name: r.name, letterGroup: r.letter_group }));
  },

  async searchHistoryTerms(q: string, limit: number = 20): Promise<HistoryTermEntry[]> {
    const raw = await getJson<any[]>(`${API_BASE}/history-dictionary/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
    return raw.map((r) => ({
      id: r.id,
      term: r.term,
      transliteration: r.transliteration,
      definition: r.definition,
      letterGroup: r.letter_group,
      isAiGenerated: r.is_ai_generated,
    }));
  },

  async searchProverbs(q: string, limit: number = 20): Promise<ProverbEntry[]> {
    const raw = await getJson<any[]>(`${API_BASE}/proverbs/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
    return raw.map((r) => ({ id: r.id, text: r.text, volume: r.volume, pageNumber: r.page_number }));
  },

  async searchEnglishUyghur(q: string, limit: number = 20): Promise<EnglishUyghurEntry[]> {
    const raw = await getJson<any[]>(`${API_BASE}/english-uyghur-dictionary/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
    return raw.map((r) => ({ id: r.id, english: r.english, uyghur: r.uyghur, letterGroup: r.letter_group }));
  },

  async searchSynonyms(q: string, limit: number = 20): Promise<SynonymEntry[]> {
    const raw = await getJson<any[]>(`${API_BASE}/synonyms/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
    return raw.map((r) => ({ id: r.id, word: r.word, letterGroup: r.letter_group, synonyms: r.synonyms || [] }));
  },

  async searchQuran(q: string, limit: number = 20): Promise<QuranAyah[]> {
    const raw = await getJson<any[]>(`${API_BASE}/quran/search?q=${encodeURIComponent(q)}&limit=${limit}`, []);
    return raw.map((r) => ({
      id: r.id,
      surah: r.surah,
      surahNameEn: r.surah_name_en,
      surahNameAr: r.surah_name_ar,
      surahNameUg: r.surah_name_ug,
      ayah: r.ayah,
      textAr: r.text_ar,
      textEn: r.text_en,
      textUg: r.text_ug,
    }));
  },

  async checkSpelling(word: string): Promise<SpellingCheckResult | null> {
    try {
      const response = await authFetch(`${API_BASE}/dictionary/check-spelling?word=${encodeURIComponent(word)}`);
      if (!response.ok) return null;
      const data = await response.json();
      return { isKnown: data.is_known, word: data.word, suggestions: data.suggestions || [] };
    } catch {
      return null;
    }
  },

  async searchBookContent(q: string, page: number = 1, pageSize: number = 40): Promise<PaginatedContentHits> {
    try {
      const url = `${API_BASE}/books/content-search?q=${encodeURIComponent(q)}&page=${page}&pageSize=${pageSize}`;
      const response = await authFetch(url);
      if (!response.ok) throw new Error('Failed to fetch content search results');
      return await response.json();
    } catch (error) {
      console.error('Failed to fetch content search results', error);
      return { hits: [], total: 0, page, pageSize };
    }
  },
};

