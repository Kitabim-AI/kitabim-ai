import React, { useEffect, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { SEARCH_TABS, SearchTabDef, SearchTabKey } from './searchTabsConfig';

interface SearchTabBarProps {
  activeTab: SearchTabKey;
  onChange: (tab: SearchTabKey) => void;
}

const TABS_PER_PAGE = 11;

const TAB_PAGES: SearchTabDef[][] = Array.from(
  { length: Math.ceil(SEARCH_TABS.length / TABS_PER_PAGE) },
  (_, pageIndex) => SEARCH_TABS.slice(pageIndex * TABS_PER_PAGE, (pageIndex + 1) * TABS_PER_PAGE)
);

const PAGE_TOGGLE_CLASSNAME =
  'hidden sm:flex items-center gap-1 px-2.5 sm:px-3.5 py-1.5 sm:py-2 transition-all duration-200 text-xs sm:text-sm whitespace-nowrap rounded-t-xl font-normal flex-shrink-0 active:scale-95 cursor-pointer bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border-0 sm:border sm:border-b-0 sm:border-slate-200 dark:sm:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200';

const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 640 : false
  );

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 640);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return isMobile;
};

export const SearchTabBar: React.FC<SearchTabBarProps> = ({ activeTab, onChange }) => {
  const { t } = useI18n();
  const [currentPage, setCurrentPage] = useState(0);
  const isMobile = useIsMobile();
  const tabRefs = React.useRef<Map<SearchTabKey, HTMLButtonElement>>(new Map());

  const isFirstPage = currentPage === 0;
  const showPagination = TAB_PAGES.length > 1;

  const goToNextPage = () => setCurrentPage((page) => page + 1);
  const goToFirstPage = () => setCurrentPage(0);

  const visibleTabs = isMobile ? SEARCH_TABS : TAB_PAGES[currentPage];

  useEffect(() => {
    const activeEl = tabRefs.current.get(activeTab);
    if (activeEl) {
      activeEl.scrollIntoView?.({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }, [activeTab]);

  return (
    <div className="w-full border-b border-slate-200 dark:border-slate-800 px-1" dir="rtl">
      <div
        className="flex items-end w-full overflow-x-auto overflow-y-hidden gap-1 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
        dir="rtl"
      >
        {showPagination && !isFirstPage && (
          <button
            type="button"
            data-testid="search-tab-page-toggle"
            onClick={goToFirstPage}
            title={t('common.back')}
            className={PAGE_TOGGLE_CLASSNAME}
          >
            <ChevronRight size={16} strokeWidth={2} className="flex-shrink-0" />
            <span className="uyghur-text mt-[2px]">...</span>
          </button>
        )}

        {visibleTabs.map(({ key, labelKey }) => {
          const isActive = key === activeTab;

          return (
            <button
              key={key}
              ref={(el) => {
                if (el) tabRefs.current.set(key, el);
                else tabRefs.current.delete(key);
              }}
              type="button"
              onClick={() => onChange(key)}
              aria-pressed={isActive}
              title={t(labelKey)}
              className={`shrink-0 sm:flex-1 sm:min-w-0 flex items-center justify-center gap-1 px-3 sm:px-2 py-1.5 sm:py-2 transition-all duration-200 text-xs sm:text-xs whitespace-nowrap rounded-t-xl font-normal active:scale-95 cursor-pointer ${
                isActive
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm font-semibold'
                  : 'bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border-0 sm:border sm:border-b-0 sm:border-slate-200 dark:sm:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              <span className="uyghur-text mt-[2px] whitespace-nowrap sm:truncate">{t(labelKey)}</span>
            </button>
          );
        })}

        {showPagination && isFirstPage && (
          <button
            type="button"
            data-testid="search-tab-page-toggle"
            onClick={goToNextPage}
            title={t('common.more')}
            className={PAGE_TOGGLE_CLASSNAME}
          >
            <ChevronLeft size={16} strokeWidth={2} className="flex-shrink-0" />
            <span className="uyghur-text mt-[2px]">...</span>
          </button>
        )}
      </div>
    </div>
  );
};
