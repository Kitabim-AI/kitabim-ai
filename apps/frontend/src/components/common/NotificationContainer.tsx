import { AlertCircle, CheckCircle2, X } from 'lucide-react';
import React from 'react';
import { useNotification } from '../../context/NotificationContext';

export const NotificationContainer: React.FC = () => {
  const { notifications, removeNotification } = useNotification();

  if (notifications.length === 0) return null;

  return (
    <div className="fixed top-24 right-8 z-[2000] flex flex-col gap-4 w-full max-w-sm pointer-events-none" dir="rtl" lang="ug">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={`pointer-events-auto flex items-center justify-between p-6 bg-white/80 backdrop-blur-2xl rounded-3xl border shadow-2xl animate-fade-in ${notification.type === 'success'
            ? 'border-emerald-500/20 text-[#1a1a1a] shadow-emerald-500/5'
            : notification.type === 'error'
              ? 'border-red-500/20 text-[#1a1a1a] shadow-red-500/5'
              : 'border-[#0369a1]/20 text-[#1a1a1a] shadow-[#0369a1]/5'
            }`}
        >
          <div className="flex items-center gap-4">
            <div className={`p-2.5 rounded-2xl ${notification.type === 'success'
              ? 'bg-emerald-50 text-emerald-500'
              : notification.type === 'error'
                ? 'bg-red-50 text-red-500'
                : 'bg-[#0369a1]/10 text-[#0369a1]'
              }`}>
              {notification.type === 'success' ? (
                <CheckCircle2 size={24} strokeWidth={3} />
              ) : notification.type === 'error' ? (
                <AlertCircle size={24} strokeWidth={3} />
              ) : (
                <AlertCircle size={24} strokeWidth={3} />
              )}
            </div>
            <p className="text-sm font-normal uyghur-text leading-relaxed">{notification.message}</p>
          </div>
          <button
            onClick={() => removeNotification(notification.id)}
            className="p-2 hover:bg-slate-100 text-slate-300 hover:text-slate-500 rounded-xl transition-all active:scale-90"
          >
            <X size={20} strokeWidth={3} />
          </button>
        </div>
      ))}
    </div>
  );
};
