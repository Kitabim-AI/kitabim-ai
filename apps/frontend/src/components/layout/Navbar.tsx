import React, { useRef } from 'react';
import { BookOpen, Library, MessageSquare, LayoutDashboard, Search, Upload, Users } from 'lucide-react';
import { AuthButton } from '../auth';
import { useAuth, useIsEditor } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

export const Navbar: React.FC = () => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { isAuthenticated } = useAuth();
  const isEditor = useIsEditor();
  const { t } = useI18n();
  const { view, setView, searchQuery, setSearchQuery, homeSearchQuery, setHomeSearchQuery, bookActions, chat, setPage } = useAppContext();

  return (
    <nav className="px-8 py-4 flex items-center justify-between sticky top-0 z-[100] transition-all duration-300 relative" dir="rtl">
      {/* Glass Backdrop - Matching Prototype */}
      <div className="absolute inset-0 bg-white/75 backdrop-blur-[20px] border-b border-[rgba(255,193,7,0.2)] shadow-[0_4px_30px_rgba(117,197,240,0.1),0_1px_0_rgba(255,255,255,0.8)_inset]"
        style={{ backdropFilter: 'blur(20px) saturate(180%)', WebkitBackdropFilter: 'blur(20px) saturate(180%)' }} />

      {/* Gradient Border at Bottom - Matching Prototype */}
      <div className="absolute -bottom-px left-0 right-0 h-px bg-gradient-to-r from-transparent via-[rgba(255,193,7,0.5)] to-transparent"
        style={{ background: 'linear-gradient(90deg, transparent, rgba(255, 193, 7, 0.5), rgba(156, 39, 176, 0.3), transparent)' }} />

      <div className="relative flex items-center gap-8">
        <div className="flex items-center gap-3 cursor-pointer group transition-transform duration-300 hover:-translate-y-0.5" onClick={() => setView('home')}>
          <div className="p-3 rounded-2xl shadow-[0_4px_20px_rgba(255,193,7,0.4),0_8px_40px_rgba(156,39_176,0.2),inset_0_1px_0_rgba(255,255,255,0.4)] transition-all duration-300 relative overflow-hidden group-hover:shadow-[0_6px_20px_rgba(117,197,240,0.5)] group-hover:-rotate-6"
            style={{
              background: 'linear-gradient(135deg, #FFD54F 0%, #FF9800 50%, #9C27B0 100%)'
            }}>
            <div className="absolute inset-0 opacity-30"
              style={{
                background: 'repeating-conic-gradient(from 0deg at 50% 50%, transparent 0deg, transparent 10deg, rgba(255, 255, 255, 0.1) 10deg, rgba(255, 255, 255, 0.1) 20deg)'
              }} />
            <BookOpen size={28} className="text-white relative z-10" strokeWidth={2} />
          </div>
          <span className="font-normal text-[#1a1a1a] text-[1.75rem] tracking-tight hidden sm:block">
            Kitabim<span className="text-[#0369a1]">.AI</span>
          </span>
        </div>

        <div className="hidden lg:flex items-center gap-1">
          <NavButton
            active={view === 'home'}
            onClick={() => setView('home')}
            icon={<Search size={18} strokeWidth={2.5} />}
            label={t('nav.home')}
          />
          <NavButton
            active={view === 'library'}
            onClick={() => setView('library')}
            icon={<Library size={18} strokeWidth={2.5} />}
            label={t('nav.library')}
          />
          <NavButton
            active={view === 'global-chat'}
            onClick={() => { setView('global-chat'); chat.clearChat(); }}
            icon={<MessageSquare size={18} strokeWidth={2.5} />}
            label={t('nav.globalChat')}
          />
          {isEditor && (
            <NavButton
              active={view === 'admin'}
              onClick={() => { setView('admin'); setPage(1); }}
              icon={<LayoutDashboard size={18} strokeWidth={2.5} />}
              label={t('nav.admin')}
            />
          )}
          <NavButton
            active={view === 'join-us'}
            onClick={() => setView('join-us')}
            icon={<Users size={18} strokeWidth={2.5} />}
            label={t('nav.joinUs')}
          />
        </div>
      </div>

      <div className="relative flex items-center gap-4">
        {(view !== 'home' || homeSearchQuery.length > 0) && (
          <div className="relative hidden xl:block">
            <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1]">
              <Search size={18} strokeWidth={3} />
            </div>
            <input
              type="text"
              placeholder={t('library.searchPlaceholder')}
              value={view === 'home' ? homeSearchQuery : searchQuery}
              onChange={(e) => view === 'home' ? setHomeSearchQuery(e.target.value) : setSearchQuery(e.target.value)}
              className="px-12 py-2.5 bg-white/50 backdrop-blur-md border-2 border-[#0369a1]/10 rounded-2xl text-sm font-normal text-[#1a1a1a] placeholder:text-slate-300 outline-none focus:border-[#0369a1] transition-all w-64 shadow-sm"
              dir="rtl"
            />
          </div>
        )}

        {isEditor && (
          <>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="relative text-white px-7 py-3 rounded-xl font-normal flex items-center gap-2 transition-all duration-300 shadow-[0_4px_12px_rgba(117,197,240,0.3)] hover:shadow-[0_8px_24px_rgba(117,197,240,0.5)] hover:-translate-y-1 active:translate-y-0 overflow-hidden"
              style={{
                background: 'linear-gradient(135deg, #0369a1 0%, #0284c7 100%)'
              }}
            >
              <span className="absolute inset-0 translate-x-[-100%] transition-transform duration-600"
                style={{
                  background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, rgba(255, 255, 255, 0) 100%)'
                }} />
              <Upload size={16} strokeWidth={2} />
              <span>{t('nav.addBook')}</span>
            </button>
            <input
              type="file"
              ref={fileInputRef}
              onChange={bookActions.handleFileUpload}
              accept="application/pdf"
              className="hidden"
            />
          </>
        )}
        <AuthButton onLogout={() => setView('home')} />
      </div>
    </nav>
  );
};

const NavButton: React.FC<{ active: boolean; onClick: () => void; icon: React.ReactNode; label: string }> = ({
  active, onClick, icon, label
}) => (
  <button
    onClick={onClick}
    className={`relative px-6 py-3 rounded-xl text-[1rem] font-normal flex items-center gap-2 transition-all duration-300 overflow-hidden ${active
      ? 'text-white shadow-[0_4px_12px_rgba(3,105,161,0.3)]'
      : 'text-[#4a5568] hover:bg-[#0369a1]/10 hover:text-[#0369a1] hover:-translate-y-0.5'
      }`}
    style={active ? {
      background: 'linear-gradient(135deg, #0369a1 0%, #0284c7 100%)'
    } : undefined}
  >
    {!active && (
      <span className="absolute inset-0 rounded-full bg-[rgba(117,197,240,0.1)] scale-0 transition-transform duration-600"
        style={{
          transform: 'translate(-50%, -50%) scale(0)',
          top: '50%',
          left: '50%'
        }} />
    )}
    <span className="relative z-10 flex items-center gap-2">
      {icon} {label}
    </span>
  </button>
);
