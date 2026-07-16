import { BookA, ArrowLeftRight, SpellCheck, ScrollText, User, Languages, Quote } from 'lucide-react';
import React, { useState } from 'react';
import { DictionaryPanel } from '../admin/dictionary/DictionaryPanel';
import { HistoryDictionaryPanel } from '../admin/dictionary/HistoryDictionaryPanel';
import { NamesDictionaryPanel } from '../admin/dictionary/NamesDictionaryPanel';
import { EnglishUyghurPanel } from '../admin/dictionary/EnglishUyghurPanel';
import { WordsPanel } from '../admin/words/WordsPanel';
import { SynonymsPanel } from '../admin/synonyms/SynonymsPanel';
import { ProverbsPanel } from '../admin/dictionary/ProverbsPanel';
import { useI18n } from '../../i18n/I18nContext';

type TabId = 'words' | 'dictionary' | 'synonyms' | 'history' | 'names' | 'english-uyghur' | 'proverbs';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
}

const DictionaryView: React.FC = () => {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<TabId>('dictionary');

  const tabs: Tab[] = [
    { id: 'dictionary', label: t('admin.dictionary.title') || 'ئىزاھلىق لۇغەت', icon: <BookA size={18} /> },
    { id: 'proverbs', label: t('admin.proverbs.title') || 'ماقال-تەمسىللەر', icon: <Quote size={18} /> },
    { id: 'history', label: t('admin.historyDictionary.title') || 'تارىخ لۇغىتى', icon: <ScrollText size={18} /> },
    { id: 'names', label: t('admin.namesDictionary.title') || 'كىشى ئىسىملىرى', icon: <User size={18} /> },
    { id: 'english-uyghur', label: t('admin.englishUyghurDictionary.title') || 'English-Uyghur', icon: <Languages size={18} /> },
    { id: 'synonyms', label: t('admin.synonyms.title') || 'مەنىداش سۆزلەر', icon: <ArrowLeftRight size={18} /> },
    { id: 'words', label: t('admin.words.title') || 'ئىملا لۇغىتى', icon: <SpellCheck size={18} /> },
  ];

  return (
    <div className="space-y-0 px-3 py-3 sm:px-6 md:px-0 animate-fade-in" dir="rtl" lang="ug">
      {/* Tab Navigation */}
      <div className="border-b border-slate-200">
        <div className="flex items-end overflow-x-auto overflow-y-hidden gap-1" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 md:gap-2.5 px-4 sm:px-5 md:px-6 py-2.5 md:py-3 transition-all duration-200
                text-[13px] md:text-[14px] whitespace-nowrap rounded-t-xl font-normal
                ${activeTab === tab.id
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm'
                  : 'bg-white dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-b-0 border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-250'
                }
              `}
              title={tab.label}
            >
              <span className="transition-all duration-200 flex items-center">
                {React.cloneElement(tab.icon as React.ReactElement<any>, { size: 16, className: 'md:w-[17px] md:h-[17px]' })}
              </span>
              <span className="hidden lg:inline mt-[3px]">
                {tab.label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="pt-6 md:pt-8">
        {activeTab === 'words' && <WordsPanel />}
        {activeTab === 'dictionary' && <DictionaryPanel />}
        {activeTab === 'proverbs' && <ProverbsPanel />}
        {activeTab === 'history' && <HistoryDictionaryPanel />}
        {activeTab === 'names' && <NamesDictionaryPanel />}
        {activeTab === 'english-uyghur' && <EnglishUyghurPanel />}
        {activeTab === 'synonyms' && <SynonymsPanel />}
      </div>
    </div>
  );
};

export default DictionaryView;
