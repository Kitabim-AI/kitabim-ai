import React from 'react';
import { X, Save, BookType, Tag } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

interface TagEditorProps {
  isOpen: boolean;
  onOpen?: () => void;
  onClose: () => void;
  onSave: () => void;
  items: string[];
  tempValue: string;
  onTempValueChange: (val: string) => void;
  onAddItem: (val: string) => void;
  onRemoveItem: (index: number) => void;
  existingItems: string[];
  placeholder?: string;
}

export const TagEditor: React.FC<TagEditorProps & { hideActions?: boolean }> = ({
  isOpen,
  onOpen,
  onClose,
  onSave,
  items,
  tempValue,
  onTempValueChange,
  onAddItem,
  onRemoveItem,
  existingItems,
  placeholder,
  hideActions
}) => {
  const { t } = useI18n();

  if (isOpen) {
    return (
      <div className="flex flex-col gap-2 min-w-[180px]" dir="rtl">
        <div className="flex flex-wrap gap-1">
          {items.map((item: string, idx: number) => (
            <span key={idx} className="flex items-center gap-1 px-2 py-0.5 bg-[#0369a1]/10 text-[#0369a1] text-[13px] rounded-md border border-[#0369a1]/20">
              {item}
              <button onClick={() => onRemoveItem(idx)} className="hover:text-red-500"><X size={10} /></button>
            </span>
          ))}
        </div>
        <div className="flex gap-1 items-center">
          <input
            autoFocus
            type="text"
            value={tempValue}
            onChange={e => e.target.value.endsWith(',') ? onAddItem(e.target.value.slice(0, -1).trim()) : onTempValueChange(e.target.value)}
            onKeyDown={e => e.key === 'Enter' ? (tempValue.trim() ? onAddItem(tempValue.trim()) : (onSave && onSave())) : (e.key === 'Backspace' && !tempValue && onRemoveItem(items.length - 1))}
            className="px-2 py-1 text-sm border border-[#0369a1]/20 rounded-lg bg-white flex-grow outline-none"
            placeholder={placeholder}
          />
          {!hideActions && (
            <>
              <button onClick={() => { if (tempValue.trim()) onAddItem(tempValue.trim()); onSave(); }} className="p-1.5 bg-[#0369a1] text-white rounded-lg hover:bg-[#0284c7]"><Save size={14} /></button>
              <button onClick={onClose} className="p-1.5 bg-slate-100 text-slate-400 rounded-lg"><X size={14} /></button>
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={onOpen}
      className={`flex flex-wrap gap-1 p-1 rounded-lg transition-all min-h-[32px] items-center ${onOpen ? 'cursor-pointer hover:bg-[#0369a1]/5' : 'cursor-default'}`}
    >
      {existingItems.length > 0 ? existingItems.map((cat: string, i: number) => <span key={i} className="px-2 py-0.5 bg-[#0369a1]/5 text-[#0369a1] text-[13px] rounded-md border border-[#0369a1]/10">{cat}</span>) : <span className="text-[12px] text-slate-300 italic flex items-center gap-1"><Tag size={12} /> {placeholder}</span>}
    </div>
  );
};
