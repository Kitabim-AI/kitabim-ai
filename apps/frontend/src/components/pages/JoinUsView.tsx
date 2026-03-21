import React, { useState, useRef, useEffect } from 'react';
import {
  HeartHandshake,
  FileEdit,
  Code,
  Heart,
  Mail,
  BookOpen,
  AlertCircle,
  Github,
  Send,
  X,
  Bot,
  CheckCircle2,
  ChevronDown,
  Check
} from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { ProverbDisplay } from '../common/ProverbDisplay';
import { useAppContext } from '../../context/AppContext';
import { submitContactForm } from '../../services/contactService';

const JoinUsView: React.FC = () => {
  const { t } = useI18n();
  const { setView } = useAppContext();
  const [showContactModal, setShowContactModal] = useState(false);
  const [contactForm, setContactForm] = useState({
    name: '',
    email: '',
    message: '',
    interest: 'editor' as 'editor' | 'developer' | 'other'
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSuccess, setIsSuccess] = useState(false);
  const [showInterestDropdown, setShowInterestDropdown] = useState(false);
  const interestDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (interestDropdownRef.current && !interestDropdownRef.current.contains(event.target as Node)) {
        setShowInterestDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const interestColors: Record<string, { bg: string; text: string }> = {
    editor: { bg: 'bg-purple-50', text: 'text-purple-600' },
    developer: { bg: 'bg-sky-50', text: 'text-[#0369a1]' },
    other: { bg: 'bg-slate-50', text: 'text-slate-600' },
  };

  const handleCloseModal = () => {
    setShowContactModal(false);
    setTimeout(() => {
      setIsSuccess(false);
      setContactForm({ name: '', email: '', message: '', interest: 'editor' });
    }, 300);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError(null);

    // Manual validation with internationalized messages
    if (!contactForm.name.trim()) {
      setSubmitError(t('joinUs.contactModal.validation.nameRequired'));
      setIsSubmitting(false);
      return;
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!contactForm.email.trim()) {
      setSubmitError(t('joinUs.contactModal.validation.emailRequired'));
      setIsSubmitting(false);
      return;
    } else if (!emailRegex.test(contactForm.email)) {
      setSubmitError(t('joinUs.contactModal.validation.emailInvalid'));
      setIsSubmitting(false);
      return;
    }

    if (!contactForm.message.trim()) {
      setSubmitError(t('joinUs.contactModal.validation.messageRequired'));
      setIsSubmitting(false);
      return;
    } else if (contactForm.message.trim().length < 10) {
      setSubmitError(t('joinUs.contactModal.validation.messageMinLength'));
      setIsSubmitting(false);
      return;
    }

    try {
      await submitContactForm(contactForm);
      setIsSuccess(true);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : t('joinUs.contactModal.errorMessage');
      setSubmitError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col items-center py-6 sm:py-8 md:py-12" dir="rtl" lang="ug">
      <div className="w-full flex flex-col items-center animate-fade-in">

        {/* Hero Section */}
        <div className="text-center mb-12 sm:mb-14 md:mb-16 px-4">
          <div className="flex flex-col items-center gap-4 sm:gap-6">
            <div className="px-6 sm:px-8 py-2.5 bg-[#0369a1] text-white rounded-full text-xs sm:text-sm font-bold uppercase mb-3 sm:mb-4 border border-[#0369a1]/20 shadow-[0_8px_20px_rgba(3,105,161,0.2)] flex items-center gap-2">
              <HeartHandshake size={16} className="sm:w-[18px] sm:h-[18px]" />
              {t('joinUs.hero.badge')}
            </div>
            <h1 className="font-black text-[#1a1a1a] leading-tight text-3xl sm:text-4xl md:text-5xl lg:text-6xl xl:text-7xl mb-2">
              {t('joinUs.hero.title')}
            </h1>
            <p className="uyghur-text text-lg sm:text-xl md:text-2xl text-slate-600 max-w-3xl leading-relaxed opacity-80">
              {t('joinUs.hero.subtitle')}
            </p>
          </div>
        </div>

        <div className="w-full max-w-6xl px-4 space-y-16 sm:space-y-20 md:space-y-24 pb-12 sm:pb-16 md:pb-20">
          {/* Who We Are - Now Full Width at the Top */}
          <div className="glass-panel rounded-[32px] sm:rounded-[40px] p-6 sm:p-8 md:p-12 border border-white/40 flex flex-col gap-6 sm:gap-8 transition-transform hover:scale-[1.005] bg-white/60">
            <div className="flex items-center gap-4 sm:gap-6">
              <div className="p-4 sm:p-5 rounded-[20px] sm:rounded-[24px] shadow-lg shrink-0 bg-gradient-to-br from-[#FFD54F] to-[#FF9800]">
                <BookOpen size={28} className="sm:w-[36px] sm:h-[36px] text-white" />
              </div>
              <h2 className="text-2xl sm:text-3xl md:text-4xl font-black text-[#1a1a1a]">{t('joinUs.whoWeAre.title')}</h2>
            </div>
            <div className="uyghur-text text-lg sm:text-xl text-slate-700 space-y-4 sm:space-y-6 leading-relaxed max-w-5xl">
              <p>{t('joinUs.whoWeAre.paragraph1')}</p>
              <p>{t('joinUs.whoWeAre.paragraph2')}</p>
            </div>
          </div>

          {/* Other Sections Side-by-Side */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 sm:gap-8 md:gap-10">
            {/* Why Spelling Mistakes */}
            <div className="glass-panel rounded-[32px] sm:rounded-[40px] p-6 sm:p-8 md:p-12 border border-[#FF9800]/10 bg-gradient-to-br from-white/90 to-orange-50/30 flex flex-col gap-6 sm:gap-8 transition-transform hover:scale-[1.01]">
              <div className="flex items-center gap-4 sm:gap-5">
                <div className="p-3 sm:p-4 rounded-[16px] sm:rounded-[20px] shadow-lg shrink-0 bg-gradient-to-br from-orange-400 to-rose-500">
                  <AlertCircle size={28} className="sm:w-[32px] sm:h-[32px] text-white" />
                </div>
                <h2 className="text-xl sm:text-2xl lg:text-3xl font-bold text-[#1a1a1a]">{t('joinUs.spellingMistakes.title')}</h2>
              </div>
              <div className="uyghur-text text-base sm:text-lg text-slate-700 space-y-3 sm:space-y-4">
                <p>{t('joinUs.spellingMistakes.paragraph1')}</p>
                <p>{t('joinUs.spellingMistakes.paragraph2')}</p>
              </div>
            </div>

            {/* Smart Library */}
            <div className="glass-panel rounded-[32px] sm:rounded-[40px] p-6 sm:p-8 md:p-12 border border-sky-300/20 bg-gradient-to-br from-white/90 to-sky-50/30 flex flex-col gap-6 sm:gap-8 transition-transform hover:scale-[1.01]">
              <div className="flex items-center gap-4 sm:gap-5">
                <div className="p-3 sm:p-4 rounded-[16px] sm:rounded-[20px] shadow-lg shrink-0 bg-gradient-to-br from-sky-400 to-blue-600">
                  <Bot size={28} className="sm:w-[32px] sm:h-[32px] text-white" />
                </div>
                <h2 className="text-xl sm:text-2xl lg:text-3xl font-bold text-[#1a1a1a]">{t('joinUs.smartLibrary.title')}</h2>
              </div>
              <div className="uyghur-text text-base sm:text-lg text-slate-700 space-y-3 sm:space-y-4">
                <p>{t('joinUs.smartLibrary.paragraph1')}</p>
                <p>{t('joinUs.smartLibrary.paragraph2')}</p>
              </div>
            </div>
          </div>

          {/* Action Cards */}
          <div className="space-y-8 sm:space-y-10 md:space-y-12">
            <div className="text-center">
              <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold text-[#1a1a1a] mb-3 sm:mb-4">{t('joinUs.howToHelp.title')}</h2>
              <ProverbDisplay
                keywords={t('proverbs.joinUs')}
                size="base"
                className="opacity-60 items-center text-center"
                defaultText={t('joinUs.howToHelp.subtitle')}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 sm:gap-8">
              {/* Editor Card */}
              <div className="glass-panel group rounded-[24px] sm:rounded-[32px] p-6 sm:p-8 border border-white/60 hover:border-purple-300 transition-all flex flex-col items-center gap-5 sm:gap-6">
                <div className="p-4 sm:p-5 rounded-2xl bg-purple-100 text-purple-600 group-hover:scale-110 group-hover:bg-purple-600 group-hover:text-white transition-all duration-300">
                  <FileEdit size={28} className="sm:w-[32px] sm:h-[32px]" />
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-[#1a1a1a]">{t('joinUs.howToHelp.editor.title')}</h3>
                <p className="uyghur-text text-slate-600 leading-relaxed text-base sm:text-lg text-right w-full">
                  {t('joinUs.howToHelp.editor.description')}
                </p>
                <p className="uyghur-text text-slate-600 leading-relaxed text-base sm:text-lg text-right w-full font-bold">
                  {t('joinUs.howToHelp.editor.benefit1')}
                </p>
                <ul className="uyghur-text w-full text-right space-y-2 mb-4 opacity-80 text-sm sm:text-base">
                  <li>• {t('joinUs.howToHelp.editor.benefit2')}</li>
                  <li>• {t('joinUs.howToHelp.editor.benefit3')}</li>
                </ul>
                <button
                  onClick={() => {
                    setContactForm({ ...contactForm, interest: 'editor' });
                    setShowContactModal(true);
                  }}
                  className="w-full py-4 min-h-[48px] bg-purple-600 text-white rounded-2xl font-bold hover:shadow-lg hover:shadow-purple-500/30 transition-all active:scale-95"
                >
                  {t('joinUs.howToHelp.editor.button')}
                </button>
              </div>

              {/* Developer Card */}
              <div className="glass-panel group rounded-[24px] sm:rounded-[32px] p-6 sm:p-8 border border-white/60 hover:border-[#0369a1]/30 transition-all flex flex-col items-center gap-5 sm:gap-6">
                <div className="p-4 sm:p-5 rounded-2xl bg-[#0369a1]/10 text-[#0369a1] group-hover:scale-110 group-hover:bg-[#0369a1] group-hover:text-white transition-all duration-300">
                  <Code size={28} className="sm:w-[32px] sm:h-[32px]" />
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-[#1a1a1a]">{t('joinUs.howToHelp.developer.title')}</h3>
                <p className="uyghur-text text-slate-600 leading-relaxed text-base sm:text-lg text-right w-full">
                  {t('joinUs.howToHelp.developer.description')}
                </p>
                <p className="uyghur-text text-slate-600 leading-relaxed text-base sm:text-lg text-right w-full font-bold">
                  {t('joinUs.howToHelp.developer.benefit1')}
                </p>
                <ul className="uyghur-text w-full text-right space-y-2 mb-4 opacity-80 text-sm sm:text-base">
                  <li>• {t('joinUs.howToHelp.developer.benefit2')}</li>
                  <li>• {t('joinUs.howToHelp.developer.benefit3')}</li>
                </ul>
                <button
                  onClick={() => {
                    setContactForm({ ...contactForm, interest: 'developer' });
                    setShowContactModal(true);
                  }}
                  className="w-full py-4 min-h-[48px] bg-[#0369a1] text-white rounded-2xl font-bold hover:shadow-lg hover:shadow-sky-500/30 transition-all active:scale-95"
                >
                  {t('joinUs.howToHelp.developer.button')}
                </button>
              </div>

              {/* Donate Card */}
              <div className="glass-panel group rounded-[24px] sm:rounded-[32px] p-6 sm:p-8 border border-white/60 hover:border-rose-300 transition-all flex flex-col items-center gap-5 sm:gap-6">
                <div className="p-4 sm:p-5 rounded-2xl bg-rose-100 text-rose-600 group-hover:scale-110 group-hover:bg-rose-600 group-hover:text-white transition-all duration-300">
                  <Heart size={28} className="sm:w-[32px] sm:h-[32px]" />
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-[#1a1a1a]">{t('joinUs.howToHelp.donate.title')}</h3>
                <p className="uyghur-text text-slate-600 leading-relaxed text-base sm:text-lg text-right w-full">
                  {t('joinUs.howToHelp.donate.description')}
                </p>
                <p className="uyghur-text text-slate-600 leading-relaxed text-base sm:text-lg text-right w-full font-bold">
                  {t('joinUs.howToHelp.donate.benefit1')}
                </p>
                <ul className="uyghur-text w-full text-right space-y-2 mb-4 opacity-80 text-sm sm:text-base">
                  <li>• {t('joinUs.howToHelp.donate.benefit2')}</li>
                  <li>• {t('joinUs.howToHelp.donate.benefit3')}</li>
                </ul>
                <a
                  href="https://www.paypal.com/donate/?hosted_button_id=TKHXS8HCDUEJA"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full py-4 min-h-[48px] bg-rose-600 text-white rounded-2xl font-bold hover:shadow-lg hover:shadow-rose-500/30 transition-all active:scale-95 flex items-center justify-center gap-3"
                >
                  <Heart size={20} className="fill-current" />
                  <span>{t('joinUs.howToHelp.donate.button')}</span>
                </a>
              </div>
            </div>
          </div>

          {/* Sponsors Strip */}
          <div className="glass-panel rounded-[32px] sm:rounded-[40px] p-6 sm:p-8 md:p-12 border border-white/60 flex flex-col md:flex-row items-center justify-between gap-6 sm:gap-8 overflow-hidden relative group">
            <div className="absolute top-0 right-0 w-32 h-32 bg-[#0369a1]/5 rounded-full blur-3xl -mr-16 -mt-16 group-hover:bg-[#0369a1]/10 transition-colors" />
            <div className="text-center md:text-right w-full md:w-auto z-10">
              <h2 className="text-2xl sm:text-3xl font-bold text-[#1a1a1a] mb-2">{t('joinUs.sponsors.title')}</h2>
              <p className="uyghur-text text-sm sm:text-base text-slate-500">{t('joinUs.sponsors.subtitle')}</p>
            </div>
            <a
              href="https://www.dallasuyghurcommunity.org"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center p-2 z-10 active:scale-95 group/logo"
            >
              <img
                src="https://dallasuyghurcommunity.org/wp-content/uploads/2025/01/DUC_Logo_3ai_Artboard-2-photoaidcom-cropped-1.png"
                alt="Dallas Uyghur Community Logo"
                className="h-20 md:h-24 lg:h-32 w-auto object-contain group-hover/logo:scale-105 transition-transform"
              />
            </a>
          </div>

          {/* Contact Strip */}
          <div className="glass-panel rounded-[32px] sm:rounded-[40px] p-6 sm:p-8 md:p-12 border border-white/60 flex flex-col md:flex-row items-center justify-between gap-6 sm:gap-8">
            <div className="text-center md:text-right w-full md:w-auto">
              <h2 className="text-2xl sm:text-3xl font-bold text-[#1a1a1a] mb-2">{t('joinUs.contact.title')}</h2>
              <p className="uyghur-text text-sm sm:text-base text-slate-500 mb-3">{t('joinUs.contact.description')}</p>
              <p className="uyghur-text text-slate-500 font-medium text-base flex flex-wrap items-center justify-center md:justify-start gap-x-2 gap-y-1">
                <span>{t('joinUs.contact.emailLabel')}</span>
                <a href="mailto:contact@kitabim.ai" className="text-[#0369a1] hover:underline font-bold" dir="ltr">contact@kitabim.ai</a>
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 w-full md:w-auto">
              <button
                onClick={() => {
                  setContactForm({ ...contactForm, interest: 'other' });
                  setShowContactModal(true);
                }}
                className="px-6 sm:px-10 py-4 min-h-[48px] bg-white text-[#1a1a1a] border border-[#0369a1]/10 rounded-2xl font-bold hover:bg-[#0369a1] hover:text-white transition-all shadow-sm active:scale-95 flex items-center justify-center gap-2"
              >
                <Send size={18} />
                {t('joinUs.contact.button')}
              </button>
              <a
                href="https://github.com/omarjan/kitabim-ai"
                target="_blank"
                rel="noopener noreferrer"
                className="px-6 py-4 min-h-[48px] bg-slate-800 text-white rounded-2xl font-bold hover:bg-black transition-all shadow-sm active:scale-95 flex items-center justify-center gap-2"
              >
                <Github size={20} />
              </a>
            </div>
          </div>
        </div>
      </div>

      {/* Modal Backdrop and Content */}
      {showContactModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6">
          <div className="absolute inset-0 bg-[#0369a1]/20 backdrop-blur-md" onClick={handleCloseModal} />
          <div className="glass-panel bg-white/95 w-full max-w-xl rounded-[32px] sm:rounded-[40px] shadow-2xl relative z-10 overflow-y-auto max-h-[90vh] animate-fade-in border border-white">
            <div className="p-6 sm:p-10">
              {isSuccess ? (
                <div className="flex flex-col items-center justify-center text-center py-8">
                  <div className="w-20 h-20 bg-green-100 text-green-600 rounded-full flex items-center justify-center mb-6">
                    <CheckCircle2 size={40} />
                  </div>
                  <h3 className="text-2xl font-bold text-[#1a1a1a] mb-2">{t('joinUs.contactModal.successTitle')}</h3>
                  <p className="uyghur-text text-slate-500 text-lg mb-8">{t('joinUs.contactModal.successMessage')}</p>
                  <button
                    onClick={handleCloseModal}
                    className="w-full py-4 bg-slate-100 hover:bg-slate-200 text-[#1a1a1a] rounded-2xl font-bold transition-all text-lg"
                  >
                    {t('common.close')}
                  </button>
                </div>
              ) : (
                <>
                  <div className="flex justify-between items-center mb-10">
                    <h3 className="text-3xl font-bold text-[#1a1a1a]">{t('joinUs.contactModal.title')}</h3>
                    <button onClick={handleCloseModal} className="p-3 hover:bg-slate-100 rounded-2xl transition-all">
                      <X size={24} />
                    </button>
                  </div>

                  <form onSubmit={handleSubmit} className="space-y-6" noValidate>
                    <div className="space-y-2">
                      <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mr-2">{t('joinUs.contactModal.interest')}</label>
                      <div className="relative" ref={interestDropdownRef}>
                        <button
                          type="button"
                          onClick={() => setShowInterestDropdown(!showInterestDropdown)}
                          className={`w-full flex items-center justify-between p-4 ${interestColors[contactForm.interest]?.bg || 'bg-slate-50'} ${interestColors[contactForm.interest]?.text || 'text-slate-600'} border-2 ${showInterestDropdown ? 'border-[#0369a1]' : 'border-slate-100'} rounded-2xl transition-all uyghur-text group`}
                        >
                          <span className="font-bold">
                            {contactForm.interest === 'editor' && t('joinUs.contactModal.interestEditor')}
                            {contactForm.interest === 'developer' && t('joinUs.contactModal.interestDeveloper')}
                            {contactForm.interest === 'other' && t('joinUs.contactModal.interestOther')}
                          </span>
                          <ChevronDown size={20} className={`transition-transform duration-300 ${showInterestDropdown ? 'rotate-180' : ''}`} />
                        </button>

                        {showInterestDropdown && (
                          <div className="absolute top-full left-0 right-0 mt-2 glass-panel bg-white/95 shadow-2xl z-[150] overflow-hidden py-2 border border-[#0369a1]/10 rounded-[20px]">
                            {(['editor', 'developer', 'other'] as const).map((interest) => (
                              <button
                                key={interest}
                                type="button"
                                onClick={() => {
                                  setContactForm({ ...contactForm, interest });
                                  setShowInterestDropdown(false);
                                }}
                                className={`w-full flex items-center justify-between px-6 py-4 text-lg font-bold transition-all ${interest === contactForm.interest ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                              >
                                <span>
                                  {interest === 'editor' && t('joinUs.contactModal.interestEditor')}
                                  {interest === 'developer' && t('joinUs.contactModal.interestDeveloper')}
                                  {interest === 'other' && t('joinUs.contactModal.interestOther')}
                                </span>
                                {interest === contactForm.interest && <Check size={18} strokeWidth={3} />}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mr-2">{t('joinUs.contactModal.name')}</label>
                        <input
                          type="text"
                          className="w-full p-4 bg-slate-50 border-2 border-slate-100 rounded-2xl focus:border-[#0369a1] outline-none transition-all"
                          placeholder={t('joinUs.contactModal.namePlaceholder')}
                          value={contactForm.name}
                          onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })}
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mr-2">{t('joinUs.contactModal.email')}</label>
                        <input
                          type="email"
                          className="w-full p-4 bg-slate-50 border-2 border-slate-100 rounded-2xl focus:border-[#0369a1] outline-none transition-all"
                          placeholder={t('joinUs.contactModal.emailPlaceholder')}
                          value={contactForm.email}
                          onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })}
                        />
                      </div>
                    </div>

                    <div className="space-y-2">
                      <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mr-2">{t('joinUs.contactModal.message')}</label>
                      <textarea
                        rows={4}
                        className="w-full p-4 bg-slate-50 border-2 border-slate-100 rounded-2xl focus:border-[#0369a1] outline-none transition-all resize-none uyghur-text"
                        placeholder={t('joinUs.contactModal.messagePlaceholder')}
                        value={contactForm.message}
                        onChange={(e) => setContactForm({ ...contactForm, message: e.target.value })}
                      />
                    </div>

                    {submitError && (
                      <div className="p-4 bg-red-50 border-2 border-red-200 rounded-2xl">
                        <p className="text-red-600 text-sm font-medium">{submitError}</p>
                      </div>
                    )}

                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className={`w-full py-5 rounded-2xl font-bold text-lg transition-all mt-4 ${isSubmitting
                        ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                        : 'bg-[#0369a1] text-white hover:shadow-xl hover:shadow-[#0369a1]/20 active:scale-95'
                        }`}
                    >
                      {isSubmitting ? t('joinUs.contactModal.submitting') : t('joinUs.contactModal.submit')}
                    </button>
                  </form>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default JoinUsView;
