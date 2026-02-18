import React from 'react';
import { RotateCcw, Edit3, Wand2, CheckCircle2, Save, Loader2 } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { MarkdownContent } from '../common/MarkdownContent';
import { HighlightedText } from '../spell-check/HighlightedText';
import { useIsEditor } from '../../hooks/useAuth';

interface PageItemProps {
  page: any;
  isActive: boolean;
  isEditing: boolean;
  fontSize: number;
  onSetActive: () => void;
  onEdit: () => void;
  onReprocess: () => void;
  onSpellCheck: () => void;
  tempText: string;
  onTempTextChange: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
  spellCheckResult: any;
  isLoading: boolean;
}

export const PageItem: React.FC<PageItemProps> = ({
  page, isActive, isEditing, fontSize, onSetActive, onEdit, onReprocess, onSpellCheck,
  tempText, onTempTextChange, onSave, onCancel, spellCheckResult, isLoading
}) => {
  const { t } = useI18n();
  const isEditor = useIsEditor();

  return (
    <div onMouseEnter={onSetActive} className={`relative p-6 rounded-[24px] transition-all duration-300 ${isActive ? 'bg-white shadow-xl scale-[1.02] border border-[#0369a1]/10' : 'opacity-80'}`}>
      <div className="flex items-center justify-between mb-4 border-b border-[#0369a1]/5 pb-3">
        <div className="flex items-center gap-2">
          {isEditor && !isEditing && (
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-all transition-all">
              <button onClick={onReprocess} className="p-2 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-lg"><RotateCcw size={14} /></button>
              <button onClick={onEdit} className="flex items-center gap-2 px-3 py-1.5 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-lg text-xs font-bold uppercase"><Edit3 size={12} /> {t('reader.editPage')}</button>
              <button onClick={onSpellCheck} className="p-2 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-lg"><Wand2 size={14} /></button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-[#94a3b8] uppercase">{t('chat.pageNumber', { page: page.pageNumber })}</span>
          {page.isVerified && <span className="flex items-center gap-1 text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full text-xs font-bold"><CheckCircle2 size={10} /> {t('reader.verified')}</span>}
        </div>
      </div>

      {isEditing ? (
        <div className="flex flex-col gap-4">
          <div className="relative w-full">
            {spellCheckResult?.corrections.length > 0 && (
              <div className="absolute inset-0 p-4 pointer-events-none overflow-hidden">
                <HighlightedText text={tempText} corrections={spellCheckResult.corrections} className="uyghur-text leading-relaxed" style={{ fontSize: `${fontSize}px` }} isLayer={true} />
              </div>
            )}
            <textarea value={tempText} onChange={(e) => onTempTextChange(e.target.value)} className="w-full p-4 uyghur-text border-2 border-[#0369a1] rounded-xl outline-none resize-none bg-white relative z-10" style={{ fontSize: `${fontSize}px` }} dir="rtl" rows={Math.min(20, tempText.split('\n').length + 2)} />
          </div>
          <div className="flex items-center gap-3">
            <button onClick={onSave} className="px-6 py-2 bg-[#0369a1] text-white rounded-xl text-sm hover:bg-[#0284c7] transition-all flex items-center gap-2"><Save size={16} /> {t('common.save')}</button>
            <button onClick={onCancel} className="px-6 py-2 bg-slate-100 text-slate-400 rounded-xl text-sm transition-all">{t('common.cancel')}</button>
          </div>
        </div>
      ) : (
        isLoading ? (
          <div className="flex flex-col items-center justify-center py-10 opacity-50"><Loader2 className="animate-spin text-[#0369a1] mb-2" /><span className="text-xs uppercase">{t('admin.table.recognizing')}</span></div>
        ) : (
          <MarkdownContent content={page.text || "..."} className="uyghur-text text-[#1a1a1a] leading-relaxed" style={{ fontSize: `${fontSize}px` }} />
        )
      )}
    </div>
  );
};
