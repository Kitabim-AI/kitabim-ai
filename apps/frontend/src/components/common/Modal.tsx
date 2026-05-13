import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react';
import React, { useEffect } from 'react';
import { useI18n } from '../../i18n/I18nContext';

interface ModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  type: 'alert' | 'confirm' | 'success';
  confirmText?: string;
  onConfirm?: () => void;
  onClose: () => void;
  destructive?: boolean;
  isLoading?: boolean;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  title,
  message,
  type,
  confirmText,
  onConfirm,
  onClose,
  destructive = false,
  isLoading = false,
}) => {
  const { t } = useI18n();

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = ''; };
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6" dir="rtl" lang="ug">
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-md animate-fade-in"
        onClick={() => (type === 'alert' || type === 'success') && onClose()}
      />
      <div
        className="bg-white/90 backdrop-blur-2xl rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.15)] w-full max-w-md relative z-10 overflow-hidden animate-fade-in border border-white/40"
      >
        <div className="p-10">
          <div className="flex items-center gap-4 mb-6">
            <div className={`p-3 rounded-2xl ${
              type === 'confirm' ? 'bg-[#0369a1]/10 text-[#0369a1]' : 
              type === 'success' ? 'bg-emerald-50 text-emerald-500' :
              'bg-red-50 text-red-500'
            }`}>
              {type === 'success' ? (
                <CheckCircle2 size={32} strokeWidth={2.5} />
              ) : (
                <AlertCircle size={32} strokeWidth={2.5} />
              )}
            </div>
            <h3 className="text-xl sm:text-2xl font-normal text-[#1a1a1a]">{title}</h3>
          </div>
          <p className="text-[#94a3b8] font-normal leading-loose mb-10 text-base sm:text-lg uyghur-text">
            {message}
          </p>
          <div className="flex items-center gap-4">
            {type === 'confirm' && (
              <button
                onClick={onClose}
                disabled={isLoading}
                className="flex-1 py-4 px-6 bg-slate-100 hover:bg-slate-200 text-[#94a3b8] font-normal rounded-[20px] transition-all active:scale-95 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('common.cancel')}
              </button>
            )}
            <button
              onClick={() => {
                if (onConfirm) {
                  onConfirm();
                } else {
                  onClose();
                }
              }}
              disabled={isLoading}
              className={`flex-1 py-4 px-6 text-white font-normal rounded-[20px] transition-all shadow-xl active:scale-95 text-sm disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 ${destructive
                ? 'bg-red-500 hover:bg-red-600 shadow-red-200'
                : 'bg-[#0369a1] hover:bg-[#0284c7] shadow-[#0369a1]/30'
                }`}
            >
              {isLoading && <Loader2 size={16} className="animate-spin" />}
              {confirmText || (type === 'confirm' ? t('modal.confirm') : t('modal.ok'))}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
