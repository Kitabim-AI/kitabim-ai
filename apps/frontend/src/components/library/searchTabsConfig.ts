import { Bot, Library, BookOpen, FileSearch, BookMarked, Users, ScrollText, MessageSquareQuote, SpellCheck, Languages, LucideIcon } from 'lucide-react';

export type SearchTabKey =
  | 'ask'
  | 'books'
  | 'quran'
  | 'content'
  | 'dictionary'
  | 'names'
  | 'history'
  | 'proverbs'
  | 'spell-check'
  | 'en-ug';

export interface SearchTabDef {
  key: SearchTabKey;
  labelKey: string;
  icon: LucideIcon;
}

// Fixed order per docs/feature/graph-rag-with-GDS/keyword-search-rework-plan.md Phase 3 — static, no usage tracking.
export const SEARCH_TABS: SearchTabDef[] = [
  { key: 'ask', labelKey: 'home.tabs.ask', icon: Bot },
  { key: 'books', labelKey: 'home.tabs.books', icon: Library },
  { key: 'quran', labelKey: 'home.tabs.quran', icon: BookOpen },
  { key: 'content', labelKey: 'home.tabs.content', icon: FileSearch },
  { key: 'dictionary', labelKey: 'home.tabs.dictionary', icon: BookMarked },
  { key: 'names', labelKey: 'home.tabs.names', icon: Users },
  { key: 'history', labelKey: 'home.tabs.history', icon: ScrollText },
  { key: 'proverbs', labelKey: 'home.tabs.proverbs', icon: MessageSquareQuote },
  { key: 'spell-check', labelKey: 'home.tabs.spellCheck', icon: SpellCheck },
  { key: 'en-ug', labelKey: 'home.tabs.enUg', icon: Languages },
];

export const DEFAULT_SEARCH_TAB: SearchTabKey = 'ask';
export const HOME_SEARCH_TAB_STORAGE_KEY = 'kitabim:homeSearchTab';
