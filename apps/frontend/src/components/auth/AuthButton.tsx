import React, { useState, useEffect, useRef } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { LogOut, User as UserIcon, LogIn, ChevronDown, Shield, Edit3, BookOpen } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

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
      className={`flex items-center gap-3 px-6 py-2.5 bg-white hover:bg-[#0369a1]/10 text-[#1a1a1a] border-2 border-[#0369a1]/20 rounded-2xl font-black text-sm transition-all active:scale-95 disabled:opacity-50 shadow-sm hover:shadow-lg shadow-[#0369a1]/10 ${className}`}
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

export function UserMenu() {
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

  const roleInfo: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
    admin: { label: t('admin.users.admin'), color: 'bg-red-500', icon: <Shield size={12} /> },
    editor: { label: t('admin.users.editor'), color: 'bg-blue-500', icon: <Edit3 size={12} /> },
    reader: { label: t('admin.users.reader'), color: 'bg-[#0369a1]', icon: <BookOpen size={12} /> },
  };

  const currentRole = roleInfo[user.role] || roleInfo.reader;

  return (
    <div ref={menuRef} className="relative z-[1001]" dir="rtl">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-3 px-2 py-2 pr-4 bg-white/60 backdrop-blur-md border border-[#0369a1]/10 rounded-2xl transition-all hover:bg-white hover:shadow-xl hover:shadow-[#0369a1]/10 group ${isOpen ? 'ring-4 ring-[#0369a1]/5 border-[#0369a1]/30' : ''}`}
      >
        <div className="flex flex-col items-end mr-3 hidden sm:flex">
          <span className="text-sm font-black text-[#1a1a1a] tracking-tight">{user.displayName}</span>
          <span className="text-[14px] font-black text-[#94a3b8] uppercase tracking-widest">{currentRole.label}</span>
        </div>

        <div className="relative">
          {user.avatarUrl ? (
            <img
              src={user.avatarUrl}
              alt={user.displayName}
              className="w-10 h-10 rounded-xl object-cover ring-2 ring-white shadow-md"
            />
          ) : (
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-[#0369a1] to-[#0284c7] flex items-center justify-center text-lg font-black text-white shadow-lg">
              {user.displayName.charAt(0).toUpperCase()}
            </div>
          )}
          <div className={`absolute -bottom-1 -right-1 w-4 h-4 ${currentRole.color} rounded-lg border-2 border-white flex items-center justify-center text-white shadow-sm`}>
            {currentRole.icon}
          </div>
        </div>

        <ChevronDown size={16} className={`text-slate-400 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`} strokeWidth={3} />
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-4 w-64 bg-white/90 backdrop-blur-2xl border border-[#0369a1]/10 rounded-3xl shadow-[0_32px_128px_rgba(0,0,0,0.15)] overflow-hidden animate-fade-in p-2">
          {/* User Header */}
          <div className="p-4 mb-2 bg-[#0369a1]/5 rounded-2xl flex flex-col items-center text-center">
            <div className="w-16 h-16 rounded-2xl mb-3 shadow-lg overflow-hidden border-2 border-white bg-white">
              {user.avatarUrl ? (
                <img src={user.avatarUrl} alt={user.displayName} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full bg-[#0369a1] flex items-center justify-center text-2xl font-black text-white">
                  {user.displayName.charAt(0).toUpperCase()}
                </div>
              )}
            </div>
            <div className="font-black text-[#1a1a1a] line-clamp-1">{user.displayName}</div>
            <div className="text-[14px] font-bold text-slate-400 mt-1 line-clamp-1">{user.email}</div>
          </div>

          <div className="space-y-1">
            <div className="px-4 py-3 flex items-center gap-3 text-sm font-black text-[#94a3b8] uppercase tracking-widest border-b border-[#0369a1]/5 mb-1">
              {t('auth.yourRole')} <span className={`px-2 py-0.5 rounded-lg ${currentRole.color} text-white`}>{currentRole.label}</span>
            </div>

            <button
              onClick={() => {
                setIsOpen(false);
                logout();
              }}
              disabled={isLoading}
              className="w-full flex items-center gap-4 px-4 py-3.5 text-red-500 hover:bg-red-50 rounded-2xl transition-all font-black text-sm active:scale-95 group"
            >
              <div className="p-2 bg-red-100 rounded-xl group-hover:bg-red-500 group-hover:text-white transition-colors">
                <LogOut size={18} strokeWidth={2.5} />
              </div>
              {t('auth.logout')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AuthButton() {
  const { isAuthenticated, isLoading } = useAuth();
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-6 py-2.5 bg-white/40 backdrop-blur-md rounded-2xl border border-[#0369a1]/10 animate-pulse">
        <div className="w-4 h-4 bg-[#0369a1]/30 rounded-full animate-bounce" />
        <span className="text-sm font-black text-[#0369a1]/50 tracking-widest uppercase">{t('common.loading')}</span>
      </div>
    );
  }

  return isAuthenticated ? <UserMenu /> : <LoginButton />;
}

export default AuthButton;
