import { RefreshCw, Search } from 'lucide-react';
import React, { useEffect, useRef } from 'react';
import { Book } from '@shared/types';
import { useIsEditor } from '../../hooks/useAuth';
import { useContentSearch } from '../../hooks/useContentSearch';
import { useLookupSearch } from '../../hooks/useLookupSearch';
import { useSpellingCheck } from '../../hooks/useSpellingCheck';
import { useI18n } from '../../i18n/I18nContext';
import {
  DictionaryEntry,
  EnglishUyghurEntry,
  HistoryTermEntry,
  NameEntry,
  ProverbEntry,
  SearchTabsService,
  SynonymEntry,
} from '../../services/searchTabsService';
import { ContentResultsList } from './ContentResultsList';
import { LookupItem, LookupResultsList } from './LookupResultsList';
import { QuranResultsList } from './QuranResultsList';
import { SearchTabKey, getTabNoResultsKey } from './searchTabsConfig';
import { SpellCheckResultView } from './SpellCheckResult';

interface HomeSearchTabResultsProps {
  activeTab: SearchTabKey;
  query: string;
  pageSize: number;
  onOpenBook: (book: Book | { id: string }, initialPage?: number) => void;
}

// Only the active tab's hook receives the live query — the rest get '' so they skip fetching
// (rules of hooks means every hook still runs each render, just as a cheap no-op).
const queryFor = (tab: SearchTabKey, activeTab: SearchTabKey, query: string) =>
  tab === activeTab ? query : '';

const mapDictionary = (e: DictionaryEntry): LookupItem => ({ id: e.id, primary: e.word, secondary: e.definition });
const mapName = (e: NameEntry): LookupItem => ({ id: e.id, primary: e.name });
const mapHistory = (e: HistoryTermEntry): LookupItem => ({
  id: e.id,
  primary: e.transliteration ? `${e.term} (${e.transliteration})` : e.term,
  secondary: e.definition,
});
const mapSynonyms = (e: SynonymEntry): LookupItem => ({
  id: e.id,
  primary: e.word,
  secondary: Array.isArray(e.synonyms) ? e.synonyms.join('، ') : '',
});
const mapEnUg = (e: EnglishUyghurEntry): LookupItem => ({
  id: e.id,
  primary: e.english,
  secondary: e.uyghur,
  primaryClassName: 'text-base font-bold text-[#1a1a1a] dark:text-slate-100',
  secondaryClassName: 'mt-1 text-base text-slate-500 dark:text-slate-400 uyghur-text',
  primaryDir: 'ltr',
  secondaryDir: 'rtl',
});

export const HomeSearchTabResults: React.FC<HomeSearchTabResultsProps> = ({ activeTab, query, pageSize, onOpenBook }) => {
  const { t } = useI18n();
  const isEditor = useIsEditor();

  const dictionary = useLookupSearch(SearchTabsService.searchDictionary, queryFor('dictionary', activeTab, query), 1);
  const names = useLookupSearch(SearchTabsService.searchNames, queryFor('names', activeTab, query), 1);
  const history = useLookupSearch(SearchTabsService.searchHistoryTerms, queryFor('history', activeTab, query), 1);
  const proverbs = useLookupSearch(SearchTabsService.searchProverbs, queryFor('proverbs', activeTab, query), 1);
  const synonyms = useLookupSearch(SearchTabsService.searchSynonyms, queryFor('synonyms', activeTab, query), 1);
  const enUg = useLookupSearch(SearchTabsService.searchEnglishUyghur, queryFor('en-ug', activeTab, query), 1);
  const quran = useLookupSearch(SearchTabsService.searchQuran, queryFor('quran', activeTab, query), 2);
  const content = useContentSearch(queryFor('content', activeTab, query), pageSize);
  const spelling = useSpellingCheck(queryFor('spell-check', activeTab, query));

  const loaderRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (activeTab !== 'content') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !content.isLoading && content.hasMore && !content.isLoadingMore) {
          content.loadMore();
        }
      },
      { threshold: 0.1, rootMargin: '600px' }
    );
    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [activeTab, content.isLoading, content.hasMore, content.isLoadingMore, content.loadMore]);

  const mapProverb = (e: ProverbEntry): LookupItem => ({
    id: e.id,
    primary: e.text,
    secondary: isEditor && (e.volume != null || e.pageNumber != null)
      ? t('home.tabs.proverbVolumePage', { volume: e.volume ?? '-', page: e.pageNumber ?? '-' })
      : undefined,
  });

  const trimmedQuery = query.trim();
  const hasQuery = trimmedQuery.length > 0;
  const noResultsTitleKey = getTabNoResultsKey(activeTab);

  switch (activeTab) {
    case 'dictionary':
      return <LookupResultsList items={dictionary.results.map(mapDictionary)} isLoading={dictionary.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'names':
      return <LookupResultsList items={names.results.map(mapName)} isLoading={names.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'history':
      return <LookupResultsList items={history.results.map(mapHistory)} isLoading={history.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'proverbs':
      return <LookupResultsList items={proverbs.results.map(mapProverb)} isLoading={proverbs.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'synonyms':
      return <LookupResultsList items={synonyms.results.map(mapSynonyms)} isLoading={synonyms.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'en-ug':
      return <LookupResultsList items={enUg.results.map(mapEnUg)} isLoading={enUg.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'quran':
      return <QuranResultsList items={quran.results} isLoading={quran.isLoading} hasQuery={hasQuery} noResultsTitleKey={noResultsTitleKey} />;
    case 'spell-check':
      return <SpellCheckResultView result={spelling.result} isLoading={spelling.isLoading} hasQuery={hasQuery} />;
    case 'content':
      return (
        <div className="w-full max-w-none">
          <ContentResultsList
            hits={content.hits}
            isLoading={content.isLoading}
            hasQuery={hasQuery}
            query={trimmedQuery}
            noResultsTitleKey={noResultsTitleKey}
            onOpenHit={(hit) => onOpenBook({ id: hit.bookId } as Book, hit.pageNumber)}
          />
          {content.hits.length > 0 && (
            <div ref={loaderRef} className="h-20 flex items-center justify-center">
              {content.isLoadingMore && <RefreshCw className="w-6 h-6 text-[#0369a1] dark:text-[#38bdf8] animate-spin" />}
            </div>
          )}
        </div>
      );
    default:
      return null;
  }
};
