import React, { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { SEARCH_TABS, SearchTabDef, SearchTabKey } from './searchTabsConfig';

interface SearchTabBarProps {
  activeTab: SearchTabKey;
  onChange: (tab: SearchTabKey) => void;
}

const TABS_PER_PAGE = 6;

const TAB_PAGES: SearchTabDef[][] = Array.from(
  { length: Math.ceil(SEARCH_TABS.length / TABS_PER_PAGE) },
  (_, pageIndex) => SEARCH_TABS.slice(pageIndex * TABS_PER_PAGE, (pageIndex + 1) * TABS_PER_PAGE)
);

export const SearchTabBar: React.FC<SearchTabBarProps> = ({ activeTab, onChange }) => {
  const { t } = useI18n();
  const [currentPage, setCurrentPage] = useState(0);

  const isLastPage = currentPage === TAB_PAGES.length - 1;
  const showToggle = TAB_PAGES.length > 1;

  const handleToggle = () => {
    setCurrentPage(isLastPage ? 0 : currentPage + 1);
  };

  return (
    <div className="w-full border-b border-slate-200 dark:border-slate-800 px-1" dir="rtl">
      <div
        className="flex items-end overflow-x-auto overflow-y-hidden gap-1 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
        dir="rtl"
      >
        {TAB_PAGES[currentPage].map(({ key, labelKey, icon: Icon }) => {
          const isActive = key === activeTab;

          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange(key)}
              aria-pressed={isActive}
              title={t(labelKey)}
              className={`flex items-center gap-2 px-3.5 sm:px-5 py-2.5 sm:py-3 transition-all duration-200 text-[13px] sm:text-[14px] whitespace-nowrap rounded-t-xl font-normal flex-shrink-0 active:scale-95 cursor-pointer ${
                isActive
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm font-semibold'
                  : 'bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-b-0 border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              <Icon size={16} strokeWidth={isActive ? 2.5 : 2} className="flex-shrink-0" />
              <span className="uyghur-text mt-[2px]">{t(labelKey)}</span>
            </button>
          );
        })}
        {showToggle && (
          <button
            type="button"
            data-testid="search-tab-page-toggle"
            onClick={handleToggle}
            title={isLastPage ? t('common.back') : t('common.more')}
            className="flex items-center gap-1.5 px-3.5 sm:px-5 py-2.5 sm:py-3 transition-all duration-200 text-[13px] sm:text-[14px] whitespace-nowrap rounded-t-xl font-normal flex-shrink-0 active:scale-95 cursor-pointer bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-b-0 border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200"
          >
            {isLastPage ? (
              <ChevronRight size={16} strokeWidth={2} className="flex-shrink-0" />
            ) : (
              <ChevronLeft size={16} strokeWidth={2} className="flex-shrink-0" />
            )}
            <span className="uyghur-text mt-[2px]">{isLastPage ? t('common.back') : '...'}</span>
          </button>
        )}
      </div>
    </div>
  );
};
