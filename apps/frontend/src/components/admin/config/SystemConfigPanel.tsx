/**
 * System Config Panel - CRUD interface for system configurations
 */

import { Edit2, Plus, RefreshCw, Save, Settings, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useI18n } from '../../../i18n/I18nContext';
import { authFetch } from '../../../services/authService';

import { useIsAdmin } from '../../../hooks/useAuth';

interface SystemConfig {
  key: string;
  value: string;
  description: string | null;
  updated_at: string;
}

interface CircuitBreakerStatus {
  text_breaker: {
    state: string;
    failure_count: number;
    time_since_opened_seconds: number;
    recovery_timeout: number;
    failure_threshold: number;
  };
  ocr_breaker: {
    state: string;
    failure_count: number;
    time_since_opened_seconds: number;
    recovery_timeout: number;
    failure_threshold: number;
  };
  embed_breaker: {
    state: string;
    failure_count: number;
    time_since_opened_seconds: number;
    recovery_timeout: number;
    failure_threshold: number;
  };
  overall_available: boolean;
  overall_state: string;
}

export function SystemConfigPanel() {
  const { t } = useI18n();
  const isAdmin = useIsAdmin();
  const [configs, setConfigs] = useState<SystemConfig[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Circuit Breaker states
  const [cbStatus, setCbStatus] = useState<CircuitBreakerStatus | null>(null);
  const [cbLoading, setCbLoading] = useState(false);

  // Editing states
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [editDescription, setEditDescription] = useState('');

  // Create states
  const [isCreating, setIsCreating] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
    return () => clearTimeout(timer);
  }, []);

  const loadConfigs = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await authFetch('/api/system-configs/');
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setConfigs(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load configurations');
    } finally {
      setIsLoading(false);
    }
  };

  const loadCircuitBreakerStatus = async () => {
    try {
      setCbLoading(true);
      const response = await authFetch('/api/system-configs/circuit-breaker/status');
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setCbStatus(data);
    } catch (err: any) {
      console.error('Failed to load circuit breaker status:', err);
    } finally {
      setCbLoading(false);
    }
  };

  const resetCircuitBreaker = async (name?: string) => {
    try {
      setCbLoading(true);
      const url = name 
        ? `/api/system-configs/circuit-breaker/reset?name=${name}` 
        : '/api/system-configs/circuit-breaker/reset';
        
      const response = await authFetch(url, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setCbStatus(data);
    } catch (err: any) {
      console.error('Failed to reset circuit breaker:', err);
    } finally {
      setCbLoading(false);
    }
  };

  const forceOpenCircuitBreaker = async (name?: string) => {
    try {
      setCbLoading(true);
      const url = name 
        ? `/api/system-configs/circuit-breaker/open?name=${name}` 
        : '/api/system-configs/circuit-breaker/open';
        
      const response = await authFetch(url, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setCbStatus(data);
    } catch (err: any) {
      console.error('Failed to open circuit breaker:', err);
    } finally {
      setCbLoading(false);
    }
  };

  useEffect(() => {
    loadConfigs();
    loadCircuitBreakerStatus();
  }, []);

  const handleCreate = async () => {
    if (!newKey.trim() || !newValue.trim()) return;

    try {
      const response = await authFetch('/api/system-configs/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          key: newKey.trim(),
          value: newValue.trim(),
          description: newDescription.trim() || null,
        }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setIsCreating(false);
      setNewKey('');
      setNewValue('');
      setNewDescription('');
      await loadConfigs();
    } catch (err: any) {
      alert(err.message || 'Failed to create configuration');
    }
  };

  const handleUpdate = async (key: string) => {
    try {
      const response = await authFetch(`/api/system-configs/${key}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          value: editValue.trim(),
          description: editDescription.trim() || null,
        }),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      setEditingKey(null);
      await loadConfigs();
    } catch (err: any) {
      alert(err.message || 'Failed to update configuration');
    }
  };


  const startEdit = (config: SystemConfig) => {
    setEditingKey(config.key);
    setEditValue(config.value);
    setEditDescription(config.description || '');
  };

  const cancelEdit = () => {
    setEditingKey(null);
    setEditValue('');
    setEditDescription('');
  };

  const filteredConfigs = configs.filter(config => 
    config.key.toLowerCase().includes(searchQuery.toLowerCase()) || 
    (config.description?.toLowerCase().includes(searchQuery.toLowerCase())) ||
    config.value.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatDisplayValue = (key: string, value: string) => {
    if (key.endsWith('_at')) {
      const num = Number(value);
      // Recognize Unix timestamps (seconds) - sanity check for range (1970-2065ish)
      if (!isNaN(num) && num > 1000000000 && num < 3000000000 && /^\d+(\.\d+)?$/.test(value)) {
        try {
          return new Date(num * 1000).toISOString().replace(/-/g, '.').replace('Z', '+00:00');
        } catch (e) {
          return value;
        }
      }
    }
    return value;
  };

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in">


      {/* Error Message */}
      {error && (
        <div className="glass-panel dark:bg-red-950/20 p-4 bg-red-50 border-2 border-red-200 dark:border-red-900/30 rounded-xl">
          <p className="text-red-650 dark:text-red-400 font-normal">{error}</p>
        </div>
      )}

      {/* Circuit Breaker Control Panel */}
      {cbStatus && (
        <div className="glass-panel dark:bg-slate-900/60 p-4 md:p-6 rounded-[16px] md:rounded-[24px] shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 md:gap-0 mb-4 md:mb-6">
            <div className="flex items-center gap-2 md:gap-3">
              <div className="p-2 md:p-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
                <Settings size={18} className="md:w-5 md:h-5" />
              </div>
              <h3 className="text-lg md:text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('admin.systemConfig.circuitBreaker.title')}</h3>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-8 mb-4 md:mb-6">
            {/* Text Model Box */}
            <div className={`glass-panel p-6 md:p-8 rounded-[32px] border-2 transition-all hover:scale-[1.01] flex flex-col justify-between ${cbStatus.text_breaker.state === 'closed' ? 'bg-green-50/40 dark:bg-green-950/10 border-green-200 dark:border-green-900/30' : cbStatus.text_breaker.state === 'open' ? 'bg-red-50/40 dark:bg-red-950/10 border-red-200 dark:border-red-900/30' : 'bg-yellow-50/40 dark:bg-yellow-950/10 border-yellow-200 dark:border-yellow-900/30'}`}>
              <div>
                <div className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wider">{t('admin.systemConfig.circuitBreaker.textLlm')}</div>
                <div className={`text-xl md:text-2xl font-normal ${cbStatus.text_breaker.state === 'closed' ? 'text-green-600 dark:text-green-400' : cbStatus.text_breaker.state === 'open' ? 'text-red-600 dark:text-red-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                  {cbStatus.text_breaker.state === 'closed' ? `✓ ${t('admin.systemConfig.circuitBreaker.states.closed')}` : cbStatus.text_breaker.state === 'open' ? `✗ ${t('admin.systemConfig.circuitBreaker.states.open')}` : `⚠ ${t('admin.systemConfig.circuitBreaker.states.half_open')}`}
                </div>
                <div className="text-xs md:text-sm text-slate-400 dark:text-slate-500 mt-2">
                  {t('admin.systemConfig.circuitBreaker.failures')}: <span className="text-slate-700 dark:text-slate-300 font-normal">{cbStatus.text_breaker.failure_count}/{cbStatus.text_breaker.failure_threshold}</span>
                </div>
              </div>
              
              {isAdmin && (
                <div className="grid grid-cols-2 gap-3 mt-8">
                  <button 
                    onClick={() => resetCircuitBreaker('llm_generate')}
                    disabled={cbStatus.text_breaker.state === 'closed' || cbLoading}
                    className="flex items-center justify-center gap-2 py-3 bg-green-600 dark:bg-green-950/40 text-white dark:text-green-400 dark:border dark:border-green-900/30 rounded-xl hover:bg-green-700 dark:hover:bg-green-900/30 transition-all font-normal text-sm shadow-lg shadow-green-600/10 dark:shadow-none disabled:opacity-30"
                  >
                    <RefreshCw size={14} />
                    {t('admin.systemConfig.circuitBreaker.reset')}
                  </button>
                  <button 
                    onClick={() => forceOpenCircuitBreaker('llm_generate')}
                    disabled={cbStatus.text_breaker.state === 'open' || cbLoading}
                    className="flex items-center justify-center gap-2 py-3 bg-red-600 dark:bg-red-950/40 text-white dark:text-red-400 dark:border dark:border-red-900/30 rounded-xl hover:bg-red-700 dark:hover:bg-red-900/30 transition-all font-normal text-sm shadow-lg shadow-red-600/10 dark:shadow-none disabled:opacity-30"
                  >
                    <X size={14} />
                    {t('admin.systemConfig.circuitBreaker.forceOpen')} 
                  </button>
                </div>
              )}
            </div>

            {/* Vectorizer Box */}
            <div className={`glass-panel p-6 md:p-8 rounded-[32px] border-2 transition-all hover:scale-[1.01] flex flex-col justify-between ${cbStatus.embed_breaker.state === 'closed' ? 'bg-green-50/40 dark:bg-green-950/10 border-green-200 dark:border-green-900/30' : cbStatus.embed_breaker.state === 'open' ? 'bg-red-50/40 dark:bg-red-950/10 border-red-200 dark:border-red-900/30' : 'bg-yellow-50/40 dark:bg-yellow-950/10 border-yellow-200 dark:border-yellow-900/30'}`}>
              <div>
                <div className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wider">{t('admin.systemConfig.circuitBreaker.embeddings')}</div>
                <div className={`text-xl md:text-2xl font-normal ${cbStatus.embed_breaker.state === 'closed' ? 'text-green-600 dark:text-green-400' : cbStatus.embed_breaker.state === 'open' ? 'text-red-600 dark:text-red-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                  {cbStatus.embed_breaker.state === 'closed' ? `✓ ${t('admin.systemConfig.circuitBreaker.states.closed')}` : cbStatus.embed_breaker.state === 'open' ? `✗ ${t('admin.systemConfig.circuitBreaker.states.open')}` : `⚠ ${t('admin.systemConfig.circuitBreaker.states.half_open')}`}
                </div>
                <div className="text-xs md:text-sm text-slate-400 dark:text-slate-500 mt-2">
                  {t('admin.systemConfig.circuitBreaker.failures')}: <span className="text-slate-700 dark:text-slate-300 font-normal">{cbStatus.embed_breaker.failure_count}/{cbStatus.embed_breaker.failure_threshold}</span>
                </div>
              </div>

              {isAdmin && (
                <div className="grid grid-cols-2 gap-3 mt-8">
                  <button 
                    onClick={() => resetCircuitBreaker('llm_embed')}
                    disabled={cbStatus.embed_breaker.state === 'closed' || cbLoading}
                    className="flex items-center justify-center gap-2 py-3 bg-green-600 dark:bg-green-950/40 text-white dark:text-green-400 dark:border dark:border-green-900/30 rounded-xl hover:bg-green-700 dark:hover:bg-green-900/30 transition-all font-normal text-sm shadow-lg shadow-green-600/10 dark:shadow-none disabled:opacity-30"
                  >
                    <RefreshCw size={14} />
                    {t('admin.systemConfig.circuitBreaker.reset')}
                  </button>
                  <button 
                    onClick={() => forceOpenCircuitBreaker('llm_embed')}
                    disabled={cbStatus.embed_breaker.state === 'open' || cbLoading}
                    className="flex items-center justify-center gap-2 py-3 bg-red-600 dark:bg-red-950/40 text-white dark:text-red-400 dark:border dark:border-red-900/30 rounded-xl hover:bg-red-700 dark:hover:bg-red-900/30 transition-all font-normal text-sm shadow-lg shadow-red-600/10 dark:shadow-none disabled:opacity-30"
                  >
                    <X size={14} />
                    {t('admin.systemConfig.circuitBreaker.forceOpen')} 
                  </button>
                </div>
              )}
            </div>

            {/* OCR Model Box */}
            <div className={`glass-panel p-6 md:p-8 rounded-[32px] border-2 transition-all hover:scale-[1.01] flex flex-col justify-between ${cbStatus.ocr_breaker.state === 'closed' ? 'bg-green-50/40 dark:bg-green-950/10 border-green-200 dark:border-green-900/30' : cbStatus.ocr_breaker.state === 'open' ? 'bg-red-50/40 dark:bg-red-950/10 border-red-200 dark:border-red-900/30' : 'bg-yellow-50/40 dark:bg-yellow-950/10 border-yellow-200 dark:border-yellow-900/30'}`}>
              <div>
                <div className="text-xs md:text-sm text-slate-500 dark:text-slate-400 mb-2 uppercase tracking-wider">{t('admin.systemConfig.circuitBreaker.ocrLlm')}</div>
                <div className={`text-xl md:text-2xl font-normal ${cbStatus.ocr_breaker.state === 'closed' ? 'text-green-600 dark:text-green-400' : cbStatus.ocr_breaker.state === 'open' ? 'text-red-600 dark:text-red-400' : 'text-yellow-600 dark:text-yellow-400'}`}>
                  {cbStatus.ocr_breaker.state === 'closed' ? `✓ ${t('admin.systemConfig.circuitBreaker.states.closed')}` : cbStatus.ocr_breaker.state === 'open' ? `✗ ${t('admin.systemConfig.circuitBreaker.states.open')}` : `⚠ ${t('admin.systemConfig.circuitBreaker.states.half_open')}`}
                </div>
                <div className="text-xs md:text-sm text-slate-400 dark:text-slate-500 mt-2">
                  {t('admin.systemConfig.circuitBreaker.failures')}: <span className="text-slate-700 dark:text-slate-300 font-normal">{cbStatus.ocr_breaker.failure_count}/{cbStatus.ocr_breaker.failure_threshold}</span>
                </div>
              </div>

              {isAdmin && (
                <div className="grid grid-cols-2 gap-3 mt-8">
                  <button 
                    onClick={() => resetCircuitBreaker('llm_ocr')}
                    disabled={cbStatus.ocr_breaker.state === 'closed' || cbLoading}
                    className="flex items-center justify-center gap-2 py-3 bg-green-600 dark:bg-green-950/20 dark:disabled:bg-green-950/10 text-white dark:text-green-400 dark:border dark:border-green-900/30 rounded-xl hover:bg-green-700 dark:hover:bg-green-900/30 transition-all font-normal text-sm shadow-lg shadow-green-600/10 dark:shadow-none disabled:opacity-30"
                  >
                    <RefreshCw size={14} />
                    {t('admin.systemConfig.circuitBreaker.reset')}
                  </button>
                  <button 
                    onClick={() => forceOpenCircuitBreaker('llm_ocr')}
                    disabled={cbStatus.ocr_breaker.state === 'open' || cbLoading}
                    className="flex items-center justify-center gap-2 py-3 bg-red-600 dark:bg-red-950/40 text-white dark:text-red-400 dark:border dark:border-red-900/30 rounded-xl hover:bg-red-700 dark:hover:bg-red-900/30 transition-all font-normal text-sm shadow-lg shadow-red-600/10 dark:shadow-none disabled:opacity-30"
                  >
                    <X size={14} />
                    {t('admin.systemConfig.circuitBreaker.forceOpen')} 
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-20 flex flex-col items-center justify-center text-center animate-pulse shadow-xl rounded-[24px]">
          <Settings className="w-16 h-16 text-[#75C5F0] dark:text-[#38bdf8] mb-6 animate-spin" />
          <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100">{t('common.loading')}</h3>
        </div>
      )}

      {/* Create Modal */}
      {isCreating && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 animate-in fade-in duration-300">
          <div
            className="absolute inset-0 bg-slate-900/40 backdrop-blur-sm"
            onClick={() => {
              setIsCreating(false);
              setNewKey('');
              setNewValue('');
              setNewDescription('');
            }}
          />
          <div className="relative w-full max-w-2xl bg-white/90 dark:bg-slate-900/90 backdrop-blur-xl rounded-[32px] border border-white/20 dark:border-slate-800 shadow-2xl shadow-slate-900/20 overflow-hidden animate-in zoom-in-95 duration-300">
            {/* Modal Header */}
            <div className="px-8 py-6 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-900/50">
              <h3 className="text-2xl font-bold text-slate-800 dark:text-slate-100 flex items-center gap-3">
                <Settings className="text-[#0369a1] dark:text-[#38bdf8] w-6 h-6" />
                {t('admin.systemConfig.createNew')}
              </h3>
              <button
                onClick={() => {
                  setIsCreating(false);
                  setNewKey('');
                  setNewValue('');
                  setNewDescription('');
                }}
                className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-100"
              >
                <X size={24} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-8 space-y-6">
              <div className="space-y-2">
                <label className="block text-sm font-normal text-[#94a3b8] px-1 uppercase tracking-wider">
                  {t('admin.systemConfig.key')} <span className="text-red-500 font-bold">*</span>
                </label>
                <input
                  type="text"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  placeholder="e.g., llm_cb_failure_threshold"
                  className="w-full px-5 py-4 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-slate-50/50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-550 outline-none focus:ring-4 focus:ring-[#0369a1]/10 dark:focus:ring-[#38bdf8]/10 focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all text-left font-mono"
                  dir="ltr"
                  data-latin="true"
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-normal text-[#94a3b8] px-1 uppercase tracking-wider">
                  {t('admin.systemConfig.value')} <span className="text-red-500 font-bold">*</span>
                </label>
                <input
                  type="text"
                  value={newValue}
                  onChange={(e) => setNewValue(e.target.value)}
                  placeholder="e.g., 5"
                  className="w-full px-5 py-4 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-slate-50/50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-550 outline-none focus:ring-4 focus:ring-[#0369a1]/10 dark:focus:ring-[#38bdf8]/10 focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all text-left"
                  dir="ltr"
                  data-latin="true"
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-normal text-[#94a3b8] px-1 uppercase tracking-wider">
                  {t('admin.systemConfig.description')}
                </label>
                <input
                  type="text"
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe the purpose of this configuration..."
                  className="w-full px-5 py-4 border-2 border-slate-100 dark:border-slate-800 rounded-2xl bg-slate-50/50 dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-550 outline-none focus:ring-4 focus:ring-[#0369a1]/10 dark:focus:ring-[#38bdf8]/10 focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all text-left"
                  dir="ltr"
                  data-latin="true"
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-8 py-6 bg-slate-50/80 dark:bg-slate-950/80 border-t border-slate-100 dark:border-slate-800 flex items-center justify-end gap-3">
              <button
                onClick={() => {
                  setIsCreating(false);
                  setNewKey('');
                  setNewValue('');
                  setNewDescription('');
                }}
                className="flex items-center gap-2 px-6 py-3 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 rounded-xl hover:bg-slate-50 dark:hover:bg-slate-800 transition-all font-normal shadow-sm"
              >
                <X size={18} />
                {t('common.cancel')}
              </button>
              <button
                onClick={handleCreate}
                disabled={!newKey.trim() || !newValue.trim()}
                className="flex items-center gap-2 px-8 py-3 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-normal shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10 transform active:scale-95"
              >
                <Save size={18} />
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Search and Action Bar - matching other tabs layout */}
      {!isLoading && (
        <div className="flex flex-col-reverse md:flex-row gap-3 md:gap-4 items-center">
          <div className="relative flex-1 lg:flex-none lg:w-[30%] group w-full">
            <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-[#0369a1] dark:text-[#38bdf8]">
              <RefreshCw size={18} className="hidden" /> {/* dummy for layout matching */}
              {/* Lucide Search Icon */}
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-search"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              ref={inputRef}
              placeholder={t('common.search')}
              className="w-full pr-12 pl-6 py-2.5 md:py-3 bg-white dark:bg-slate-900 border-2 border-[#0369a1]/10 dark:border-[#38bdf8]/10 rounded-2xl text-[#1a1a1a] dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none focus:border-[#0369a1] dark:focus:border-[#38bdf8] transition-all shadow-sm text-base"
              dir="ltr"
              data-latin="true"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute inset-y-0 left-4 flex items-center text-slate-400 hover:text-[#0369a1] dark:hover:text-[#38bdf8] transition-colors"
              >
                <X size={18} />
              </button>
            )}
          </div>
  
          <div className="flex items-center gap-2 md:gap-3 shrink-0 w-full justify-end md:w-auto md:justify-start md:mr-auto">
            <button
              onClick={loadConfigs}
              className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-white dark:bg-slate-800 border border-[#0369a1]/20 dark:border-[#38bdf8]/20 text-[#0369a1] dark:text-[#38bdf8] rounded-xl hover:bg-[#0369a1]/10 dark:hover:bg-[#38bdf8]/10 transition-all shadow-sm"
            >
              <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
              <span className="text-xs md:text-sm font-normal">{t('common.refresh')}</span>
            </button>
            <button
              onClick={() => setIsCreating(true)}
              className="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0284c7] dark:hover:bg-[#38bdf8]/90 transition-all shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10"
            >
              <Plus size={14} className="md:w-4 md:h-4" />
              <span className="text-xs md:text-sm font-normal">{t('admin.systemConfig.add')}</span>
            </button>
          </div>
        </div>
      )}

      {/* Configs Table */}
      {!isLoading && configs.length > 0 && (
        <div className="glass-panel dark:bg-slate-900/60 overflow-hidden rounded-[16px] md:rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10 dark:border-slate-800">
          <div className="overflow-x-auto custom-scrollbar" dir="ltr">
            <table className="w-full text-left lg:min-w-[700px]">
              <thead>
                <tr className="bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 border-b border-[#0369a1]/10 dark:border-slate-800 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] dark:text-[#38bdf8] uppercase">
                  <th className="px-3 md:px-6 py-3 md:py-5 font-normal w-1/4 text-left">{t('admin.systemConfig.key')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 font-normal w-1/4 text-left">{t('admin.systemConfig.value')}</th>
                  <th className="hidden lg:table-cell px-3 md:px-6 py-3 md:py-5 font-normal w-1/3 text-left">{t('admin.systemConfig.description')}</th>
                  <th className="px-3 md:px-6 py-3 md:py-5 font-normal w-1/6 text-right">{t('admin.systemConfig.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5 dark:divide-slate-800/30">
                {filteredConfigs.map((config) => (
                  <tr key={config.key} className="border-b border-[#0369a1]/5 dark:border-slate-800/30 hover:bg-[#e8f4f8]/20 dark:hover:bg-[#38bdf8]/5 transition-colors">
                    <td className="px-3 md:px-6 py-4 md:py-6">
                      <code className="text-[11px] md:text-sm font-mono bg-[#0369a1]/5 dark:bg-[#38bdf8]/5 px-2 md:px-3 py-0.5 md:py-1 rounded-lg text-[#0369a1] dark:text-[#38bdf8] break-all">
                        {config.key}
                      </code>
                    </td>
                    <td className="px-3 md:px-6 py-4 md:py-6">
                      {editingKey === config.key ? (
                        <input
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          className="w-full px-2 md:px-3 py-1.5 md:py-2 border-2 border-[#0369a1] dark:border-[#38bdf8] rounded-xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none text-left text-base"
                          dir="ltr"
                          data-latin="true"
                        />
                      ) : (
                        <span className="font-normal text-[#1a1a1a] dark:text-slate-100 text-sm md:text-base break-all">
                          {formatDisplayValue(config.key, config.value)}
                        </span>
                      )}
                    </td>
                    <td className="hidden lg:table-cell px-3 md:px-6 py-4 md:py-6">
                      {editingKey === config.key ? (
                        <input
                          type="text"
                          value={editDescription}
                          onChange={(e) => setEditDescription(e.target.value)}
                          className="w-full px-2 md:px-3 py-1.5 md:py-2 border-2 border-[#0369a1] dark:border-[#38bdf8] rounded-xl bg-white dark:bg-slate-950 text-slate-800 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 outline-none text-left text-base"
                          dir="ltr"
                          data-latin="true"
                        />
                      ) : (
                        <span className="text-xs md:text-sm text-[#94a3b8] dark:text-slate-400">
                          {config.description || <em className="opacity-50">No description</em>}
                        </span>
                      )}
                    </td>
                    <td className="px-3 md:px-6 py-4 md:py-6">
                      <div className="flex items-center justify-end gap-1 md:gap-2">
                        {editingKey === config.key ? (
                          <>
                            <button
                              onClick={() => handleUpdate(config.key)}
                              className="p-1.5 md:p-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/10"
                              title={t('common.save')}
                            >
                              <Save size={16} className="md:w-[18px] md:h-[18px]" />
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="p-1.5 md:p-2.5 bg-slate-100 dark:bg-slate-800 text-slate-650 dark:text-slate-400 rounded-xl hover:bg-slate-200 dark:hover:bg-slate-700 transition-all"
                              title={t('common.cancel')}
                            >
                              <X size={16} className="md:w-[18px] md:h-[18px]" />
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => startEdit(config)}
                            className="p-1.5 md:p-2.5 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-xl hover:bg-[#0369a1] dark:hover:bg-[#38bdf8] hover:text-white dark:hover:text-slate-950 transition-all border border-[#0369a1]/5 dark:border-[#38bdf8]/10 hover:shadow-lg hover:shadow-[#0369a1]/20"
                            title={t('common.edit')}
                          >
                            <Edit2 size={16} className="md:w-[18px] md:h-[18px]" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !isCreating && configs.length === 0 && (
        <div className="glass-panel dark:bg-slate-900/60 border border-[#0369a1]/10 dark:border-slate-800 p-20 flex flex-col items-center justify-center text-center shadow-xl rounded-[24px]">
          <Settings className="w-16 h-16 text-[#75C5F0] dark:text-[#38bdf8] mb-6 opacity-30" />
          <h3 className="text-xl font-normal text-[#1a1a1a] dark:text-slate-100 mb-2">{t('admin.systemConfig.empty')}</h3>
          <p className="text-slate-500 dark:text-slate-400 font-normal mb-6">{t('admin.systemConfig.emptyDescription')}</p>
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 rounded-xl hover:bg-[#0369a1]/90 dark:hover:bg-[#38bdf8]/90 transition-all shadow-lg shadow-[#0369a1]/20 dark:shadow-[#38bdf8]/10"
          >
            <Plus size={16} />
            {t('admin.systemConfig.add')}
          </button>
        </div>
      )}
    </div>
  );
}

export default SystemConfigPanel;
