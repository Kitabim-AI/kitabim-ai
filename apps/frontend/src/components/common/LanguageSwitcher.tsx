import React from 'react';
import { Globe } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { Language } from '../../i18n/i18n';

export const LanguageSwitcher: React.FC = () => {
  const { language, setLanguage, t } = useI18n();

  const languages: { code: Language; label: string }[] = [
    { code: 'ug', label: 'ئۇيغۇرچە' },
    { code: 'en', label: 'English' },
  ];

  return (
    <div className="relative group">
      <button
        className="p-3 text-[#4a5568] hover:bg-[#0369a1]/10 hover:text-[#0369a1] rounded-xl transition-all duration-300 hover:-translate-y-0.5"
        title={t('nav.switchLanguage')}
      >
        <Globe size={20} strokeWidth={2.5} />
      </button>

      <div className="absolute left-0 top-full mt-2 bg-white/90 backdrop-blur-2xl rounded-2xl shadow-xl border border-[#0369a1]/20 overflow-hidden opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-300 min-w-[120px] z-50">
        {languages.map((lang) => (
          <button
            key={lang.code}
            onClick={() => setLanguage(lang.code)}
            className={`w-full px-4 py-2.5 text-sm font-normal transition-colors text-left ${language === lang.code
              ? 'bg-[#0369a1] text-white'
              : 'text-[#1a1a1a] hover:bg-[#0369a1]/10'
              }`}
          >
            {lang.label}
          </button>
        ))}
      </div>
    </div>
  );
};
