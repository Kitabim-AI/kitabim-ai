import React from 'react';
import { AlertCircle } from 'lucide-react';

interface ModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  type: 'alert' | 'confirm';
  confirmText?: string;
  onConfirm?: () => void;
  onClose: () => void;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  title,
  message,
  type,
  confirmText,
  onConfirm,
  onClose,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-300"
        onClick={() => type === 'alert' && onClose()}
      />
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-md relative z-10 overflow-hidden animate-in zoom-in-95 duration-200 border border-slate-100">
        <div className="p-8">
          <div className="flex items-center gap-3 mb-4">
            <div className={`p-2 rounded-xl ${type === 'confirm' ? 'bg-amber-100 text-amber-600' : 'bg-red-100 text-red-600'}`}>
              <AlertCircle size={24} />
            </div>
            <h3 className="text-xl font-bold text-slate-900">{title}</h3>
          </div>
          <p className="text-slate-600 leading-relaxed mb-8">
            {message}
          </p>
          <div className="flex items-center gap-3">
            {type === 'confirm' && (
              <button
                onClick={onClose}
                className="flex-1 py-3 px-4 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold rounded-2xl transition-colors"
              >
                Cancel
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
              className={`flex-1 py-3 px-4 text-white font-bold rounded-2xl transition-all shadow-lg active:scale-95 ${(confirmText === 'Delete Permanently' || (!confirmText && type === 'confirm' && title === 'Confirm Deletion'))
                  ? 'bg-red-500 hover:bg-red-600 shadow-red-100'
                  : 'bg-indigo-600 hover:bg-indigo-700 shadow-indigo-100'
                }`}
            >
              {confirmText || (type === 'confirm' ? 'Confirm' : 'Understood')}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
