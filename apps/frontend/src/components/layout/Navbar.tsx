import { BookA, BookOpen, BookOpenCheck, Bot, HeartHandshake, Home, LibraryBig, Menu, Monitor, Moon, Network, RefreshCw, Search, Settings, Sun, Upload, X } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { useAppContext } from '../../context/AppContext';
import { useTheme } from '../../context/ThemeContext';
import { useAuth, useIsEditor } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { AuthButton } from '../auth';

export const Navbar: React.FC = () => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isAuthenticated } = useAuth();
  const isEditor = useIsEditor();
  const { t } = useI18n();
  const {
    view,
    previousView,
    setView,
    setSearchQuery,
    isGlobalSearchOpen,
    setIsGlobalSearchOpen,
    homeSearchQuery,
    setHomeSearchQuery,
    bookActions,
    chat,
    setPage,
    isLoading,
    activeTab
  } = useAppContext();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const [themeDropdownOpen, setThemeDropdownOpen] = useState(false);
  const themeRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (themeRef.current && !themeRef.current.contains(e.target as Node)) {
        setThemeDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const getThemeIcon = () => {
    switch (theme) {
      case 'light': return <Sun size={22} className="text-[#0369a1] dark:text-[#38bdf8]" />;
      case 'dark': return <Moon size={22} className="text-[#0369a1] dark:text-[#38bdf8]" />;
      case 'system': return <Monitor size={22} className="text-[#0369a1] dark:text-[#38bdf8]" />;
    }
  };

  const handleNavClick = (callback: () => void) => {
    callback();
    setMobileMenuOpen(false);
  };

  return (
    <>
      <nav className="fixed top-0 left-0 right-0 px-4 sm:px-6 md:px-8 lg:px-8 xl:px-10 py-1.5 sm:py-2 flex items-center justify-between z-[100] transition-all duration-300" dir="rtl">
        {/* Glass Backdrop - Matching Prototype */}
        <div className="absolute inset-0 bg-white/75 backdrop-blur-[20px] border-b border-[rgba(255,193,7,0.2)] shadow-[0_4px_30px_rgba(117,197,240,0.1),0_1px_0_rgba(255,255,255,0.8)_inset]"
          style={{ backdropFilter: 'blur(20px) saturate(180%)', WebkitBackdropFilter: 'blur(20px) saturate(180%)' }} />

        {/* Gradient Border at Bottom - Matching Prototype */}
        <div className="absolute -bottom-px left-0 right-0 h-px bg-gradient-to-l from-transparent via-[rgba(255,193,7,0.5)] to-transparent"
          style={{ background: 'linear-gradient(270deg, transparent, rgba(255, 193, 7, 0.5), rgba(156, 39, 176, 0.3), transparent)' }} />

        <div className="relative flex items-center gap-3 sm:gap-4 md:gap-3 lg:gap-4 xl:gap-5">
          <div className="flex items-center h-[48px] gap-2 sm:gap-3 cursor-pointer group transition-transform duration-300 hover:-translate-y-0.5" onClick={() => setView('home')}>
            <div className="flex-shrink-0 w-9 h-9 md:w-11 md:h-11 flex items-center justify-center rounded-xl md:rounded-2xl shadow-[0_4px_20px_rgba(255,193,7,0.4),0_8px_40px_rgba(156,39_176,0.2),inset_0_1px_0_rgba(255,255,255,0.4)] transition-all duration-300 relative overflow-hidden group-hover:shadow-[0_6px_20px_rgba(3,105,161,0.5)] icon-shake"
              style={{
                background: 'linear-gradient(135deg, #FFD54F 0%, #FF9800 50%, #9C27B0 100%)'
              }}>
              <div className="absolute inset-0 opacity-30"
                style={{
                  background: 'repeating-conic-gradient(from 0deg at 50% 50%, transparent 0deg, transparent 10deg, rgba(255, 255, 255, 0.1) 10deg, rgba(255, 255, 255, 0.1) 20deg)'
                }} />
              <BookOpen size={24} className="md:w-7 md:h-7 text-white relative z-10" strokeWidth={2} />
            </div>
            <span dir="ltr" className="flex items-center font-semibold text-[#1a1a1a] text-[24px] mt-[12px] md:text-[28px] md:mt-[14px] lg:text-[30px] lg:mt-[15px] xl:text-[32px] xl:mt-[16px] tracking-tight">
              Kitabim<span className="text-[#0369a1]">.AI</span>
            </span>
          </div>

          {/* Desktop/Tablet Navigation - hide icons on md, show on lg+ */}
          <div className="hidden lg:flex items-center gap-1">
            <NavButton
              active={view === 'home'}
              onClick={() => setView('home')}
              icon={<Home size={20} strokeWidth={2.5} />}
              label={t('nav.home')}
            />
            <NavButton
              active={view === 'library' || (view === 'reader' && previousView === 'library')}
              onClick={() => { setSearchQuery(''); setView('library'); }}
              icon={<LibraryBig size={20} strokeWidth={2.5} />}
              label={t('nav.library')}
            />
            <NavButton
              active={view === 'global-chat'}
              onClick={() => { setSearchQuery(''); setView('global-chat'); chat.clearChat(); }}
              icon={<Bot size={24} strokeWidth={2.5} />}
              label={t('nav.globalChat')}
            />
            <NavButton
              active={view === 'graph'}
              onClick={() => { setSearchQuery(''); setView('graph'); }}
              icon={<Network size={20} strokeWidth={2.5} />}
              label={t('nav.graph')}
            />
            <NavButton
              active={view === 'dictionary'}
              onClick={() => { setSearchQuery(''); setView('dictionary'); }}
              icon={<BookA size={20} strokeWidth={2.5} />}
              label={t('nav.dictionary')}
            />
            {isEditor && (
              <NavButton
                active={view === 'spell-check'}
                onClick={() => { setSearchQuery(''); setView('spell-check'); }}
                icon={<BookOpenCheck size={20} strokeWidth={2.5} />}
                label={t('nav.spellCheck')}
              />
            )}
            <NavButton
              active={view === 'quran'}
              onClick={() => { setSearchQuery(''); setView('quran'); }}
              icon={<BookOpen size={20} strokeWidth={2.5} />}
              label={t('nav.quran')}
            />
            {isEditor && (
              <NavButton
                active={view === 'admin' || (view === 'reader' && previousView === 'admin')}
                onClick={() => { setSearchQuery(''); setView('admin'); setPage(1); }}
                icon={<Settings size={20} strokeWidth={2.5} />}
                label={t('nav.admin')}
              />
            )}
            <NavButton
              active={view === 'join-us'}
              onClick={() => { setSearchQuery(''); setView('join-us'); }}
              icon={<HeartHandshake size={20} strokeWidth={2.5} />}
              label={t('nav.joinUs')}
            />
          </div>
        </div>

        <div className="relative flex items-center gap-2 lg:gap-3">
          {/* Search Toggle Button */}
          <button
            onClick={() => setIsGlobalSearchOpen(true)}
            className="group relative flex items-center justify-center w-9 h-9 md:w-11 md:h-11 bg-white/50 dark:bg-slate-900/50 backdrop-blur-md border border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-xl md:rounded-2xl hover:border-[#0369a1] dark:hover:border-[#38bdf8] hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/5 transition-all shadow-sm overflow-hidden active:scale-90"
            title={t('library.searchPlaceholder')}
          >
            <Search size={22} className="text-[#0369a1] dark:text-[#38bdf8] group-hover:scale-110 transition-transform" strokeWidth={2.5} />
            <div className="absolute inset-0 bg-gradient-to-tr from-[#0369a1]/0 to-[#0369a1]/10 opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>

          {/* Theme Toggle Dropdown */}
          <div className="relative" ref={themeRef}>
            <button
              onClick={() => setThemeDropdownOpen(!themeDropdownOpen)}
              className="group relative flex items-center justify-center w-9 h-9 md:w-11 md:h-11 bg-white/50 dark:bg-slate-900/50 backdrop-blur-md border border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-xl md:rounded-2xl hover:border-[#0369a1] dark:hover:border-[#38bdf8] hover:bg-[#0369a1]/5 dark:hover:bg-[#38bdf8]/5 transition-all shadow-sm overflow-hidden active:scale-90"
              title={t('theme.selector') || 'تېما'}
            >
              {getThemeIcon()}
              <div className="absolute inset-0 bg-gradient-to-tr from-[#0369a1]/0 to-[#0369a1]/10 opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>

            {themeDropdownOpen && (
              <div className="absolute left-0 mt-2 w-32 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl shadow-xl z-[110] py-1.5 animate-fade-in">
                <button
                  onClick={() => { setTheme('light'); setThemeDropdownOpen(false); }}
                  className={`w-full px-3 py-2 text-sm flex items-center gap-2.5 transition-all text-right ${theme === 'light' ? 'bg-[#0369a1]/10 text-[#0369a1] dark:text-[#38bdf8] font-medium' : 'text-slate-600 dark:text-slate-300 hover:bg-[#0369a1]/5'}`}
                  dir="rtl"
                >
                  <Sun size={16} />
                  <span className="uyghur-text">{t('theme.light') || 'يورۇق'}</span>
                </button>
                <button
                  onClick={() => { setTheme('dark'); setThemeDropdownOpen(false); }}
                  className={`w-full px-3 py-2 text-sm flex items-center gap-2.5 transition-all text-right ${theme === 'dark' ? 'bg-[#0369a1]/10 text-[#0369a1] dark:text-[#38bdf8] font-medium' : 'text-slate-600 dark:text-slate-300 hover:bg-[#0369a1]/5'}`}
                  dir="rtl"
                >
                  <Moon size={16} />
                  <span className="uyghur-text">{t('theme.dark') || 'قاراڭغۇ'}</span>
                </button>
                <button
                  onClick={() => { setTheme('system'); setThemeDropdownOpen(false); }}
                  className={`w-full px-3 py-2 text-sm flex items-center gap-2.5 transition-all text-right ${theme === 'system' ? 'bg-[#0369a1]/10 text-[#0369a1] dark:text-[#38bdf8] font-medium' : 'text-slate-600 dark:text-slate-300 hover:bg-[#0369a1]/5'}`}
                  dir="rtl"
                >
                  <Monitor size={16} />
                  <span className="uyghur-text">{t('theme.system') || 'ئاپتوماتىك'}</span>
                </button>
              </div>
            )}
          </div>

          {isEditor && (
            <>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={bookActions.isCheckingGlobal}
                title={t('nav.addBook')}
                className="group relative flex items-center justify-center w-9 h-9 md:w-11 md:h-11 bg-white/50 backdrop-blur-md border border-[#0369a1]/10 rounded-xl md:rounded-2xl hover:border-[#0369a1] hover:bg-[#0369a1]/5 transition-all shadow-sm overflow-hidden active:scale-90"
                aria-busy={bookActions.isCheckingGlobal}
              >
                {bookActions.isCheckingGlobal ? (
                  <RefreshCw size={22} strokeWidth={2.5} className="text-[#0369a1] relative z-10 animate-spin" />
                ) : (
                  <Upload size={22} strokeWidth={2.5} className="text-[#0369a1] relative z-10 group-hover:scale-110 transition-transform" />
                )}
                <div className="absolute inset-0 bg-gradient-to-tr from-[#0369a1]/0 to-[#0369a1]/10 opacity-0 group-hover:opacity-100 transition-opacity" />
              </button>
              <input
                type="file"
                ref={fileInputRef}
                onChange={bookActions.handleFileUpload}
                accept="application/pdf,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                className="hidden"
              />
            </>
          )}
          <div className="hidden sm:block">
            <AuthButton onLogout={() => setView('home')} />
          </div>

          {/* Mobile Menu Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="lg:hidden flex items-center justify-center w-9 h-9 rounded-xl hover:bg-[#0369a1]/10 text-[#0369a1] border border-[#0369a1]/10 transition-all relative z-10"
          >
            {mobileMenuOpen ? <X size={24} strokeWidth={2.5} /> : <Menu size={24} strokeWidth={2.5} />}
          </button>
        </div>
      </nav>

      {/* Mobile Menu Overlay */}
      {mobileMenuOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/20 backdrop-blur-sm z-[90] lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />

          {/* Menu Panel */}
          <div className="fixed top-[72px] left-0 right-0 bg-white/95 dark:bg-slate-900/95 backdrop-blur-2xl border-b border-[#0369a1]/10 dark:border-[#38bdf8]/10 shadow-2xl z-[95] lg:hidden animate-fade-in" dir="rtl">
            <div className="px-4 py-6 space-y-2">
              <MobileNavButton
                active={view === 'home'}
                onClick={() => handleNavClick(() => setView('home'))}
                icon={<Home size={20} strokeWidth={2.5} />}
                label={t('nav.home')}
              />
              <MobileNavButton
                active={view === 'library' || (view === 'reader' && previousView === 'library')}
                onClick={() => handleNavClick(() => setView('library'))}
                icon={<LibraryBig size={20} strokeWidth={2.5} />}
                label={t('nav.library')}
              />
              <MobileNavButton
                active={view === 'global-chat'}
                onClick={() => handleNavClick(() => { setView('global-chat'); chat.clearChat(); })}
                icon={<Bot size={24} strokeWidth={2.5} />}
                label={t('nav.globalChat')}
              />
              <MobileNavButton
                active={view === 'graph'}
                onClick={() => handleNavClick(() => setView('graph'))}
                icon={<Network size={20} strokeWidth={2.5} />}
                label={t('nav.graph')}
              />
              <MobileNavButton
                active={view === 'dictionary'}
                onClick={() => handleNavClick(() => setView('dictionary'))}
                icon={<BookA size={20} strokeWidth={2.5} />}
                label={t('nav.dictionary')}
              />
              {isEditor && (
                <MobileNavButton
                  active={view === 'spell-check'}
                  onClick={() => handleNavClick(() => setView('spell-check'))}
                  icon={<BookOpenCheck size={20} strokeWidth={2.5} />}
                  label={t('nav.spellCheck')}
                />
              )}
              <MobileNavButton
                active={view === 'quran'}
                onClick={() => handleNavClick(() => setView('quran'))}
                icon={<BookOpen size={20} strokeWidth={2.5} />}
                label={t('nav.quran')}
              />
              {isEditor && (
                <MobileNavButton
                  active={view === 'admin' || (view === 'reader' && previousView === 'admin')}
                  onClick={() => handleNavClick(() => { setView('admin'); setPage(1); })}
                  icon={<Settings size={20} strokeWidth={2.5} />}
                  label={t('nav.admin')}
                />
              )}
              <MobileNavButton
                active={view === 'join-us'}
                onClick={() => handleNavClick(() => setView('join-us'))}
                icon={<HeartHandshake size={20} strokeWidth={2.5} />}
                label={t('nav.joinUs')}
              />

              {/* Mobile Theme Selector */}
              <div className="pt-4 border-t border-[#0369a1]/10 dark:border-[#38bdf8]/10 flex items-center justify-between px-2">
                <span className="text-sm font-medium text-slate-500 dark:text-slate-400 uyghur-text">{t('theme.title') || 'تېما'}:</span>
                <div className="flex bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 rounded-xl p-1 gap-1 border border-[#0369a1]/10 dark:border-[#38bdf8]/10">
                  <button
                    onClick={() => setTheme('light')}
                    className={`p-2 rounded-lg transition-all flex items-center gap-1.5 ${theme === 'light' ? 'bg-[#0369a1] text-white shadow-md' : 'text-slate-500 dark:text-slate-400 hover:text-[#0369a1]'}`}
                    title={t('theme.light') || 'Light'}
                  >
                    <Sun size={16} />
                    <span className="text-xs uyghur-text">{t('theme.light') || 'يورۇق'}</span>
                  </button>
                  <button
                    onClick={() => setTheme('dark')}
                    className={`p-2 rounded-lg transition-all flex items-center gap-1.5 ${theme === 'dark' ? 'bg-[#0369a1] text-white shadow-md' : 'text-slate-500 dark:text-slate-400 hover:text-[#0369a1]'}`}
                    title={t('theme.dark') || 'Dark'}
                  >
                    <Moon size={16} />
                    <span className="text-xs uyghur-text">{t('theme.dark') || 'قاراڭغۇ'}</span>
                  </button>
                  <button
                    onClick={() => setTheme('system')}
                    className={`p-2 rounded-lg transition-all flex items-center gap-1.5 ${theme === 'system' ? 'bg-[#0369a1] text-white shadow-md' : 'text-slate-500 dark:text-slate-400 hover:text-[#0369a1]'}`}
                    title={t('theme.system') || 'System'}
                  >
                    <Monitor size={16} />
                    <span className="text-xs uyghur-text">{t('theme.system') || 'ئاپتوماتىك'}</span>
                  </button>
                </div>
              </div>

              {/* Auth section in mobile menu */}
              <div className="pt-4 border-t border-[#0369a1]/10 dark:border-[#38bdf8]/10 sm:hidden">
                <AuthButton onLogout={() => { setView('home'); setMobileMenuOpen(false); }} dropdownSide="right" inline />
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
};

const NavButton: React.FC<{
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  showIcon?: 'always' | 'lg';
}> = ({ active, onClick, icon, label, showIcon = 'always' }) => (
  <button
    onClick={onClick}
    title={label}
    className={`relative px-2.5 lg:px-3 xl:px-3 2xl:px-4 h-[36px] md:h-[42px] rounded-xl text-sm lg:text-base font-normal flex items-center gap-2 transition-all duration-300 group ${active
      ? 'text-[#0369a1] bg-[#0369a1]/10 shadow-[inset_0_0_0_1px_rgba(3,105,161,0.2)]'
      : 'text-[#64748b] hover:bg-[#0369a1]/5 hover:text-[#0369a1]'
      }`}
  >
    <div className="flex items-center gap-2 relative z-10">
      <span className={`${showIcon === 'lg' ? 'hidden lg:inline-flex' : 'inline-flex'} items-center transition-transform group-hover:scale-110 ${active ? 'text-[#0369a1]' : ''}`}>
        {icon}
      </span>
      <span className={`transition-all duration-300 whitespace-nowrap mt-[3px] overflow-hidden ${
        // Hide labels on md/lg to save space, show only on xl or larger screens
        'hidden 2xl:inline-flex'
      }`}>
        {label}
      </span>
    </div>
    {active && (
      <div className="absolute inset-0 bg-gradient-to-l from-[#0369a1]/0 via-[#0369a1]/5 to-[#0369a1]/0 animate-shimmer" />
    )}
  </button>
);

const MobileNavButton: React.FC<{
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}> = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={`w-full px-4 py-3 rounded-2xl text-base font-normal flex items-center gap-3 transition-all ${active
      ? 'bg-[#0369a1] text-white shadow-lg'
      : 'text-[#4a5568] hover:bg-[#0369a1]/10 hover:text-[#0369a1]'
      }`}
  >
    {icon}
    {label}
  </button>
);
