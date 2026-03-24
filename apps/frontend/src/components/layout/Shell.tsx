import React from 'react';
import { Navbar } from './Navbar';
import { Modal } from '../common/Modal';
import { NotificationContainer } from '../common/NotificationContainer';
import { SearchOverlay } from '../library/SearchOverlay';
import { useAppContext } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';

interface ShellProps {
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ children }) => {
  const {
    bookActions,
    modal,
    setModal,
    isReaderFullscreen,
    view,
  } = useAppContext();
  const { t } = useI18n();

  return (
    <div className="h-[100dvh] bg-transparent flex flex-col font-sans relative overflow-hidden notranslate" dir="rtl" translate="no">
      <div className={isReaderFullscreen ? 'hidden lg:block' : ''}>
        <Navbar />
      </div>

      <main className="flex-grow overflow-y-auto overscroll-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden pt-[72px] sm:pt-[88px] lg:pt-[96px] px-0 sm:px-2 md:px-4 lg:px-8 max-w-[1600px] mx-auto w-full relative z-10 flex flex-col">

        <div className="flex-grow">
          {children}
        </div>

        <footer className={`mt-8 mb-6 border-t border-[#0369a1]/10 pt-4 flex flex-col sm:flex-row items-center justify-between gap-2 w-full px-4 sm:px-2 ${view === 'join-us' ? 'max-w-6xl mx-auto' : ['global-chat', 'spell-check'].includes(view) ? 'lg:max-w-5xl lg:mx-auto' : ''}`} dir="rtl">
          <p className="text-xs text-slate-400 font-normal uyghur-text">
            © {new Date().getFullYear()} Kitabim.AI — {t('app.footer.copyright')}
          </p>
          <a
            href="mailto:contact@kitabim.ai"
            className="text-xs text-slate-400 font-normal uyghur-text hover:text-[#0369a1] transition-colors"
          >
            {t('app.footer.contactUs')}: contact@kitabim.ai
          </a>
        </footer>
      </main>

      <SearchOverlay />

      <Modal
        isOpen={modal.isOpen}
        title={modal.title}
        message={modal.message}
        type={modal.type}
        confirmText={modal.confirmText}
        onConfirm={modal.onConfirm}
        destructive={modal.destructive}
        isLoading={modal.isLoading}
        onClose={() => setModal({ ...modal, isOpen: false })}
      />
      <NotificationContainer />

      {/* Global Book Opening Spinner */}
      {bookActions.isOpeningBook && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-white/60 backdrop-blur-sm animate-fade-in">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
            <span className="text-sm font-bold text-[#0369a1] uppercase tracking-wider animate-pulse">{t('common.loading')}...</span>
          </div>
        </div>
      )}
    </div>
  );
};
