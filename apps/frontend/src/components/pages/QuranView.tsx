import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Hash,
  Loader2,
  RefreshCw,
  Search,
  BookOpen,
  X
} from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useI18n } from '../../i18n/I18nContext';
import { authFetch } from '../../services/authService';

interface QuranAyahEntry {
  id: number;
  surah: number;
  surah_name_en: string;
  surah_name_ar: string;
  surah_name_ug: string;
  ayah: number;
  text_ar: string;
  text_en: string;
  text_ug: string;
}

interface SurahEntry {
  surah: number;
  surah_name_en: string;
  surah_name_ar: string;
  surah_name_ug: string;
}

import { formatQuranAyahUg, normalizeArabicWithAyah } from '../../utils/quranUtils';

export const QuranView: React.FC = () => {
  const { t, language } = useI18n();
  const [suggestions, setSuggestions] = useState<QuranAyahEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [surahs, setSurahs] = useState<SurahEntry[]>([]);
  const [activeSurah, setActiveSurah] = useState<number | null>(1);
  const [activeAyah, setActiveAyah] = useState<number | null>(null);
  const [verses, setVerses] = useState<QuranAyahEntry[]>([]);
  const [isLoadingVerses, setIsLoadingVerses] = useState(false);
  const [stats, setStats] = useState<{ total_entries: number } | null>(null);

  // Separate combobox input and focus states
  const [surahInputValue, setSurahInputValue] = useState('');
  const [ayahInputValue, setAyahInputValue] = useState('');
  const [surahSearchQuery, setSurahSearchQuery] = useState('');
  const [ayahSearchQuery, setAyahSearchQuery] = useState('');
  const [isSurahFocused, setIsSurahFocused] = useState(false);
  const [isAyahFocused, setIsAyahFocused] = useState(false);

  // Global Keyword Search State
  const [globalSearchQuery, setGlobalSearchQuery] = useState('');

  // Fetch all surahs
  const fetchSurahs = async () => {
    try {
      const resp = await authFetch('/api/quran/surahs');
      if (resp.ok) {
        const data = await resp.json();
        setSurahs(data);
      }
    } catch (e) {
      console.error('Failed to fetch surahs list', e);
    }
  };

  // Fetch verses for active surah
  const fetchVerses = async (surahNum: number) => {
    setIsLoadingVerses(true);
    try {
      const resp = await authFetch(`/api/quran?surah=${surahNum}&limit=350`);
      if (resp.ok) {
        const data = await resp.json();
        setVerses(data);
      }
    } catch (e) {
      console.error(`Failed to fetch verses for surah ${surahNum}`, e);
    } finally {
      setIsLoadingVerses(false);
    }
  };

  // Fetch total count stats
  const fetchStats = async (surahNum?: number) => {
    try {
      const url = surahNum ? `/api/quran/stats?surah=${surahNum}` : '/api/quran/stats';
      const resp = await authFetch(url);
      if (resp.ok) {
        setStats(await resp.json());
      }
    } catch (e) {
      console.error('Failed to fetch quran stats', e);
    }
  };

  // Search verses
  const searchEntries = async (q: string) => {
    if (!q.trim()) {
      setSuggestions([]);
      return;
    }

    setIsSearching(true);
    try {
      const resp = await authFetch(`/api/quran/search?q=${encodeURIComponent(q)}&limit=30`);
      if (resp.ok) {
        const data = await resp.json();
        setSuggestions(data);
      }
    } catch (e) {
      console.error('Failed to search Quran', e);
    } finally {
      setIsSearching(false);
    }
  };

  useEffect(() => {
    fetchSurahs();
    fetchStats(1);
    fetchVerses(1);
  }, []);

  const activeSurahObj = surahs.find(s => s.surah === activeSurah);

  const getSurahLabel = (sObj?: SurahEntry) => {
    if (!sObj) return '';
    return language === 'ug'
      ? `${sObj.surah}. ${sObj.surah_name_ug} سۈرىسى`
      : `${sObj.surah}. ${sObj.surah_name_en}`;
  };

  const getAyahLabel = (ayahNum: number | null) => {
    if (ayahNum === null) {
      return t('quran.allAyahs') || 'ھەممە ئايەت';
    }
    return language === 'ug'
      ? `${ayahNum}-ئايەت`
      : `Ayah ${ayahNum}`;
  };

  useEffect(() => {
    if (!isSurahFocused) {
      setSurahInputValue(getSurahLabel(activeSurahObj));
    }
  }, [activeSurah, surahs, isSurahFocused, language]);

  useEffect(() => {
    if (!isAyahFocused) {
      setAyahInputValue(getAyahLabel(activeAyah));
    }
  }, [activeAyah, isAyahFocused, language]);

  const handleSurahSelect = (surahNum: number) => {
    setActiveSurah(surahNum);
    setActiveAyah(null);
    setGlobalSearchQuery('');
    setSuggestions([]);
    fetchStats(surahNum);
    fetchVerses(surahNum);
    document.querySelector('main')?.scrollTo({ top: 0, behavior: 'instant' });
  };

  const handleSelectSurah = (surahNum: number) => {
    handleSurahSelect(surahNum);
    setIsSurahFocused(false);
  };

  const handleSelectAyah = (ayahNum: number | null) => {
    setActiveAyah(ayahNum);
    setIsAyahFocused(false);
  };

  const handleSurahFocus = () => {
    setIsSurahFocused(true);
    setSurahInputValue('');
    setSurahSearchQuery('');
  };

  const handleAyahFocus = () => {
    setIsAyahFocused(true);
    setAyahInputValue('');
    setAyahSearchQuery('');
  };

  const handleSurahChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSurahInputValue(val);
    setSurahSearchQuery(val);
  };

  const handleAyahChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setAyahInputValue(val);
    setAyahSearchQuery(val);
  };

  const handleSurahKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      if (filteredSurahs.length > 0) {
        handleSelectSurah(filteredSurahs[0].surah);
      } else {
        setIsSurahFocused(false);
      }
    } else if (e.key === 'Escape') {
      setIsSurahFocused(false);
    }
  };

  const handleAyahKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      if (ayahSearchQuery.trim() === '') {
        handleSelectAyah(null);
      } else {
        const parsed = parseInt(ayahSearchQuery, 10);
        if (!isNaN(parsed) && parsed >= 1 && parsed <= verses.length) {
          handleSelectAyah(parsed);
        } else if (filteredAyahs.length > 0) {
          handleSelectAyah(filteredAyahs[0]);
        } else {
          setIsAyahFocused(false);
        }
      }
    } else if (e.key === 'Escape') {
      setIsAyahFocused(false);
    }
  };

  useEffect(() => {
    const query = globalSearchQuery.trim();
    if (!query) {
      if (activeSurah === null) {
        setSuggestions([]);
        setActiveSurah(1);
        setActiveAyah(null);
        fetchStats(1);
        fetchVerses(1);
      }
      return;
    }

    const timer = setTimeout(() => {
      if (query.length >= 2) {
        setActiveSurah(null);
        setActiveAyah(null);
        setSurahInputValue('');
        setAyahInputValue('');
        setSurahSearchQuery('');
        setAyahSearchQuery('');
        searchEntries(query);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [globalSearchQuery]);

  const handleClearGlobalSearch = () => {
    setGlobalSearchQuery('');
    setSuggestions([]);
    setActiveSurah(1);
    setActiveAyah(null);
    fetchStats(1);
    fetchVerses(1);
  };

  const filteredSurahs = surahs.filter(s =>
    s.surah_name_ug.toLowerCase().includes(surahSearchQuery.toLowerCase()) ||
    s.surah_name_en.toLowerCase().includes(surahSearchQuery.toLowerCase()) ||
    s.surah.toString().includes(surahSearchQuery)
  );

  const ayahOptions = Array.from({ length: verses.length }, (_, i) => i + 1);
  const filteredAyahs = ayahOptions.filter(num =>
    num.toString().includes(ayahSearchQuery)
  );

  const prevSurahObj = surahs.find(s => s.surah === (activeSurah !== null ? activeSurah! - 1 : 0));
  const nextSurahObj = surahs.find(s => s.surah === (activeSurah !== null ? activeSurah! + 1 : 0));

  const activeEntries = globalSearchQuery.trim()
    ? suggestions
    : activeAyah !== null
      ? verses.filter(v => v.ayah === activeAyah)
      : verses;

  // Smart navigation calculations
  let prevDisabled = false;
  let nextDisabled = false;
  let prevLabel = '';
  let nextLabel = '';
  let handlePrevClick = () => {};
  let handleNextClick = () => {};

  if (globalSearchQuery.trim()) {
    prevDisabled = true;
    nextDisabled = true;
    prevLabel = t('common.previous') || 'ئالدىنقى';
    nextLabel = t('common.next') || 'كېيىنكى';
  } else if (activeSurah !== null && activeAyah !== null) {
    prevDisabled = activeAyah <= 1;
    nextDisabled = activeAyah >= verses.length;
    
    prevLabel = activeAyah > 1 
      ? t('quran.ayahItem', { count: activeAyah - 1 })
      : (t('common.previous') || 'ئالدىنقى');
    nextLabel = activeAyah < verses.length
      ? t('quran.ayahItem', { count: activeAyah + 1 })
      : (t('common.next') || 'كېيىنكى');
      
    handlePrevClick = () => {
      if (activeAyah > 1) {
        setActiveAyah(activeAyah - 1);
      }
    };
    handleNextClick = () => {
      if (activeAyah < verses.length) {
        setActiveAyah(activeAyah + 1);
      }
    };
  } else if (activeSurah !== null && activeAyah === null) {
    prevDisabled = !prevSurahObj;
    nextDisabled = !nextSurahObj;
    
    prevLabel = prevSurahObj 
      ? `${prevSurahObj.surah}. ${prevSurahObj.surah_name_ug}` 
      : (t('common.previous') || 'ئالدىنقى');
    nextLabel = nextSurahObj 
      ? `${nextSurahObj.surah}. ${nextSurahObj.surah_name_ug}` 
      : (t('common.next') || 'كېيىنكى');
      
    handlePrevClick = () => {
      if (prevSurahObj) {
        handleSurahSelect(prevSurahObj.surah);
      }
    };
    handleNextClick = () => {
      if (nextSurahObj) {
        handleSurahSelect(nextSurahObj.surah);
      }
    };
  }

  return (
    <div className="quran-page space-y-6 md:space-y-8 px-3 py-3 sm:px-6 md:px-0 animate-fade-in pb-20 relative" dir="rtl" lang="ug">
      {/* Backdrop overlay for dropdown click-away */}
      {(isSurahFocused || isAyahFocused) && (
        <div 
          className="fixed inset-0 z-20 cursor-default" 
          onClick={() => {
            setIsSurahFocused(false);
            setIsAyahFocused(false);
          }}
        />
      )}

      {/* Page Title Header */}
      <div className="flex items-center gap-3 md:gap-4 border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 pb-4 group">
        <div className="p-2 md:p-3 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 icon-shake">
          <BookOpen size={20} className="md:w-6 md:h-6" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-800 dark:text-slate-100 uyghur-text">
            {t('quran.title') || 'قۇرئان كەرىم'}
          </h1>
          <p className="text-xs text-slate-400 dark:text-slate-500 font-normal uyghur-text">
            {t('quran.subtitle')}
          </p>
        </div>
      </div>

      {/* Control Bar (Dropdowns and Search Box) */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between w-full gap-4 relative z-30">
        
        {/* Mobile: Search Box on top, Desktop: Search Box in middle */}
        <div className="order-1 md:order-2 flex-1 min-w-[280px]">
          <div className="relative w-full group">
            <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8] transition-colors z-10 font-bold">
              {isSearching ? (
                <RefreshCw className="animate-spin" size={16} />
              ) : (
                <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
              )}
            </div>
            <input
              type="text"
              value={globalSearchQuery}
              onFocus={() => {
                setIsSurahFocused(false);
                setIsAyahFocused(false);
              }}
              onChange={(e) => setGlobalSearchQuery(e.target.value)}
              className={`w-full pr-11 md:pr-14 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl uyghur-text outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] text-slate-800 dark:text-slate-100 transition-all shadow-sm placeholder:text-slate-300 dark:placeholder:text-slate-500 text-base md:pl-14 ${
                globalSearchQuery ? 'pl-11' : 'pl-4'
              }`}
              placeholder={t('quran.searchKeyword') || 'ھالقىلىق سۆز بويىچە ئىزدەش...'}
              dir="rtl"
            />
            <div className="absolute inset-y-0 left-3 md:left-4 flex items-center gap-1 md:gap-2 z-10">
              {globalSearchQuery && (
                <button 
                  type="button"
                  onClick={handleClearGlobalSearch}
                  className="p-1.5 md:p-2 text-slate-300 dark:text-slate-500 hover:text-red-500 dark:hover:text-red-400 transition-colors"
                  title={t('common.clear')}
                >
                  <X strokeWidth={2.5} className="w-4 h-4 md:w-5 md:h-5" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Dropdowns side-by-side on mobile and next to search on desktop */}
        <div className="order-2 md:order-1 flex items-center gap-3 w-full md:w-auto">
          {/* Surah Dropdown */}
          <div className="relative flex-1 md:flex-none md:w-64">
            <div className="flex items-center justify-between gap-2 px-3.5 py-2.5 md:py-3 bg-white dark:bg-slate-900 rounded-2xl border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 focus-within:border-[#0369a1] dark:focus-within:border-[#38bdf8] transition-all shadow-sm">
              <input
                type="text"
                value={surahInputValue}
                onFocus={handleSurahFocus}
                onChange={handleSurahChange}
                onKeyDown={handleSurahKeyDown}
                placeholder={t('quran.selectSurah') || 'سۈرە تاللاڭ'}
                className="w-full bg-transparent border-none outline-none text-slate-800 dark:text-slate-100 text-base md:text-sm font-semibold uyghur-text"
                dir="rtl"
              />
              <ChevronDown size={16} className="text-[#0369a1] dark:text-[#38bdf8] opacity-70 pointer-events-none" />
            </div>

            {/* Surah List Dropdown Panel */}
            {isSurahFocused && surahs.length > 0 && (
              <div className="absolute right-0 left-0 mt-2 max-h-[300px] overflow-y-auto bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-[#0369a1]/15 dark:border-[#38bdf8]/20 rounded-2xl shadow-xl z-40 divide-y divide-slate-50 dark:divide-slate-800 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden animate-fade-in animate-slide-down">
                {filteredSurahs.length > 0 ? (
                  filteredSurahs.map((surah) => (
                    <button
                      key={surah.surah}
                      onClick={() => handleSelectSurah(surah.surah)}
                      className={`w-full text-right px-4 py-3 text-sm uyghur-text transition-all flex items-center justify-between hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/5 ${
                        activeSurah === surah.surah 
                          ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] font-semibold' 
                          : 'text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <span>{t('quran.surahItem', { number: surah.surah, name: language === 'ug' ? surah.surah_name_ug : surah.surah_name_en })}</span>
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-3 text-sm text-slate-400 dark:text-slate-500 text-center uyghur-text">
                    {t('quran.noSurahFound')}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Ayah Dropdown */}
          <div className="relative flex-1 md:flex-none md:w-44">
            <div className={`flex items-center justify-between gap-2 px-3.5 py-2.5 md:py-3 bg-white dark:bg-slate-900 rounded-2xl border-2 transition-all shadow-sm ${
              activeSurah === null 
                ? 'border-slate-100 dark:border-slate-800 opacity-50 pointer-events-none'
                : 'border-[#0369a1]/10 dark:border-[#38bdf8]/10 focus-within:border-[#0369a1] dark:focus-within:border-[#38bdf8]'
            }`}>
              <input
                type="text"
                value={ayahInputValue}
                onFocus={handleAyahFocus}
                onChange={handleAyahChange}
                onKeyDown={handleAyahKeyDown}
                disabled={activeSurah === null}
                placeholder={t('quran.selectAyah') || 'ئايەت تاللاڭ'}
                className="w-full bg-transparent border-none outline-none text-slate-800 dark:text-slate-100 text-base md:text-sm font-semibold uyghur-text"
                dir="rtl"
              />
              <ChevronDown size={16} className="text-[#0369a1] dark:text-[#38bdf8] opacity-70 pointer-events-none" />
            </div>

            {/* Ayah List Dropdown Panel */}
            {isAyahFocused && activeSurah !== null && (
              <div className="absolute right-0 left-0 mt-2 max-h-[300px] overflow-y-auto bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-[#0369a1]/15 dark:border-[#38bdf8]/20 rounded-2xl shadow-xl z-40 divide-y divide-slate-50 dark:divide-slate-800 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden animate-fade-in animate-slide-down">
                <button
                  onClick={() => handleSelectAyah(null)}
                  className={`w-full text-right px-4 py-3 text-sm uyghur-text transition-all flex items-center justify-between hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/5 ${
                    activeAyah === null 
                      ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] font-semibold' 
                      : 'text-slate-700 dark:text-slate-300'
                  }`}
                >
                  {t('quran.allAyahs') || 'ھەممە ئايەت'}
                </button>
                {filteredAyahs.length > 0 ? (
                  filteredAyahs.map((ayahNum) => (
                    <button
                      key={ayahNum}
                      onClick={() => handleSelectAyah(ayahNum)}
                      className={`w-full text-right px-4 py-3 text-sm uyghur-text transition-all flex items-center justify-between hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/5 ${
                        activeAyah === ayahNum 
                          ? 'bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] font-semibold' 
                          : 'text-slate-700 dark:text-slate-300'
                      }`}
                    >
                      <span>{t('quran.ayahItem', { count: ayahNum })}</span>
                    </button>
                  ))
                ) : (
                  <div className="px-4 py-3 text-sm text-slate-400 dark:text-slate-500 text-center uyghur-text">
                    {t('quran.noAyahFound')}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Stats Badge */}
        {stats && (
          <div className="order-3 md:order-3 flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] dark:text-[#38bdf8] bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3.5 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap self-end md:self-auto">
            <Hash size={12} className="md:w-[14px] md:h-[14px]" />
            {globalSearchQuery.trim() 
              ? t('quran.totalVerses', { count: suggestions.length.toLocaleString() }) || `${suggestions.length} ئايەت`
              : activeAyah !== null
                ? t('quran.totalVerses', { count: '1' }) || '1 ئايەت'
                : t('quran.totalVerses', { count: stats.total_entries.toLocaleString() }) || `${stats.total_entries} ئايەت`
            }
          </div>
        )}
      </div>

      {/* Verses List Content */}
      <div className="space-y-4">
        {isLoadingVerses && activeEntries.length === 0 && (
           <div className="flex justify-center py-20">
              <Loader2 size={40} className="animate-spin text-[#0369a1]/20" />
           </div>
        )}

        {globalSearchQuery.trim() && !isSearching && suggestions.length === 0 && (
          <div className="glass-panel rounded-[24px] md:rounded-[32px] py-8 md:py-12 px-4 md:px-8 flex flex-col items-center justify-center gap-3 md:gap-4 text-center animate-fade-in shadow-lg border border-[#0369a1]/10">
             <div className="p-3 md:p-4 bg-amber-50 dark:bg-amber-500/10 text-amber-500 dark:text-amber-400 rounded-full shadow-inner ring-4 ring-amber-50/50 dark:ring-amber-500/10">
                <AlertCircle className="w-6 h-6 md:w-8 md:h-8" />
             </div>
             <div className="space-y-1">
                <h3 className="text-lg md:text-xl font-normal text-[#1a1a1a] dark:text-slate-100">
                  {t('quran.ayahNotFound') || 'ئايەت تېپىلمىدى.'}
                </h3>
                <p className="text-slate-400 font-bold text-[9px] md:text-xs uppercase tracking-widest opacity-60 line-clamp-1">
                  {globalSearchQuery}
                </p>
             </div>
          </div>
        )}

        {activeEntries.length > 0 && (
          <div className="space-y-4">
            <div className="glass-panel rounded-[32px] p-4 md:p-6 overflow-hidden shadow-xl animate-fade-in border border-[#0369a1]/5 dark:border-[#38bdf8]/10 bg-white dark:bg-slate-900/60">
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {activeEntries.map((entry) => (
                  <div 
                    key={entry.id} 
                    className="py-6 md:py-8 first:pt-2 last:pb-2 flex flex-col gap-4 w-full"
                  >
                    {/* Arabic Text (Centered, large, Adobe Arabic Font) */}
                    <div 
                      className="text-right text-3xl md:text-4xl text-slate-900 dark:text-slate-100 leading-[2] md:leading-[2.2] font-normal w-full arabic-text"
                      dir="rtl"
                      lang="ar"
                    >
                      {normalizeArabicWithAyah(entry.text_ar, entry.ayah)}
                    </div>

                    {/* Uyghur Text */}
                    <div 
                      className="uyghur-text text-base md:text-lg text-slate-700 dark:text-slate-200 leading-relaxed text-right mt-2"
                      dir="rtl"
                      lang="ug"
                    >
                      {formatQuranAyahUg(entry.text_ug)}
                    </div>

                    {/* English Text */}
                    <div 
                      className="text-left text-sm md:text-base text-slate-500 dark:text-slate-400 leading-relaxed font-sans mt-1"
                      dir="ltr"
                      lang="en"
                    >
                      {entry.text_en}
                    </div>

                    {/* Verse Badge / Info */}
                    <div className="flex justify-between items-center mt-2 pt-3 border-t border-slate-50 dark:border-slate-800">
                      <span className="text-[11px] md:text-xs text-[#0369a1] dark:text-[#38bdf8] font-semibold bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 px-3 py-1 rounded-full border border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-sm whitespace-nowrap self-end uyghur-text">
                        {t('quran.badgeTemplate', { 
                          surah: entry.surah, 
                          surahName: language === 'ug' ? entry.surah_name_ug : entry.surah_name_en, 
                          ayah: entry.ayah 
                        })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {!isLoadingVerses && (
          <div className="flex items-center justify-between gap-3 pt-2">
            <button
              onClick={handlePrevClick}
              disabled={prevDisabled}
              className="flex-1 flex items-center gap-2 justify-center px-4 py-3 md:py-3.5 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl text-[#0369a1] dark:text-[#38bdf8] font-semibold text-sm hover:border-[#0369a1]/30 dark:hover:border-[#38bdf8]/30 transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none uyghur-text shadow-sm"
            >
              <ChevronRight size={18} strokeWidth={2.5} />
              <span className="truncate">{prevLabel}</span>
            </button>
            <button
              onClick={handleNextClick}
              disabled={nextDisabled}
              className="flex-1 flex items-center gap-2 justify-center px-4 py-3 md:py-3.5 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl text-[#0369a1] dark:text-[#38bdf8] font-semibold text-sm hover:border-[#0369a1]/30 dark:hover:border-[#38bdf8]/30 transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none uyghur-text shadow-sm"
            >
              <span className="truncate">{nextLabel}</span>
              <ChevronLeft size={18} strokeWidth={2.5} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default QuranView;
