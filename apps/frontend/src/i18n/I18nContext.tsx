import React, { createContext, useContext, useState, ReactNode } from 'react';
import { Language, translations, defaultLanguage, getNestedTranslation } from './i18n';

interface I18nContextType {
  language: Language;
  setLanguage: (lang: Language) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

export const I18nContext = createContext<I18nContextType | undefined>(undefined);

export const I18nProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const savedLang = (localStorage.getItem('kitabim_language') as Language) || defaultLanguage;
  const [language, setLanguageState] = useState<Language>(savedLang);

  const setLanguage = (lang: Language) => {
    setLanguageState(lang);
    localStorage.setItem('kitabim_language', lang);
  };

  const t = (key: string, params?: Record<string, string | number>): string => {
    let translation = getNestedTranslation(translations[language], key);

    // Replace parameters if provided
    if (params) {
      Object.entries(params).forEach(([paramKey, value]) => {
        translation = translation.replace(`{{${paramKey}}}`, String(value));
      });
    }

    return translation;
  };

  return (
    <I18nContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </I18nContext.Provider>
  );
};

export const useI18n = (): I18nContextType => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return context;
};
