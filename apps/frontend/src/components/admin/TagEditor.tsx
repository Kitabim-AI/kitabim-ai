import React, { useState, useRef, useEffect } from 'react';
import { X, Save, BookType, Tag, Plus } from 'lucide-react';
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
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Get unique existing categories from all books (not just current book's categories)
  const allCategories = React.useMemo(() => {
    return Array.from(new Set(existingItems)).sort();
  }, [existingItems]);

  // Filter suggestions based on input and exclude already added items
  const suggestions = React.useMemo(() => {
    if (!tempValue.trim()) return allCategories.filter(cat => !items.includes(cat));
    const query = tempValue.toLowerCase().trim();
    return allCategories.filter(cat =>
      cat.toLowerCase().includes(query) && !items.includes(cat)
    );
  }, [tempValue, allCategories, items]);

  // Handle clicking outside to close suggestions
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node) &&
        inputRef.current &&
        !inputRef.current.contains(event.target as Node)
      ) {
        setShowSuggestions(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleAddTag = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !items.includes(trimmed)) {
      onAddItem(trimmed);
      setShowSuggestions(false);
    }
  };

  if (isOpen) {
    return (
      <div className="flex flex-col gap-2 min-w-[180px]" dir="rtl">
        {/* Current tags */}
        <div className="flex flex-wrap gap-1">
          {items.map((item: string, idx: number) => (
            <span key={idx} className="flex items-center gap-1 px-2 py-0.5 bg-[#0369a1]/10 text-[#0369a1] text-[13px] rounded-md border border-[#0369a1]/20">
              {item}
              <button onClick={() => onRemoveItem(idx)} className="hover:text-red-500"><X size={10} /></button>
            </span>
          ))}
        </div>

        {/* Input with + button */}
        <div className="relative">
          <div className="flex gap-1 items-center">
            <input
              ref={inputRef}
              autoFocus
              type="text"
              value={tempValue}
              onChange={e => {
                if (e.target.value.endsWith(',')) {
                  handleAddTag(e.target.value.slice(0, -1));
                } else {
                  onTempValueChange(e.target.value);
                  setShowSuggestions(true);
                }
              }}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  if (tempValue.trim()) {
                    handleAddTag(tempValue);
                  } else if (onSave) {
                    onSave();
                  }
                } else if (e.key === 'Backspace' && !tempValue && items.length > 0) {
                  onRemoveItem(items.length - 1);
                } else if (e.key === 'Escape') {
                  setShowSuggestions(false);
                }
              }}
              onFocus={() => setShowSuggestions(true)}
              className="px-2 py-1 text-sm border border-[#0369a1]/20 rounded-lg bg-white flex-grow outline-none"
              placeholder={placeholder}
            />

            {/* Add button */}
            <button
              onClick={() => handleAddTag(tempValue)}
              disabled={!tempValue.trim()}
              className="p-1.5 bg-[#0369a1]/10 text-[#0369a1] rounded-lg hover:bg-[#0369a1] hover:text-white transition-all disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-[#0369a1]/10 disabled:hover:text-[#0369a1]"
              title={t('common.add') || 'Add'}
            >
              <Plus size={14} strokeWidth={2.5} />
            </button>

            {!hideActions && (
              <>
                <button
                  onClick={() => {
                    // Add pending tag if there's text in the input
                    if (tempValue.trim() && !items.includes(tempValue.trim())) {
                      onAddItem(tempValue.trim());
                    }
                    // Clear the input
                    onTempValueChange('');
                    // Close suggestions
                    setShowSuggestions(false);
                    // Then save
                    onSave();
                  }}
                  className="p-1.5 bg-[#0369a1] text-white rounded-lg hover:bg-[#0284c7]"
                >
                  <Save size={14} />
                </button>
                <button onClick={onClose} className="p-1.5 bg-slate-100 text-slate-400 rounded-lg"><X size={14} /></button>
              </>
            )}
          </div>

          {/* Autocomplete dropdown */}
          {showSuggestions && suggestions.length > 0 && (
            <div
              ref={dropdownRef}
              className="absolute top-full left-0 right-0 mt-1 glass-panel shadow-lg z-[100] overflow-hidden max-h-[200px] overflow-y-auto"
              style={{ borderRadius: '12px' }}
            >
              <div className="py-1">
                {suggestions.slice(0, 10).map((suggestion, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleAddTag(suggestion)}
                    className="w-full text-left px-3 py-2 text-[13px] text-[#1a1a1a] hover:bg-[#0369a1]/10 transition-all flex items-center gap-2"
                  >
                    <Tag size={12} className="text-[#0369a1]" />
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Quick-add existing categories (when not searching) */}
        {!tempValue && allCategories.filter(cat => !items.includes(cat)).length > 0 && (
          <div className="flex flex-col gap-1">
            <div className="text-[11px] text-slate-400 uppercase tracking-wide">{t('admin.categories.existingCategories') || 'Existing Categories'}</div>
            <div className="flex flex-wrap gap-1">
              {allCategories
                .filter(cat => !items.includes(cat))
                .slice(0, 8)
                .map((cat, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleAddTag(cat)}
                    className="px-2 py-0.5 bg-slate-50 text-slate-600 text-[12px] rounded-md border border-slate-200 hover:bg-[#0369a1]/10 hover:text-[#0369a1] hover:border-[#0369a1]/20 transition-all"
                  >
                    {cat}
                  </button>
                ))}
            </div>
          </div>
        )}
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
