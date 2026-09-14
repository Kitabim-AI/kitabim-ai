import { Lock, LogIn, Sparkles } from 'lucide-react';
import React from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';

interface GuestAuthWallProps {
  className?: string;
}

export const GuestAuthWall: React.FC<GuestAuthWallProps> = ({ className = '' }) => {
  const { loginWithGoogle, loginWithFacebook, isLoading } = useAuth();
  const { t } = useI18n();

  return (
    <div
      data-testid="guest-auth-wall"
      className={`w-full max-w-2xl mx-auto my-8 p-6 sm:p-10 rounded-[32px] bg-gradient-to-b from-white/90 via-sky-50/40 to-white/90 dark:from-slate-900/90 dark:via-sky-950/20 dark:to-slate-900/90 backdrop-blur-xl border-2 border-[#0369a1]/20 dark:border-[#38bdf8]/20 shadow-[0_20px_60px_-15px_rgba(3,105,161,0.15)] dark:shadow-[0_20px_60px_-15px_rgba(0,0,0,0.5)] text-center relative overflow-hidden transition-all ${className}`}
    >
      {/* Decorative top accent glow */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-1 bg-gradient-to-r from-transparent via-[#0369a1] dark:via-[#38bdf8] to-transparent rounded-full opacity-60" />

      {/* Floating Icon with badge */}
      <div className="relative inline-flex items-center justify-center mb-6">
        <div className="w-16 h-16 sm:w-20 sm:h-20 rounded-3xl bg-gradient-to-br from-[#0369a1] to-[#0284c7] dark:from-[#0284c7] dark:to-[#38bdf8] flex items-center justify-center shadow-xl shadow-[#0369a1]/25 dark:shadow-[#38bdf8]/20 text-white">
          <Lock size={32} className="sm:w-9 sm:h-9" strokeWidth={2.2} />
        </div>
        <div className="absolute -top-1 -right-1 w-7 h-7 rounded-full bg-amber-400 dark:bg-amber-300 text-slate-900 flex items-center justify-center shadow-md animate-pulse">
          <Sparkles size={15} strokeWidth={2.5} />
        </div>
      </div>

      {/* Title */}
      <h3 className="text-xl sm:text-2xl font-bold text-[#1a1a1a] dark:text-slate-100 mb-3 uyghur-text">
        {t('reader.guestLimitTitle')}
      </h3>

      {/* Description */}
      <p className="text-sm sm:text-base text-slate-600 dark:text-slate-400 max-w-lg mx-auto mb-8 leading-relaxed uyghur-text">
        {t('reader.guestLimitDesc')}
      </p>

      {/* OAuth Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5 max-w-md mx-auto">
        {/* Google Sign In */}
        <button
          onClick={loginWithGoogle}
          disabled={isLoading}
          data-testid="guest-auth-google-btn"
          className="w-full sm:w-auto flex-1 flex items-center justify-center gap-3 px-6 py-3.5 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-[#1a1a1a] dark:text-slate-100 border-2 border-[#4285F4]/30 hover:border-[#4285F4] rounded-2xl font-medium text-sm transition-all active:scale-95 disabled:opacity-50 shadow-md hover:shadow-lg shadow-[#4285F4]/10"
        >
          <div className="bg-[#4285F4] p-1.5 rounded-lg shrink-0">
            <svg width="16" height="16" viewBox="0 0 18 18" fill="white">
              <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" />
              <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" />
              <path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" />
              <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" />
            </svg>
          </div>
          <span className="uyghur-text whitespace-nowrap">
            {isLoading ? t('auth.loggingIn') : t('auth.loginWithGoogle')}
          </span>
        </button>

        {/* Facebook Sign In */}
        <button
          onClick={loginWithFacebook}
          disabled={isLoading}
          data-testid="guest-auth-facebook-btn"
          className="w-full sm:w-auto flex-1 flex items-center justify-center gap-3 px-6 py-3.5 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-[#1a1a1a] dark:text-slate-100 border-2 border-[#1877F2]/30 hover:border-[#1877F2] rounded-2xl font-medium text-sm transition-all active:scale-95 disabled:opacity-50 shadow-md hover:shadow-lg shadow-[#1877F2]/10"
        >
          <div className="bg-[#1877F2] p-1.5 rounded-lg shrink-0">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
            </svg>
          </div>
          <span className="uyghur-text whitespace-nowrap">
            {isLoading ? t('auth.loggingIn') : t('auth.loginWithFacebook')}
          </span>
        </button>
      </div>
    </div>
  );
};

export default GuestAuthWall;
