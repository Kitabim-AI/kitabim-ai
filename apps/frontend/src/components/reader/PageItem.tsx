import { BookmarkCheck, Edit3, ListTree, ListX, Loader2, RotateCcw, Save } from 'lucide-react';
import React from 'react';
import { useIsEditor } from '../../hooks/useAuth';
import { useI18n } from '../../i18n/I18nContext';
import { MarkdownContent } from '../common/MarkdownContent';

const normalizeArabic = (text: string): string => {
  if (!text) return '';
  return text
    .replace(/\u06E1/g, '\u0652') // Uthmanic Sukun -> Standard Sukun
    .replace(/\u0671/g, '\u0627') // Alif Wasla -> Standard Alif
    .replace(/[\u06D6-\u06DC\u06DF-\u06E0\u06E2-\u06ED]/g, '') // Remove Uthmanic signs that disrupt cursive connections
    ;
};

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
  onSetStartPage?: () => void;
  onToggleToc?: (nextIsToc: boolean) => void;

  tempText: string;
  onTempTextChange: (text: string) => void;
  onSave: () => void;
  onCancel: () => void;
  isLoading: boolean;
  isSaving?: boolean;
  isFullscreen?: boolean;
  contentPageOffset?: number;
  onTocPageClick?: (targetPage: number) => void;
}

export const PageItem: React.FC<PageItemProps> = ({
  page, isActive, isEditing, fontSize, contentFontFamily, contentFontClassName, onSetActive, onEdit, onReprocess, onSetStartPage, onToggleToc,
  tempText, onTempTextChange, onSave, onCancel, isLoading, isSaving, isFullscreen, contentPageOffset, onTocPageClick
}) => {
  const { t } = useI18n();
  const isEditor = useIsEditor();
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const containerRef = React.useRef<HTMLDivElement>(null);

  const adjustHeight = React.useCallback(() => {
    if (!isEditing || !textareaRef.current || !containerRef.current) return;
    const textarea = textareaRef.current;
    const container = containerRef.current;

    textarea.style.height = '100%';
    const containerHeight = container.clientHeight;
    textarea.style.height = 'auto';
    const contentHeight = textarea.scrollHeight;

    if (contentHeight > containerHeight && containerHeight > 0) {
      textarea.style.height = `${contentHeight}px`;
    } else {
      textarea.style.height = '100%';
    }
  }, [isEditing]);

  React.useEffect(() => {
    if (isEditing && textareaRef.current) {
      textareaRef.current.focus();
      adjustHeight();
    }
  }, [isEditing, tempText, fontSize, adjustHeight]);

  React.useEffect(() => {
    if (!isEditing || !containerRef.current) return;
    const observer = new ResizeObserver(() => adjustHeight());
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [isEditing, adjustHeight]);

  return (
    <div onMouseEnter={onSetActive} className={`group relative p-6 rounded-[24px] transition-all duration-300 border ${isEditing ? 'flex-1 flex flex-col min-h-0' : ''} ${isActive ? 'bg-white dark:bg-slate-900/60 shadow-xl border-[#0369a1]/10 dark:border-[#38bdf8]/10' : 'border-transparent'}`}>
      <div className="flex items-center justify-between mb-4 border-b border-[#0369a1]/5 dark:border-slate-800 pb-3">
        <div className="flex items-center gap-2">
          {isEditor && !isEditing && (
            <div className={`flex items-center gap-2 transition-all ${isFullscreen ? 'hidden' : `${isActive ? 'opacity-100' : 'opacity-0'} sm:group-hover:opacity-100`}`}>
              <button onClick={onReprocess} className="p-2 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-lg" title={t('reader.reprocessPage')}><RotateCcw size={14} /></button>
              <button onClick={onEdit} className="flex items-center gap-2 px-3 py-1.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-lg text-xs font-bold uppercase"><Edit3 size={12} /> <span className="hidden sm:inline">{t('reader.editPage')}</span></button>
              {onSetStartPage && (
                <button
                  onClick={onSetStartPage}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-lg text-xs font-bold uppercase"
                  title={t('reader.setStartPageTitle') || "Mark this physical page as Content Page 1"}
                >
                  <BookmarkCheck size={12} />
                  <span className="hidden sm:inline">{t('reader.setPageOne') || "Mark as Page 1"}</span>
                </button>
              )}
              {onToggleToc && (
                <button
                  onClick={() => onToggleToc(!(page?.isToc ?? page?.is_toc))}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 rounded-lg text-xs font-bold uppercase"
                  title={(page?.isToc ?? page?.is_toc) ? t('reader.unmarkAsTocTitle') : t('reader.markAsTocTitle')}
                >
                  {(page?.isToc ?? page?.is_toc) ? <ListX size={12} /> : <ListTree size={12} />}
                  <span className="hidden sm:inline">{(page?.isToc ?? page?.is_toc) ? t('reader.unmarkAsToc') : t('reader.markAsToc')}</span>
                </button>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-[#94a3b8] dark:text-slate-500 uppercase flex items-center gap-1.5">
            <span>{t('chat.pageNumber', { page: page.displayPageNumber || page.display_page_number || page.pageNumber })}</span>
            {(page.displayPageNumber || page.display_page_number) && String(page.displayPageNumber || page.display_page_number) !== String(page.pageNumber) && (
              <span className="text-[10px] opacity-60">(PDF {page.pageNumber})</span>
            )}
          </span>
        </div>
      </div>

      {isEditing ? (
        <div className="flex-1 flex flex-col gap-4 min-h-0">
          <div ref={containerRef} className="relative flex-1 flex flex-col min-h-[300px]">
            <textarea 
              ref={textareaRef}
              value={contentFontClassName === 'reader-font-adobe' ? normalizeArabic(tempText) : tempText} 
              onChange={(e) => onTempTextChange(contentFontClassName === 'reader-font-adobe' ? normalizeArabic(e.target.value) : e.target.value)} 
              className={`flex-1 w-full h-full p-4 uyghur-text border-2 border-[#0369a1] dark:border-[#38bdf8] rounded-xl outline-none resize-none bg-white dark:bg-slate-800 text-[#1a1a1a] dark:text-slate-100 relative z-10 custom-scrollbar leading-relaxed ${contentFontClassName || ''}`} 
              style={{ fontSize: `${fontSize}px`, fontFamily: contentFontFamily }} 
              dir="rtl" 
            />
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
              className="px-6 py-2 bg-slate-100 dark:bg-slate-800 text-slate-400 dark:text-slate-500 rounded-xl text-sm transition-all disabled:opacity-30"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      ) : (
        isLoading ? (
          <div className="flex flex-col items-center justify-center py-10 opacity-50"><Loader2 className="animate-spin text-[#0369a1] dark:text-[#38bdf8] mb-2" /><span className="text-xs uppercase dark:text-slate-400">{t('admin.table.recognizing')}</span></div>
        ) : (
          <MarkdownContent 
            content={contentFontClassName === 'reader-font-adobe' ? normalizeArabic(page.text || '') : (page.text || "...")} 
            className={`uyghur-text text-[#1a1a1a] dark:text-slate-100 ${contentFontClassName || ''}`} 
            style={{ fontSize: `${fontSize}px`, fontFamily: contentFontFamily }} 
            contentPageOffset={contentPageOffset}
            onTocPageClick={onTocPageClick}
          />
        )
      )}
    </div>
  );
};
