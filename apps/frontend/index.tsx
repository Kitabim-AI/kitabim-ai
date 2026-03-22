
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './src/App';
import { AuthProvider } from './src/hooks/useAuth';
import { NotificationProvider } from './src/context/NotificationContext';
import { I18nProvider } from './src/i18n/I18nContext';
import { initAppConfig } from './src/services/authService';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error("Could not find root element to mount to");
}

// Fetch app config (app ID) from backend before rendering so all API calls
// have the correct X-Kitabim-App-Id header from the start.
initAppConfig().then(() => {
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <I18nProvider>
        <AuthProvider>
          <NotificationProvider>
            <App />
          </NotificationProvider>
        </AuthProvider>
      </I18nProvider>
    </React.StrictMode>
  );
});
