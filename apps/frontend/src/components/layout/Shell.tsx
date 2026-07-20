import React from 'react';
import { Heart } from 'lucide-react';
import { useAppContext } from '../../context/AppContext';
import { useI18n } from '../../i18n/I18nContext';
import { Modal } from '../common/Modal';
import { NotificationContainer } from '../common/NotificationContainer';
import { SearchOverlay } from '../library/SearchOverlay';
import { Navbar } from './Navbar';

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
      <div className={`${isReaderFullscreen ? 'hidden lg:block' : ''} navbar-wrapper`}>
        <Navbar />
      </div>

      <main className={`flex-grow overscroll-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden pt-[72px] sm:pt-[88px] lg:pt-[96px] px-0 sm:px-2 md:px-4 lg:px-8 max-w-[1600px] mx-auto w-full relative z-10 flex flex-col min-h-0 ${['spell-check', 'graph'].includes(view) ? 'overflow-y-auto lg:overflow-hidden' : ['global-chat', 'reader'].includes(view) ? 'overflow-hidden' : 'overflow-y-auto'}`}>

        <div className={`flex-grow flex flex-col ${['global-chat', 'reader', 'spell-check', 'graph'].includes(view) ? 'min-h-0' : ''}`}>
          {children}
        </div>

        {view !== 'reader' && view !== 'admin' && view !== 'join-us' && view !== 'graph' && view !== 'dictionary' && view !== 'quran' && (
          <footer className={`border-t border-[#0369a1]/10 dark:border-[#38bdf8]/10 pt-4 ${['global-chat', 'spell-check'].includes(view) ? 'hidden sm:flex' : 'flex'} flex-col sm:flex-row sm:flex-wrap lg:grid lg:grid-cols-3 items-center justify-center sm:justify-around lg:justify-items-stretch gap-4 w-full px-4 sm:px-2 ${['global-chat', 'spell-check'].includes(view) ? 'mb-2 mt-4 lg:max-w-5xl lg:mx-auto' : 'mb-6 mt-8'}`} dir="rtl">
            {/* Right Column (Copyright) */}
            <div className="w-full sm:w-auto text-center lg:text-right whitespace-nowrap">
              <p className="text-xs text-slate-400 font-normal uyghur-text">
                © {new Date().getFullYear()} Kitabim.AI — {t('app.footer.copyright')}
              </p>
            </div>

            {/* Middle Column (Sponsors & Donate) - Perfectly Centered */}
            <div className="flex items-center justify-center gap-4 select-none w-full sm:w-auto whitespace-nowrap">
              <div className="flex items-center gap-3">
                <span className="text-[10px] sm:text-xs text-slate-400 font-medium tracking-wider uyghur-text">
                  {t('app.footer.sponsors')}
                </span>
                <a
                  href="https://www.dallasuyghurcommunity.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Dallas Uyghur Community"
                  className="flex items-center justify-center transition-transform hover:scale-105 active:scale-95"
                >
                  <img
                    src="https://dallasuyghurcommunity.org/wp-content/uploads/2025/01/DUC_Logo_3ai_Artboard-2-photoaidcom-cropped-1.png"
                    alt="Dallas Uyghur Community"
                    className="h-10 sm:h-12 w-auto object-contain"
                  />
                </a>
                <a
                  href="https://uyghursfoundation.org"
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Uyghur Projects Foundation"
                  className="flex items-center justify-center transition-transform hover:scale-105 active:scale-95"
                >
                  <img
                    src="https://uyghursfoundation.org/en/wp-content/uploads/2021/07/upf-150x150.jpg"
                    alt="Uyghur Projects Foundation"
                    className="h-10 sm:h-12 w-auto object-contain rounded-full"
                  />
                </a>
              </div>
              <div className="w-[1px] h-6 bg-slate-200 dark:bg-slate-800" />
              <a
                href="https://www.paypal.com/donate/?hosted_button_id=TKHXS8HCDUEJA"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-rose-600 hover:bg-rose-500 hover:shadow-lg hover:shadow-rose-500/20 active:scale-95 transition-all duration-300 rounded-full"
              >
                <Heart size={14} className="fill-current" />
                <span>{t('app.footer.donate')}</span>
              </a>
            </div>

            {/* Left Column (Contact Us) */}
            <div className="w-full sm:w-auto text-center lg:text-left whitespace-nowrap">
              <a
                href="mailto:contact@kitabim.ai"
                className="text-xs text-slate-400 font-normal uyghur-text hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors"
              >
                {t('app.footer.contactUs')}: contact@kitabim.ai
              </a>
            </div>
          </footer>
        )}
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
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-white/60 dark:bg-slate-950/60 backdrop-blur-sm animate-fade-in">
          <div className="flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-[#0369a1]/10 border-t-[#0369a1] dark:border-t-[#38bdf8] rounded-full animate-spin"></div>
            <span className="text-sm font-bold text-[#0369a1] dark:text-[#38bdf8] uppercase tracking-wider animate-pulse">{t('common.loading')}...</span>
          </div>
        </div>
      )}
    </div>
  );
};
