import React from 'react';
import { useNotification } from '../../context/NotificationContext';
import { CheckCircle2, AlertCircle, X } from 'lucide-react';

export const NotificationContainer: React.FC = () => {
  const { notifications, removeNotification } = useNotification();

  if (notifications.length === 0) return null;

  return (
    <div className="flex flex-col gap-2 mb-4 w-full">
      {notifications.map((notification) => (
        <div
          key={notification.id}
          className={`flex items-center justify-between p-4 rounded-xl border animate-in fade-in slide-in-from-top-4 duration-300 ${notification.type === 'success'
              ? 'bg-emerald-50 border-emerald-100 text-emerald-800 shadow-sm shadow-emerald-100/50'
              : notification.type === 'error'
                ? 'bg-rose-50 border-rose-100 text-rose-800 shadow-sm shadow-rose-100/50'
                : 'bg-indigo-50 border-indigo-100 text-indigo-800 shadow-sm shadow-indigo-100/50'
            }`}
        >
          <div className="flex items-center gap-3">
            {notification.type === 'success' ? (
              <CheckCircle2 size={18} className="text-emerald-500" />
            ) : notification.type === 'error' ? (
              <AlertCircle size={18} className="text-rose-500" />
            ) : (
              <AlertCircle size={18} className="text-indigo-500" />
            )}
            <p className="text-sm font-medium">{notification.message}</p>
          </div>
          <button
            onClick={() => removeNotification(notification.id)}
            className={`p-1 rounded-lg transition-colors ${notification.type === 'success'
                ? 'hover:bg-emerald-100 text-emerald-400 hover:text-emerald-600'
                : notification.type === 'error'
                  ? 'hover:bg-rose-100 text-rose-400 hover:text-rose-600'
                  : 'hover:bg-indigo-100 text-indigo-400 hover:text-indigo-600'
              }`}
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
};
