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
        {(isLoading || bookActions?.isCheckingGlobal) && view !== 'reader' && !searchQuery && !homeSearchQuery && (
          <div className="absolute inset-0 bg-white/40 backdrop-blur-md z-40 flex items-center justify-center min-h-[400px] rounded-[40px]">
            <div className="flex flex-col items-center gap-6">
              <div className="relative">
                <div className="w-16 h-16 border-4 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
                <div className="absolute inset-0 flex items-center justify-center text-[#0369a1]">
                  <RefreshCw size={24} className="animate-pulse" />
                </div>
              </div>
              <span className="text-sm font-normal text-[#0369a1] uppercase animate-pulse">{t('common.loadingApp')}</span>
            </div>
          </div>
        )}

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
        onClose={() => setModal({ ...modal, isOpen: false })}
      />
      <NotificationContainer />
    </div>
  );
};
