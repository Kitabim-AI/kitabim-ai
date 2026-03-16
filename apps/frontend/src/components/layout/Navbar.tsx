import React, { useRef, useState } from 'react';
import { BookOpen, Library, Bot, LayoutDashboard, Search, Upload, Users, Menu, X, RefreshCw, BookOpenCheck } from 'lucide-react';
import { AuthButton } from '../auth';
import { useAuth, useIsEditor } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

export const Navbar: React.FC = () => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isAuthenticated } = useAuth();
  const isEditor = useIsEditor();
  const { t } = useI18n();
  const { view, setView, searchQuery, setSearchQuery, homeSearchQuery, setHomeSearchQuery, bookActions, chat, setPage, isLoading } = useAppContext();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [localSearch, setLocalSearch] = useState(searchQuery);

  // Sync local search when global search is cleared or changed externally
  React.useEffect(() => {
    setLocalSearch(searchQuery);
  }, [searchQuery]);

  // Debounce global search update
  React.useEffect(() => {
    const timer = setTimeout(() => {
      if (localSearch !== searchQuery) {
        setSearchQuery(localSearch);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch, searchQuery, setSearchQuery]);

  const handleNavClick = (callback: () => void) => {
    callback();
    setMobileMenuOpen(false);
  };

  return (
    <>
      <nav className="px-4 sm:px-6 md:px-10 lg:px-12 py-3 sm:py-4 flex items-center justify-between sticky top-0 z-[100] transition-all duration-300" dir="rtl">
        {/* Glass Backdrop - Matching Prototype */}
        <div className="absolute inset-0 bg-white/75 backdrop-blur-[20px] border-b border-[rgba(255,193,7,0.2)] shadow-[0_4px_30px_rgba(117,197,240,0.1),0_1px_0_rgba(255,255,255,0.8)_inset]"
          style={{ backdropFilter: 'blur(20px) saturate(180%)', WebkitBackdropFilter: 'blur(20px) saturate(180%)' }} />

        {/* Gradient Border at Bottom - Matching Prototype */}
        <div className="absolute -bottom-px left-0 right-0 h-px bg-gradient-to-l from-transparent via-[rgba(255,193,7,0.5)] to-transparent"
          style={{ background: 'linear-gradient(270deg, transparent, rgba(255, 193, 7, 0.5), rgba(156, 39, 176, 0.3), transparent)' }} />

        <div className="relative flex items-center gap-3 sm:gap-4 md:gap-3 lg:gap-8">
          <div className="flex items-center h-[48px] gap-2 sm:gap-3 cursor-pointer group transition-transform duration-300 hover:-translate-y-0.5" onClick={() => setView('home')}>
            <div className="flex-shrink-0 p-2 md:p-2.5 rounded-xl md:rounded-2xl shadow-[0_4px_20px_rgba(255,193,7,0.4),0_8px_40px_rgba(156,39_176,0.2),inset_0_1px_0_rgba(255,255,255,0.4)] transition-all duration-300 relative overflow-hidden group-hover:shadow-[0_6px_20px_rgba(3,105,161,0.5)] icon-shake"
              style={{
                background: 'linear-gradient(135deg, #FFD54F 0%, #FF9800 50%, #9C27B0 100%)'
              }}>
              <div className="absolute inset-0 opacity-30"
                style={{
                  background: 'repeating-conic-gradient(from 0deg at 50% 50%, transparent 0deg, transparent 10deg, rgba(255, 255, 255, 0.1) 10deg, rgba(255, 255, 255, 0.1) 20deg)'
                }} />
              <BookOpen size={20} className="md:w-5 md:h-5 text-white relative z-10" strokeWidth={2} />
            </div>
            <span dir="ltr" className="flex items-center font-semibold text-[#1a1a1a] text-[24px] mt-[12px] md:text-[32px] md:mt-[16px] tracking-tight">
              Kitabim<span className="text-[#0369a1]">.AI</span>
            </span>
          </div>

          {/* Desktop/Tablet Navigation - hide icons on md, show on lg+ */}
          <div className="hidden md:flex items-center gap-1">
            <NavButton
              active={view === 'home'}
              onClick={() => setView('home')}
              icon={<Search size={20} strokeWidth={2.5} />}
              label={t('nav.home')}
            />
            <NavButton
              active={view === 'library'}
              onClick={() => setView('library')}
              icon={<Library size={20} strokeWidth={2.5} />}
              label={t('nav.library')}
            />
            <NavButton
              active={view === 'global-chat'}
              onClick={() => { setView('global-chat'); chat.clearChat(); }}
              icon={<Bot size={24} strokeWidth={2.5} />}
              label={t('nav.globalChat')}
            />
            {isEditor && (
              <NavButton
                active={view === 'spell-check'}
                onClick={() => setView('spell-check')}
                icon={<BookOpenCheck size={20} strokeWidth={2.5} />}
                label={t('nav.spellCheck')}
              />
            )}
            {isEditor && (
              <NavButton
                active={view === 'admin'}
                onClick={() => { setView('admin'); setPage(1); }}
                icon={<LayoutDashboard size={20} strokeWidth={2.5} />}
                label={t('nav.admin')}
              />
            )}
            <NavButton
              active={view === 'join-us'}
              onClick={() => setView('join-us')}
              icon={<Users size={20} strokeWidth={2.5} />}
              label={t('nav.joinUs')}
            />
          </div>
        </div>

        <div className="relative flex items-center gap-2 md:gap-2 lg:gap-4">
          {(view === 'admin' || view === 'library') && (
            <div className="relative hidden xl:block">
              <input
                type="text"
                placeholder={t('library.searchPlaceholder')}
                value={localSearch}
                onChange={(e) => setLocalSearch(e.target.value)}
                className="pr-11 pl-11 py-2.5 bg-white/50 backdrop-blur-md border-2 border-[#0369a1]/10 rounded-2xl text-sm font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none focus:border-[#0369a1] transition-all w-64 shadow-sm uyghur-text"
                dir="rtl"
              />
              <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1]">
                {isLoading && localSearch ? (
                  <RefreshCw size={18} strokeWidth={3} className="animate-spin" />
                ) : (
                  <Search size={18} strokeWidth={3} />
                )}
              </div>
              {localSearch && (
                <button
                  onClick={() => { setLocalSearch(''); setSearchQuery(''); }}
                  className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-[#0369a1] transition-all active:scale-90"
                >
                  <X size={16} strokeWidth={3} />
                </button>
              )}
            </div>
          )}

          {isEditor && (
            <>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="group relative px-[0.7rem] md:px-5 lg:px-6 h-[35px] md:h-[48px] rounded-[0.7rem] md:rounded-2xl font-normal flex items-center justify-center gap-2 transition-all duration-300 text-white shadow-[0_8px_20px_rgba(3,105,161,0.2)] hover:shadow-[0_12px_28px_rgba(3,105,161,0.3)] hover:-translate-y-0.5 active:translate-y-0 overflow-hidden text-sm lg:text-base"
                style={{
                  background: 'linear-gradient(135deg, #0369a1 0%, #0284c7 100%)'
                }}
              >
                <div className="absolute inset-0 bg-gradient-to-l from-white/0 via-white/20 to-white/0 translate-x-[100%] group-hover:animate-shimmer-fast" />
                <Upload size={14} strokeWidth={3} className="relative z-10 lg:w-[16px] lg:h-[16px]" />
                <span className="relative z-10 hidden lg:inline whitespace-nowrap">{t('nav.addBook')}</span>
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
            className="md:hidden p-2 min-w-[44px] min-h-[44px] rounded-xl hover:bg-[#0369a1]/10 text-[#0369a1] transition-all relative z-10"
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
            className="fixed inset-0 bg-black/20 backdrop-blur-sm z-[90] md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />

          {/* Menu Panel */}
          <div className="fixed top-[72px] left-0 right-0 bg-white/95 backdrop-blur-2xl border-b border-[#0369a1]/10 shadow-2xl z-[95] md:hidden animate-fade-in" dir="rtl">
            <div className="px-4 py-6 space-y-2">
              <MobileNavButton
                active={view === 'home'}
                onClick={() => handleNavClick(() => setView('home'))}
                icon={<Search size={20} strokeWidth={2.5} />}
                label={t('nav.home')}
              />
              <MobileNavButton
                active={view === 'library'}
                onClick={() => handleNavClick(() => setView('library'))}
                icon={<Library size={20} strokeWidth={2.5} />}
                label={t('nav.library')}
              />
              <MobileNavButton
                active={view === 'global-chat'}
                onClick={() => handleNavClick(() => { setView('global-chat'); chat.clearChat(); })}
                icon={<Bot size={24} strokeWidth={2.5} />}
                label={t('nav.globalChat')}
              />
              {isEditor && (
                <MobileNavButton
                  active={view === 'spell-check'}
                  onClick={() => handleNavClick(() => setView('spell-check'))}
                  icon={<BookOpenCheck size={20} strokeWidth={2.5} />}
                  label={t('nav.spellCheck')}
                />
              )}
              {isEditor && (
                <MobileNavButton
                  active={view === 'admin'}
                  onClick={() => handleNavClick(() => { setView('admin'); setPage(1); })}
                  icon={<LayoutDashboard size={20} strokeWidth={2.5} />}
                  label={t('nav.admin')}
                />
              )}
              <MobileNavButton
                active={view === 'join-us'}
                onClick={() => handleNavClick(() => setView('join-us'))}
                icon={<Users size={20} strokeWidth={2.5} />}
                label={t('nav.joinUs')}
              />

              {/* Auth section in mobile menu */}
              <div className="pt-4 border-t border-[#0369a1]/10 sm:hidden">
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
    className={`relative px-3 md:px-3 lg:px-4 xl:px-6 h-[44px] md:h-[48px] rounded-2xl text-sm lg:text-base font-normal flex items-center gap-2 transition-all duration-300 group ${active
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
        'hidden xl:inline-flex'
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
