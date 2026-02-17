import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { LogOut, User as UserIcon, LogIn, ChevronDown, Shield, Edit3, BookOpen } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { UserAvatar } from '../common/UserAvatar';

interface LoginButtonProps {
  className?: string;
}

export function LoginButton({ className = '' }: LoginButtonProps) {
  const { login, isLoading } = useAuth();
  const { t } = useI18n();

  return (
    <button
      onClick={login}
      disabled={isLoading}
      className={`flex items-center gap-3 px-6 py-2.5 bg-white hover:bg-[#0369a1]/10 text-[#1a1a1a] border-2 border-[#0369a1]/20 rounded-2xl font-normal text-sm transition-all active:scale-95 disabled:opacity-50 shadow-sm hover:shadow-lg shadow-[#0369a1]/10 ${className}`}
    >
      <div className="bg-[#4285F4] p-1.5 rounded-lg">
        <svg width="16" height="16" viewBox="0 0 18 18" fill="white">
          <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" />
          <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" />
          <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" />
          <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" />
        </svg>
      </div>
      <span className="uyghur-text">{isLoading ? t('auth.loggingIn') : t('auth.loginWithGoogle')}</span>
    </button>
  );
}


export function UserMenu({ onLogout }: { onLogout?: () => void }) {
  const { user, logout, isLoading } = useAuth();
  const { t } = useI18n();
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!user) return null;

  const roleInfo: Record<string, { label: string; bg: string; text: string; icon: React.ReactNode }> = {
    admin: {
      label: t('admin.users.admin'),
      bg: 'linear-gradient(135deg, #FFD54F 0%, #FF9800 50%, #9C27B0 100%)',
      text: 'text-white',
      icon: <Shield size={12} />
    },
    editor: {
      label: t('admin.users.editor'),
      bg: 'linear-gradient(135deg, #0369a1 0%, #0284c7 100%)',
      text: 'text-white',
      icon: <Edit3 size={12} />
    },
    reader: {
      label: t('admin.users.reader'),
      bg: 'linear-gradient(135deg, #64748b 0%, #475569 100%)',
      text: 'text-white',
      icon: <BookOpen size={12} />
    },
  };

  const currentRole = roleInfo[user.role] || roleInfo.reader;

  return (
    <div ref={menuRef} className="relative z-[1001]" dir="rtl">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-3 px-2 py-2 pr-4 bg-white/75 backdrop-blur-md border border-[#FF9800]/10 rounded-2xl transition-all hover:bg-white hover:shadow-xl hover:shadow-[#FF9800]/10 group ${isOpen ? 'ring-4 ring-[#FF9800]/5 border-[#FF9800]/30' : ''}`}
      >
        <div className="flex flex-col items-end mr-3 hidden sm:flex">
          <span className="text-sm font-normal text-[#1a1a1a]">{user.displayName}</span>
          <span className="text-[12px] font-normal text-[#FF9800] uppercase tracking-wider">{currentRole.label}</span>
        </div>

        <div className="relative">
          <UserAvatar
            url={user.avatarUrl}
            name={user.displayName}
            className="w-10 h-10 rounded-xl object-cover ring-2 ring-white shadow-md transition-transform group-hover:scale-110"
          />
          <div
            className={`absolute -bottom-1 -right-1 w-5 h-5 rounded-lg border-2 border-white flex items-center justify-center text-white shadow-sm`}
            style={{ background: currentRole.bg }}
          >
            {currentRole.icon}
          </div>
        </div>

        <ChevronDown size={14} className={`text-slate-400 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} strokeWidth={3} />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-4 w-72 bg-white/95 backdrop-blur-2xl border border-[#FF9800]/20 rounded-[32px] shadow-[0_32px_128px_rgba(255,152,0,0.1)] overflow-hidden animate-fade-in p-2">
          {/* User Header */}
          <div className="p-6 mb-2 bg-gradient-to-br from-[#FF9800]/5 to-[#9C27B0]/5 rounded-[24px] flex flex-col items-center text-center">
            <div className="relative mb-4">
              <div className="w-20 h-20 rounded-[28px] shadow-2xl overflow-hidden border-4 border-white bg-white transform rotate-3 transition-transform hover:rotate-0">
                <UserAvatar
                  url={user.avatarUrl}
                  name={user.displayName}
                  className="w-full h-full object-cover"
                />
              </div>
              <div
                className="absolute -bottom-2 -right-2 px-3 py-1 rounded-full text-[11px] font-normal uppercase text-white shadow-lg"
                style={{ background: currentRole.bg }}
              >
                {currentRole.label}
              </div>
            </div>
            <div className="font-normal text-[#1a1a1a] text-lg">{user.displayName}</div>
            <div className="text-[13px] font-normal text-slate-400 mt-1">{user.email}</div>
          </div>

          <div className="p-2 space-y-1">
            <button
              onClick={() => {
                setIsOpen(false);
                logout();
                onLogout?.();
              }}
              disabled={isLoading}
              className="w-full flex items-center justify-between px-5 py-4 text-[#1a1a1a] hover:bg-[#FF9800]/5 rounded-2xl transition-all font-normal text-sm active:scale-95 group"
            >
              <div className="flex items-center gap-4">
                <div className="p-2.5 bg-[#FF9800]/10 text-[#FF9800] rounded-xl group-hover:bg-[#FF9800] group-hover:text-white transition-all shadow-sm">
                  <LogOut size={18} strokeWidth={2.5} />
                </div>
                <span className="group-hover:text-[#FF9800] transition-colors uppercase font-normal">{t('auth.logout')}</span>
              </div>
              <ChevronDown size={14} className="opacity-0 group-hover:opacity-100 -rotate-90 transition-all text-[#FF9800]/30" strokeWidth={3} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AuthButton({ onLogout }: { onLogout?: () => void }) {
  const { isAuthenticated, isLoading } = useAuth();
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-6 py-2.5 bg-white/40 backdrop-blur-md rounded-2xl border border-[#0369a1]/10 animate-pulse">
        <div className="w-4 h-4 bg-[#0369a1]/30 rounded-full animate-bounce" />
        <span className="text-sm font-normal text-[#0369a1]/50 uppercase">{t('common.loading')}</span>
      </div>
    );
  }

  return isAuthenticated ? <UserMenu onLogout={onLogout} /> : <LoginButton />;
}

export default AuthButton;
