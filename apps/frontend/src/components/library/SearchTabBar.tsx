import React from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { SEARCH_TABS, SearchTabKey } from './searchTabsConfig';

interface SearchTabBarProps {
  activeTab: SearchTabKey;
  onChange: (tab: SearchTabKey) => void;
}

export const SearchTabBar: React.FC<SearchTabBarProps> = ({ activeTab, onChange }) => {
  const { t } = useI18n();

  return (
    <div className="w-full overflow-x-auto custom-scrollbar pb-1" dir="rtl">
      <div className="flex items-center gap-2 min-w-max px-0.5">
        {SEARCH_TABS.map(({ key, labelKey, icon: Icon }) => {
          const isActive = key === activeTab;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange(key)}
              aria-pressed={isActive}
              className={`flex items-center gap-1.5 px-3 sm:px-4 py-2 rounded-2xl text-xs sm:text-sm font-normal whitespace-nowrap transition-all active:scale-95 ${
                isActive
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-md shadow-[#0369a1]/20'
                  : 'bg-white/60 dark:bg-slate-900/60 text-slate-500 dark:text-slate-400 border border-[#0369a1]/10 dark:border-slate-800 hover:border-[#0369a1]/30 hover:text-[#0369a1] dark:hover:text-[#38bdf8]'
              }`}
            >
              <Icon size={14} strokeWidth={2.5} />
              <span className="uyghur-text">{t(labelKey)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
