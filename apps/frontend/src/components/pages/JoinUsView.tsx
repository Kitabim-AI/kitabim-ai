import React, { useState } from 'react';
import {
  Users,
  FileEdit,
  Code,
  Heart,
  Mail,
  BookOpen,
  AlertCircle,
  Github,
  Send,
  X,
  ArrowLeft,
  Sparkles
} from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

const JoinUsView: React.FC = () => {
  const { t } = useI18n();
  const { setView, previousView } = useAppContext();
  const [showContactModal, setShowContactModal] = useState(false);
  const [contactForm, setContactForm] = useState({
    name: '',
    email: '',
    message: '',
    interest: 'editor' // editor, developer, other
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // In a real app, this would send to an API
    console.log('Contact form submitted:', contactForm);
    alert(t('common.success'));
    setShowContactModal(false);
    setContactForm({ name: '', email: '', message: '', interest: 'editor' });
  };

  return (
    <div className="flex flex-col items-center animate-fade-in py-12" dir="rtl" lang="ug">
      {/* Back Button */}
      <div className="w-full max-w-6xl mb-8 flex justify-start px-4">
        <button
          onClick={() => setView(previousView || 'home')}
          className="p-3 bg-white/40 hover:bg-[#0369a1] text-[#0369a1] hover:text-white rounded-2xl transition-all shadow-sm active:scale-90 flex items-center gap-2 group"
        >
          <ArrowLeft size={20} strokeWidth={3} className="group-hover:-translate-x-1 transition-transform" />
        </button>
      </div>

      {/* Hero Section */}
      <div className="text-center mb-16 px-4">
        <div className="flex flex-col items-center gap-6">
          <div className="px-8 py-2.5 bg-[#0369a1] text-white rounded-full text-[14px] font-bold uppercase mb-4 border border-[#0369a1]/20 shadow-[0_8px_20px_rgba(3,105,161,0.2)] flex items-center gap-2">
            <Users size={18} />
            {t('joinUs.hero.badge')}
          </div>
          <h1 className="font-black text-[#1a1a1a] leading-tight text-5xl md:text-7xl mb-2">
            {t('joinUs.hero.title')}
          </h1>
          <p className="uyghur-text text-xl md:text-2xl text-slate-600 max-w-3xl leading-relaxed opacity-80">
            {t('joinUs.hero.subtitle')}
          </p>
        </div>
      </div>

      <div className="w-full max-w-6xl px-4 space-y-24 pb-20">
        {/* Who We Are - Now Full Width at the Top */}
        <div className="glass-panel rounded-[40px] p-8 md:p-12 border border-white/40 flex flex-col gap-8 transition-transform hover:scale-[1.005] bg-white/60">
          <div className="flex items-center gap-6">
            <div className="p-5 rounded-[24px] shadow-lg shrink-0 bg-gradient-to-br from-[#FFD54F] to-[#FF9800]">
              <BookOpen size={36} className="text-white" />
            </div>
            <h2 className="text-3xl md:text-4xl font-black text-[#1a1a1a]">{t('joinUs.whoWeAre.title')}</h2>
          </div>
          <div className="uyghur-text text-xl text-slate-700 space-y-6 leading-relaxed max-w-5xl">
            <p>{t('joinUs.whoWeAre.paragraph1')}</p>
            <p>{t('joinUs.whoWeAre.paragraph2')}</p>
          </div>
        </div>

        {/* Other Sections Side-by-Side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-10">
          {/* Why Spelling Mistakes */}
          <div className="glass-panel rounded-[40px] p-8 md:p-12 border border-[#FF9800]/10 bg-gradient-to-br from-white/90 to-orange-50/30 flex flex-col gap-8 transition-transform hover:scale-[1.01]">
            <div className="flex items-center gap-5">
              <div className="p-4 rounded-[20px] shadow-lg shrink-0 bg-gradient-to-br from-orange-400 to-rose-500">
                <AlertCircle size={32} className="text-white" />
              </div>
              <h2 className="text-2xl lg:text-3xl font-bold text-[#1a1a1a]">{t('joinUs.spellingMistakes.title')}</h2>
            </div>
            <div className="uyghur-text text-lg text-slate-700 space-y-4">
              <p>{t('joinUs.spellingMistakes.paragraph1')}</p>
              <p>{t('joinUs.spellingMistakes.paragraph2')}</p>
            </div>
          </div>

          {/* Smart Library */}
          <div className="glass-panel rounded-[40px] p-8 md:p-12 border border-sky-300/20 bg-gradient-to-br from-white/90 to-sky-50/30 flex flex-col gap-8 transition-transform hover:scale-[1.01]">
            <div className="flex items-center gap-5">
              <div className="p-4 rounded-[20px] shadow-lg shrink-0 bg-gradient-to-br from-sky-400 to-blue-600">
                <Sparkles size={32} className="text-white" />
              </div>
              <h2 className="text-2xl lg:text-3xl font-bold text-[#1a1a1a]">{t('joinUs.smartLibrary.title')}</h2>
            </div>
            <div className="uyghur-text text-lg text-slate-700 space-y-4">
              <p>{t('joinUs.smartLibrary.paragraph1')}</p>
              <p>{t('joinUs.smartLibrary.paragraph2')}</p>
            </div>
          </div>
        </div>

        {/* Action Cards */}
        <div className="space-y-12">
          <div className="text-center">
            <h2 className="text-4xl font-bold text-[#1a1a1a] mb-4">{t('joinUs.howToHelp.title')}</h2>
            <p className="text-slate-500 text-lg">{t('joinUs.howToHelp.subtitle')}</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {/* Editor Card */}
            <div className="glass-panel group rounded-[32px] p-8 border border-white/60 hover:border-purple-300 transition-all flex flex-col items-center gap-6">
              <div className="p-5 rounded-2xl bg-purple-100 text-purple-600 group-hover:scale-110 group-hover:bg-purple-600 group-hover:text-white transition-all duration-300">
                <FileEdit size={32} />
              </div>
              <h3 className="text-2xl font-bold text-[#1a1a1a]">{t('joinUs.howToHelp.editor.title')}</h3>
              <p className="uyghur-text text-slate-600 leading-relaxed text-lg text-right w-full">
                {t('joinUs.howToHelp.editor.description')}
              </p>
              <p className="uyghur-text text-slate-600 leading-relaxed text-lg text-right w-full font-bold">
                {t('joinUs.howToHelp.editor.benefit1')}
              </p>
              <ul className="uyghur-text w-full text-right space-y-2 mb-4 opacity-80 text-base">
                <li>• {t('joinUs.howToHelp.editor.benefit2')}</li>
                <li>• {t('joinUs.howToHelp.editor.benefit3')}</li>
              </ul>
              <button
                onClick={() => {
                  setContactForm({ ...contactForm, interest: 'editor' });
                  setShowContactModal(true);
                }}
                className="w-full py-4 bg-purple-600 text-white rounded-2xl font-bold hover:shadow-lg hover:shadow-purple-500/30 transition-all active:scale-95"
              >
                {t('joinUs.howToHelp.editor.button')}
              </button>
            </div>

            {/* Developer Card */}
            <div className="glass-panel group rounded-[32px] p-8 border border-white/60 hover:border-[#0369a1]/30 transition-all flex flex-col items-center gap-6">
              <div className="p-5 rounded-2xl bg-[#0369a1]/10 text-[#0369a1] group-hover:scale-110 group-hover:bg-[#0369a1] group-hover:text-white transition-all duration-300">
                <Code size={32} />
              </div>
              <h3 className="text-2xl font-bold text-[#1a1a1a]">{t('joinUs.howToHelp.developer.title')}</h3>
              <p className="uyghur-text text-slate-600 leading-relaxed text-lg text-right w-full">
                {t('joinUs.howToHelp.developer.description')}
              </p>
              <p className="uyghur-text text-slate-600 leading-relaxed text-lg text-right w-full font-bold">
                {t('joinUs.howToHelp.developer.benefit1')}
              </p>
              <ul className="uyghur-text w-full text-right space-y-2 mb-4 opacity-80 text-base">
                <li>• {t('joinUs.howToHelp.developer.benefit2')}</li>
                <li>• {t('joinUs.howToHelp.developer.benefit3')}</li>
              </ul>
              <button
                onClick={() => {
                  setContactForm({ ...contactForm, interest: 'developer' });
                  setShowContactModal(true);
                }}
                className="w-full py-4 bg-[#0369a1] text-white rounded-2xl font-bold hover:shadow-lg hover:shadow-sky-500/30 transition-all active:scale-95"
              >
                {t('joinUs.howToHelp.developer.button')}
              </button>
            </div>

            {/* Donate Card */}
            <div className="glass-panel group rounded-[32px] p-8 border border-white/60 hover:border-rose-300 transition-all flex flex-col items-center gap-6">
              <div className="p-5 rounded-2xl bg-rose-100 text-rose-600 group-hover:scale-110 group-hover:bg-rose-600 group-hover:text-white transition-all duration-300">
                <Heart size={32} />
              </div>
              <h3 className="text-2xl font-bold text-[#1a1a1a]">{t('joinUs.howToHelp.donate.title')}</h3>
              <p className="uyghur-text text-slate-600 leading-relaxed text-lg text-right w-full">
                {t('joinUs.howToHelp.donate.description')}
              </p>
              <p className="uyghur-text text-slate-600 leading-relaxed text-lg text-right w-full font-bold">
                {t('joinUs.howToHelp.donate.benefit1')}
              </p>
              <ul className="uyghur-text w-full text-right space-y-2 mb-4 opacity-80 text-base">
                <li>• {t('joinUs.howToHelp.donate.benefit2')}</li>
                <li>• {t('joinUs.howToHelp.donate.benefit3')}</li>
              </ul>
              <button
                onClick={() => alert(t('joinUs.howToHelp.donate.comingSoon'))}
                className="w-full py-4 bg-rose-600 text-white rounded-2xl font-bold hover:shadow-lg hover:shadow-rose-500/30 transition-all active:scale-95"
              >
                {t('joinUs.howToHelp.donate.button')}
              </button>
            </div>
          </div>
        </div>

        {/* Contact Strip */}
        <div className="glass-panel rounded-[40px] p-12 border border-white/60 flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="text-right">
            <h2 className="text-3xl font-bold text-[#1a1a1a] mb-2">{t('joinUs.contact.title')}</h2>
            <p className="uyghur-text text-slate-500">{t('joinUs.contact.description')}</p>
          </div>
          <div className="flex gap-4">
            <button
              onClick={() => setShowContactModal(true)}
              className="px-10 py-4 bg-white text-[#1a1a1a] border border-[#0369a1]/10 rounded-2xl font-bold hover:bg-[#0369a1] hover:text-white transition-all shadow-sm active:scale-95 flex items-center gap-2"
            >
              <Send size={18} />
              {t('joinUs.contact.button')}
            </button>
            <a
              href="https://github.com/omarjan/kitabim-ai"
              target="_blank"
              rel="noopener noreferrer"
              className="px-6 py-4 bg-slate-800 text-white rounded-2xl font-bold hover:bg-black transition-all shadow-sm active:scale-95 flex items-center gap-2"
            >
              <Github size={20} />
            </a>
          </div>
        </div>
      </div>

      {/* Modal Backdrop and Content */}
      {showContactModal && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-[#0369a1]/20 backdrop-blur-md" onClick={() => setShowContactModal(false)} />
          <div className="glass-panel bg-white/95 w-full max-w-xl rounded-[40px] shadow-2xl relative z-10 overflow-hidden animate-fade-in border border-white">
            <div className="p-10">
              <div className="flex justify-between items-center mb-10">
                <h3 className="text-3xl font-bold text-[#1a1a1a]">{t('joinUs.contactModal.title')}</h3>
                <button onClick={() => setShowContactModal(false)} className="p-3 hover:bg-slate-100 rounded-2xl transition-all">
                  <X size={24} />
                </button>
              </div>

              <form onSubmit={handleSubmit} className="space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mr-2">{t('joinUs.contactModal.interest')}</label>
                  <select
                    value={contactForm.interest}
                    onChange={(e) => setContactForm({ ...contactForm, interest: e.target.value })}
                    className="w-full p-4 bg-slate-50 border-2 border-slate-100 rounded-2xl focus:border-[#0369a1] outline-none transition-all uyghur-text"
                  >
                    <option value="editor">{t('joinUs.contactModal.interestEditor')}</option>
                    <option value="developer">{t('joinUs.contactModal.interestDeveloper')}</option>
                    <option value="other">{t('joinUs.contactModal.interestOther')}</option>
                  </select>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-slate-400 uppercase tracking-wider mr-2">{t('joinUs.contactModal.name')}</label>
                    <input
                      type="text"
                      required
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
                      required
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
                    required
                    rows={4}
                    className="w-full p-4 bg-slate-50 border-2 border-slate-100 rounded-2xl focus:border-[#0369a1] outline-none transition-all resize-none uyghur-text"
                    placeholder={t('joinUs.contactModal.messagePlaceholder')}
                    value={contactForm.message}
                    onChange={(e) => setContactForm({ ...contactForm, message: e.target.value })}
                  />
                </div>

                <button
                  type="submit"
                  className="w-full py-5 bg-[#0369a1] text-white rounded-2xl font-bold text-lg hover:shadow-xl hover:shadow-[#0369a1]/20 transition-all active:scale-95 mt-4"
                >
                  {t('joinUs.contactModal.submit')}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default JoinUsView;
