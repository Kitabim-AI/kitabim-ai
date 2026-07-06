import {
  AlertCircle,
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

const normalizeArabic = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/\u06E1/g, '\u0652') // Uthmanic Sukun -> Standard Sukun
    .replace(/\u0671/g, '\u0627') // Alif Wasla -> Standard Alif
    .replace(/[\u06D6-\u06DC\u06DF-\u06E0\u06E2-\u06ED]/g, '') // Remove Uthmanic signs that disrupt cursive connections
    ;
};

export const QuranView: React.FC = () => {
  const { t, language } = useI18n();
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<QuranAyahEntry[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [surahs, setSurahs] = useState<SurahEntry[]>([]);
  const [activeSurah, setActiveSurah] = useState<number>(1);
  const [verses, setVerses] = useState<QuranAyahEntry[]>([]);
  const [isLoadingVerses, setIsLoadingVerses] = useState(false);
  const [stats, setStats] = useState<{ total_entries: number } | null>(null);

  // Merged Search/Dropdown states
  const [isFocused, setIsFocused] = useState(false);
  const [dropdownSearch, setDropdownSearch] = useState('');
  const [inputValue, setInputValue] = useState('');

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

  useEffect(() => {
    const timer = setTimeout(() => {
      searchEntries(searchQuery);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const activeSurahObj = surahs.find(s => s.surah === activeSurah);

  useEffect(() => {
    if (!isFocused && !searchQuery) {
      if (activeSurahObj) {
        setInputValue(`${activeSurahObj.surah}. ${activeSurahObj.surah_name_ug} / ${normalizeArabic(activeSurahObj.surah_name_ar)}`);
      }
    }
  }, [activeSurah, surahs, isFocused, searchQuery]);

  const handleSurahSelect = (surahNum: number) => {
    setActiveSurah(surahNum);
    setSearchQuery('');
    setSuggestions([]);
    fetchStats(surahNum);
    fetchVerses(surahNum);
  };

  const handleInputFocus = () => {
    setIsFocused(true);
    setInputValue('');
    setDropdownSearch('');
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputValue(val);
    setDropdownSearch(val);
    setSearchQuery(val);
  };

  const handleSelectSurah = (surahNum: number) => {
    handleSurahSelect(surahNum);
    setIsFocused(false);
  };

  const handleCloseDropdown = () => {
    setIsFocused(false);
    if (!searchQuery) {
      if (activeSurahObj) {
        setInputValue(`${activeSurahObj.surah}. ${activeSurahObj.surah_name_ug} / ${normalizeArabic(activeSurahObj.surah_name_ar)}`);
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      setIsFocused(false);
    }
  };

  const filteredSurahs = surahs.filter(s => 
    s.surah_name_ug.toLowerCase().includes(dropdownSearch.toLowerCase()) ||
    s.surah_name_en.toLowerCase().includes(dropdownSearch.toLowerCase()) ||
    s.surah.toString().includes(dropdownSearch)
  );

  const activeEntries = searchQuery.trim() ? suggestions : verses;

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in pb-20 relative" dir="rtl" lang="ug">
      {/* Backdrop overlay for dropdown click-away */}
      {isFocused && (
        <div 
          className="fixed inset-0 z-20 cursor-default" 
          onClick={handleCloseDropdown}
        />
      )}

      {/* Page Title Header */}
      <div className="flex items-center gap-3 md:gap-4 border-b border-[#0369a1]/10 pb-4">
        <div className="p-3 bg-[#0369a1]/10 rounded-2xl text-[#0369a1]">
          <BookOpen size={24} strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-800 uyghur-text">
            {t('quran.title') || 'قۇرئان كەرىم'}
          </h1>
          <p className="text-xs text-slate-400 font-normal uyghur-text">
            {t('quran.subtitle')}
          </p>
        </div>
      </div>

      {/* Merged Search & Surah Selector Box */}
      <div className="flex flex-col-reverse md:flex-row items-center justify-between w-full gap-3 md:gap-4 relative z-30">
        <div className="relative flex-1 lg:flex-none lg:w-[45%] group w-full">
          <div className="absolute inset-y-0 right-4 md:right-5 flex items-center pointer-events-none text-[#0369a1] transition-colors z-10 font-bold">
            {isSearching ? (
              <RefreshCw className="animate-spin" size={16} />
            ) : (
              <Search size={18} strokeWidth={3} className="md:w-5 md:h-5" />
            )}
          </div>
          <input
            type="text"
            value={inputValue}
            onFocus={handleInputFocus}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            className="w-full pr-11 md:pr-14 pl-20 md:pl-28 py-2.5 md:py-3 bg-white border-2 border-[#0369a1]/10 rounded-2xl uyghur-text outline-none focus:border-[#0369a1] transition-all shadow-sm placeholder:text-slate-300 text-base"
            placeholder={t('quran.searchPlaceholder') || 'قۇرئاندىن سۈرە ياكى ئايەت ئىزدەش...'}
            dir="rtl"
          />
          <div className="absolute inset-y-0 left-3 md:left-4 flex items-center gap-1 md:gap-2 z-10">
            {(searchQuery || isFocused) && (
              <button 
                onClick={() => {
                  setSearchQuery('');
                  setInputValue('');
                  setIsFocused(false);
                }}
                className="p-1.5 md:p-2 text-slate-300 hover:text-red-500 transition-colors"
                title={t('common.clear')}
              >
                <X strokeWidth={2.5} className="w-4 h-4 md:w-5 md:h-5" />
              </button>
            )}
          </div>

          {/* Surah List Dropdown Panel */}
          {isFocused && surahs.length > 0 && (
            <div className="absolute right-0 left-0 mt-2 max-h-[300px] overflow-y-auto bg-white/95 backdrop-blur-md border border-[#0369a1]/15 rounded-2xl shadow-xl z-40 divide-y divide-slate-50 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden animate-fade-in">
              <div className="px-4 py-2 text-xs font-bold text-[#0369a1] bg-[#0369a1]/5 text-right uyghur-text">
                سۈرىلەر
              </div>
              {filteredSurahs.length > 0 ? (
                filteredSurahs.map((surah) => (
                  <button
                    key={surah.surah}
                    onClick={() => handleSelectSurah(surah.surah)}
                    className={`w-full text-right px-4 py-3 text-sm uyghur-text transition-all flex items-center justify-between hover:bg-[#0369a1]/5 ${
                      activeSurah === surah.surah 
                        ? 'bg-[#0369a1]/10 text-[#0369a1] font-semibold' 
                        : 'text-slate-700'
                    }`}
                  >
                    <span>{surah.surah}. {surah.surah_name_ug}</span>
                    <span className="text-xs text-slate-400 font-semibold arabic-text" dir="rtl">{normalizeArabic(surah.surah_name_ar)}</span>
                  </button>
                ))
              ) : (
                <div className="px-4 py-3 text-sm text-slate-400 text-center uyghur-text">
                  ماس كېلىدىغان سۈرە تېپىلمىدى (ئايەت ئىزدەش ئۈچۈن Enter بېسىڭ)
                </div>
              )}
            </div>
          )}
        </div>

        {stats && (
          <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] bg-[#0369a1]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 shadow-sm whitespace-nowrap self-end md:self-auto md:mr-auto">
            <Hash size={12} className="md:w-[14px] md:h-[14px]" />
            {searchQuery.trim() 
              ? t('quran.totalVerses', { count: suggestions.length.toLocaleString() }) || `${suggestions.length} ئايەت`
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

        {searchQuery.trim() && !isSearching && suggestions.length === 0 && (
          <div className="glass-panel rounded-[24px] md:rounded-[32px] py-8 md:py-12 px-4 md:px-8 flex flex-col items-center justify-center gap-3 md:gap-4 text-center animate-fade-in shadow-lg border border-[#0369a1]/10">
             <div className="p-3 md:p-4 bg-amber-50 text-amber-500 rounded-full shadow-inner ring-4 ring-amber-50/50">
                <AlertCircle className="w-6 h-6 md:w-8 md:h-8" />
             </div>
             <div className="space-y-1">
                <h3 className="text-lg md:text-xl font-normal text-[#1a1a1a]">
                  {t('quran.ayahNotFound') || 'ئايەت تېپىلمىدى.'}
                </h3>
                <p className="text-slate-400 font-bold text-[9px] md:text-xs uppercase tracking-widest opacity-60 line-clamp-1">
                  {searchQuery}
                </p>
             </div>
          </div>
        )}

        {activeEntries.length > 0 && (
          <div className="space-y-4">
            <div className="glass-panel rounded-[32px] p-4 md:p-6 overflow-hidden shadow-xl animate-fade-in border border-[#0369a1]/5 bg-white">
              <div className="divide-y divide-slate-100">
                {activeEntries.map((entry) => (
                  <div 
                    key={entry.id} 
                    className="py-6 md:py-8 first:pt-2 last:pb-2 flex flex-col gap-4 w-full"
                  >
                    {/* Arabic Text (Centered, large, Adobe Arabic Font) */}
                    <div 
                      className="text-right text-3xl md:text-4xl text-slate-900 leading-[2] md:leading-[2.2] font-normal text-right w-full arabic-text"
                      dir="rtl"
                      lang="ar"
                    >
                      {normalizeArabic(entry.text_ar)}
                    </div>

                    {/* Uyghur Text */}
                    <div 
                      className="uyghur-text text-base md:text-lg text-slate-700 leading-relaxed text-right mt-2"
                      dir="rtl"
                      lang="ug"
                    >
                      {entry.text_ug}
                    </div>

                    {/* English Text */}
                    <div 
                      className="text-left text-sm md:text-base text-slate-500 leading-relaxed font-sans mt-1"
                      dir="ltr"
                      lang="en"
                    >
                      {entry.text_en}
                    </div>

                    {/* Verse Badge / Info */}
                    <div className="flex justify-between items-center mt-2 pt-3 border-t border-slate-50">
                      <span className="text-[11px] md:text-xs text-[#0369a1] font-semibold bg-[#0369a1]/10 px-3 py-1 rounded-full border border-[#0369a1]/20 shadow-sm whitespace-nowrap self-end uyghur-text">
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
      </div>
    </div>
  );
};

export default QuranView;
