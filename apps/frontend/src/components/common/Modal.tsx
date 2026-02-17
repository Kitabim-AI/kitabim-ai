import React from 'react';
import { AlertCircle } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

interface ModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  type: 'alert' | 'confirm';
  confirmText?: string;
  onConfirm?: () => void;
  onClose: () => void;
  destructive?: boolean;
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
}) => {
  const { t } = useI18n();
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6" dir="rtl">
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-md animate-fade-in"
        onClick={() => type === 'alert' && onClose()}
      />
      <div
        className="bg-white/90 backdrop-blur-2xl rounded-[40px] shadow-[0_32px_128px_rgba(0,0,0,0.15)] w-full max-w-md relative z-10 overflow-hidden animate-fade-in border border-white/40"
      >
        <div className="p-10">
          <div className="flex items-center gap-4 mb-6">
            <div className={`p-3 rounded-2xl ${type === 'confirm' ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'bg-red-50 text-red-500'}`}>
              <AlertCircle size={32} strokeWidth={2.5} />
            </div>
            <h3 className="text-2xl font-black text-[#1a1a1a]">{title}</h3>
          </div>
          <p className="text-[#94a3b8] font-bold leading-loose mb-10 text-lg uyghur-text">
            {message}
          </p>
          <div className="flex items-center gap-4">
            {type === 'confirm' && (
              <button
                onClick={onClose}
                className="flex-1 py-4 px-6 bg-slate-100 hover:bg-slate-200 text-[#94a3b8] font-black rounded-[20px] transition-all active:scale-95 text-sm"
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
              className={`flex-1 py-4 px-6 text-white font-black rounded-[20px] transition-all shadow-xl active:scale-95 text-sm ${destructive
                ? 'bg-red-500 hover:bg-red-600 shadow-red-200'
                : 'bg-[#0369a1] hover:bg-[#0284c7] shadow-[#0369a1]/30'
                }`}
            >
              {confirmText || (type === 'confirm' ? t('modal.confirm') : t('modal.ok'))}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
