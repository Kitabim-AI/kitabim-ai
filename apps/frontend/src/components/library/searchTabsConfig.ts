import { Bot, Library, BookOpen, FileSearch, BookMarked, Users, ScrollText, MessageSquareQuote, SpellCheck, ArrowLeftRight, Languages, LucideIcon } from 'lucide-react';

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
  | 'synonyms'
  | 'en-ug';

export interface SearchTabDef {
  key: SearchTabKey;
  labelKey: string;
  placeholderKey: string;
  noResultsKey: string;
  icon: LucideIcon;
}

// Fixed order per docs/feature/graph-rag-with-GDS/keyword-search-rework-plan.md Phase 3 — static, no usage tracking.
export const SEARCH_TABS: SearchTabDef[] = [
  { key: 'ask', labelKey: 'home.tabs.ask', placeholderKey: 'home.placeholders.ask', noResultsKey: 'home.noResults.ask', icon: Bot },
  { key: 'books', labelKey: 'home.tabs.books', placeholderKey: 'home.placeholders.books', noResultsKey: 'home.noResults.books', icon: Library },
  { key: 'content', labelKey: 'home.tabs.content', placeholderKey: 'home.placeholders.content', noResultsKey: 'home.noResults.content', icon: FileSearch },
  { key: 'history', labelKey: 'home.tabs.history', placeholderKey: 'home.placeholders.history', noResultsKey: 'home.noResults.history', icon: ScrollText },
  { key: 'dictionary', labelKey: 'home.tabs.dictionary', placeholderKey: 'home.placeholders.dictionary', noResultsKey: 'home.noResults.dictionary', icon: BookMarked },
  { key: 'quran', labelKey: 'home.tabs.quran', placeholderKey: 'home.placeholders.quran', noResultsKey: 'home.noResults.quran', icon: BookOpen },
  { key: 'proverbs', labelKey: 'home.tabs.proverbs', placeholderKey: 'home.placeholders.proverbs', noResultsKey: 'home.noResults.proverbs', icon: MessageSquareQuote },
  { key: 'names', labelKey: 'home.tabs.names', placeholderKey: 'home.placeholders.names', noResultsKey: 'home.noResults.names', icon: Users },
  { key: 'synonyms', labelKey: 'home.tabs.synonyms', placeholderKey: 'home.placeholders.synonyms', noResultsKey: 'home.noResults.synonyms', icon: ArrowLeftRight },
  { key: 'spell-check', labelKey: 'home.tabs.spellCheck', placeholderKey: 'home.placeholders.spellCheck', noResultsKey: 'home.noResults.spellCheck', icon: SpellCheck },
  { key: 'en-ug', labelKey: 'home.tabs.enUg', placeholderKey: 'home.placeholders.enUg', noResultsKey: 'home.noResults.enUg', icon: Languages },
];

export const DEFAULT_SEARCH_TAB: SearchTabKey = 'ask';

export const getTabPlaceholderKey = (tabKey: SearchTabKey): string => {
  const tab = SEARCH_TABS.find((t) => t.key === tabKey);
  return tab ? tab.placeholderKey : 'home.searchOrChatPlaceholder';
};

export const getTabNoResultsKey = (tabKey: SearchTabKey): string => {
  const tab = SEARCH_TABS.find((t) => t.key === tabKey);
  return tab ? tab.noResultsKey : 'library.noResults.title';
};
