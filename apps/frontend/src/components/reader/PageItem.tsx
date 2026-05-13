import { Edit3, Loader2, RotateCcw, Save } from 'lucide-react';
import React from 'react';
import { useIsEditor } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { MarkdownContent } from '../common/MarkdownContent';

interface PageItemProps {
  page: any;
  isActive: boolean;
  isEditing: boolean;
  fontSize: number;
  contentFontFamily?: string;
  contentFontClassName?: string;
  onSetActive: () => void;
  onEdit: () => void;
  onReprocess: () => void;

  tempText: string;
  onTempTextChange: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
  isLoading: boolean;
  isSaving?: boolean;
  isFullscreen?: boolean;
}

export const PageItem: React.FC<PageItemProps> = ({
  page, isActive, isEditing, fontSize, contentFontFamily, contentFontClassName, onSetActive, onEdit, onReprocess,
  tempText, onTempTextChange, onSave, onCancel, isLoading, isSaving, isFullscreen
}) => {
  const { t } = useI18n();
  const isEditor = useIsEditor();

  return (
    <div onMouseEnter={onSetActive} className={`group relative p-6 rounded-[24px] transition-all duration-300 border ${isEditing ? 'flex-1 flex flex-col min-h-0' : ''} ${isActive ? 'bg-white shadow-xl border-[#0369a1]/10' : 'border-transparent'}`}>
      <div className="flex items-center justify-between mb-4 border-b border-[#0369a1]/5 pb-3">
        <div className="flex items-center gap-2">
          {isEditor && !isEditing && (
            <div className={`flex items-center gap-2 transition-all ${isFullscreen ? 'hidden' : `${isActive ? 'opacity-100' : 'opacity-0'} sm:group-hover:opacity-100`}`}>
              <button onClick={onReprocess} className="p-2 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-lg" title={t('reader.reprocessPage')}><RotateCcw size={14} /></button>
              <button onClick={onEdit} className="flex items-center gap-2 px-3 py-1.5 bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white rounded-lg text-xs font-bold uppercase"><Edit3 size={12} /> {t('reader.editPage')}</button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-[#94a3b8] uppercase">{t('chat.pageNumber', { page: page.pageNumber })}</span>
        </div>
      </div>

      {isEditing ? (
        <div className="flex-1 flex flex-col gap-4 min-h-0">
          <div className="relative flex-1 flex flex-col min-h-0">
            <textarea value={tempText} onChange={(e) => onTempTextChange(e.target.value)} className={`flex-1 w-full p-4 uyghur-text border-2 border-[#0369a1] rounded-xl outline-none resize-none bg-white relative z-10 min-h-0 custom-scrollbar ${contentFontClassName || ''}`} style={{ fontSize: `${fontSize}px`, fontFamily: contentFontFamily }} dir="rtl" />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={onSave}
              disabled={isSaving}
              className="px-6 py-2 bg-[#0369a1] text-white rounded-xl text-sm hover:bg-[#0284c7] transition-all flex items-center gap-2 disabled:opacity-50"
            >
              {isSaving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
              {t('common.save')}
            </button>
            <button
              onClick={onCancel}
              disabled={isSaving}
              className="px-6 py-2 bg-slate-100 text-slate-400 rounded-xl text-sm transition-all disabled:opacity-30"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      ) : (
        isLoading ? (
          <div className="flex flex-col items-center justify-center py-10 opacity-50"><Loader2 className="animate-spin text-[#0369a1] mb-2" /><span className="text-xs uppercase">{t('admin.table.recognizing')}</span></div>
        ) : (
          <MarkdownContent content={page.text || "..."} className={`uyghur-text text-[#1a1a1a] ${contentFontClassName || ''}`} style={{ fontSize: `${fontSize}px`, fontFamily: contentFontFamily }} />
        )
      )}
    </div>
  );
};
