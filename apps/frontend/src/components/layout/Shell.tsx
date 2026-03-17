import React from 'react';
import { Navbar } from './Navbar';
import { Modal } from '../common/Modal';
import { NotificationContainer } from '../common/NotificationContainer';
import { RefreshCw } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';

interface ShellProps {
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({ children }) => {
  const {
    view,
    setView,
    searchQuery,
    setSearchQuery,
    homeSearchQuery,
    bookActions,
    chat,
    setPage,
    isLoading,
    modal,
    setModal,
    isReaderFullscreen,
  } = useAppContext();
  const { t } = useI18n();

  // Fix iOS Safari keyboard dismiss leaving page scrolled with empty space at bottom
  React.useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    let keyboardOpen = false;
    const handleResize = () => {
      const shrunk = vv.height < window.innerHeight * 0.85;
      if (keyboardOpen && !shrunk) {
        // keyboard just closed — reset scroll
        requestAnimationFrame(() => window.scrollTo(0, 0));
      }
      keyboardOpen = shrunk;
    };
    vv.addEventListener('resize', handleResize);
    return () => vv.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="min-h-[100dvh] bg-transparent flex flex-col font-sans relative overflow-x-hidden notranslate" dir="rtl" translate="no">
      <div className={isReaderFullscreen ? 'hidden lg:block' : ''}>
        <Navbar />
      </div>

      <main className="flex-grow p-0 sm:p-2 md:p-4 lg:p-8 max-w-[1600px] mx-auto w-full relative z-10">

        {children}
      </main>

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
