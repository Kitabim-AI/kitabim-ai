/**
 * System Config Panel - CRUD interface for system configurations
 */

import React, { useState, useEffect } from 'react';
import { Settings, Plus, Save, X, Edit2, RefreshCw } from 'lucide-react';
import { authFetch } from '../../../services/authService';
import { useI18n } from '../../../i18n/I18nContext';

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
  embed_breaker: {
    state: string;
    failure_count: number;
    time_since_opened_seconds: number;
    recovery_timeout: number;
    failure_threshold: number;
  };
  overall_available: boolean;
}

export function SystemConfigPanel() {
  const { t } = useI18n();
  const [configs, setConfigs] = useState<SystemConfig[]>([]);
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

  const resetCircuitBreaker = async () => {
    try {
      setCbLoading(true);
      const response = await authFetch('/api/system-configs/circuit-breaker/reset', {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setCbStatus(data);
    } catch (err: any) {
      alert(err.message || 'Failed to reset circuit breaker');
    } finally {
      setCbLoading(false);
    }
  };

  const forceOpenCircuitBreaker = async () => {
    if (!confirm('Are you sure you want to manually open the circuit breaker? This will stop all LLM processing.')) {
      return;
    }
    try {
      setCbLoading(true);
      const response = await authFetch('/api/system-configs/circuit-breaker/open', {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`Error ${response.status}: ${await response.text()}`);
      }
      const data = await response.json();
      setCbStatus(data);
    } catch (err: any) {
      alert(err.message || 'Failed to open circuit breaker');
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

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-4 group">
          <div className="p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:rotate-6">
            <Settings size={24} />
          </div>
          <div>
            <h2 className="text-2xl md:text-3xl font-normal text-[#1a1a1a]">
              {t('admin.systemConfig.title')}
            </h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <p className="text-[12px] md:text-[14px] font-normal text-[#94a3b8] uppercase">
                {t('admin.systemConfig.subtitle')}
              </p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={loadConfigs}
            className="flex items-center gap-2 px-4 py-2.5 bg-white text-[#0369a1] rounded-xl border border-[#0369a1]/20 hover:border-[#0369a1] transition-all shadow-sm"
          >
            <RefreshCw size={16} />
            <span className="text-sm font-normal">{t('common.refresh')}</span>
          </button>
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-2 px-4 py-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/20"
          >
            <Plus size={16} />
            <span className="text-sm font-normal">{t('admin.systemConfig.add')}</span>
          </button>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="glass-panel p-4 bg-red-50 border-2 border-red-200 rounded-xl">
          <p className="text-red-600 font-normal">{error}</p>
        </div>
      )}

      {/* Circuit Breaker Control Panel */}
      {cbStatus && (
        <div className="glass-panel p-6 rounded-[24px] shadow-xl border border-[#0369a1]/10">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
                <Settings size={20} />
              </div>
              <h3 className="text-xl font-normal text-[#1a1a1a]">Circuit Breaker Status</h3>
            </div>
            <button
              onClick={loadCircuitBreakerStatus}
              disabled={cbLoading}
              className="flex items-center gap-2 px-4 py-2 bg-white text-[#0369a1] rounded-xl border border-[#0369a1]/20 hover:border-[#0369a1] transition-all shadow-sm disabled:opacity-50"
            >
              <RefreshCw size={16} className={cbLoading ? 'animate-spin' : ''} />
              <span className="text-sm">Refresh</span>
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {/* Overall Status */}
            <div className={`p-4 rounded-2xl border-2 ${cbStatus.overall_available ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
              <div className="text-sm text-slate-600 mb-1 uppercase tracking-wider">Overall Status</div>
              <div className={`text-2xl font-normal ${cbStatus.overall_available ? 'text-green-600' : 'text-red-600'}`}>
                {cbStatus.overall_available ? '✓ Available' : '✗ Unavailable'}
              </div>
            </div>

            {/* Text Breaker */}
            <div className={`p-4 rounded-2xl border-2 ${cbStatus.text_breaker.state === 'closed' ? 'bg-green-50 border-green-200' : cbStatus.text_breaker.state === 'open' ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'}`}>
              <div className="text-sm text-slate-600 mb-1 uppercase tracking-wider">Text LLM</div>
              <div className="text-xl font-normal text-slate-800 capitalize">{cbStatus.text_breaker.state}</div>
              <div className="text-xs text-slate-500 mt-2">
                Failures: {cbStatus.text_breaker.failure_count}/{cbStatus.text_breaker.failure_threshold}
                {cbStatus.text_breaker.state === 'open' && (
                  <> • Opens for {cbStatus.text_breaker.recovery_timeout}s</>
                )}
              </div>
            </div>

            {/* Embed Breaker */}
            <div className={`p-4 rounded-2xl border-2 ${cbStatus.embed_breaker.state === 'closed' ? 'bg-green-50 border-green-200' : cbStatus.embed_breaker.state === 'open' ? 'bg-red-50 border-red-200' : 'bg-yellow-50 border-yellow-200'}`}>
              <div className="text-sm text-slate-600 mb-1 uppercase tracking-wider">Embeddings</div>
              <div className="text-xl font-normal text-slate-800 capitalize">{cbStatus.embed_breaker.state}</div>
              <div className="text-xs text-slate-500 mt-2">
                Failures: {cbStatus.embed_breaker.failure_count}/{cbStatus.embed_breaker.failure_threshold}
                {cbStatus.embed_breaker.state === 'open' && (
                  <> • Opened for {cbStatus.embed_breaker.time_since_opened_seconds}s</>
                )}
              </div>
            </div>
          </div>

          {/* Control Buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={resetCircuitBreaker}
              disabled={cbLoading || cbStatus.overall_available}
              className="flex items-center gap-2 px-4 py-2.5 bg-green-600 text-white rounded-xl hover:bg-green-700 transition-all shadow-lg shadow-green-600/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-green-600"
            >
              <RefreshCw size={16} />
              <span className="text-sm font-normal">Reset (Close) Circuit Breaker</span>
            </button>
            <button
              onClick={forceOpenCircuitBreaker}
              disabled={cbLoading || !cbStatus.overall_available}
              className="flex items-center gap-2 px-4 py-2.5 bg-red-600 text-white rounded-xl hover:bg-red-700 transition-all shadow-lg shadow-red-600/20 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-red-600"
            >
              <X size={16} />
              <span className="text-sm font-normal">Force Open (Stop Processing)</span>
            </button>
          </div>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center animate-pulse">
          <Settings className="w-16 h-16 text-[#75C5F0] mb-6 animate-spin" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
        </div>
      )}

      {/* Create Modal */}
      {isCreating && (
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
          <div className="relative w-full max-w-2xl bg-white/90 backdrop-blur-xl rounded-[32px] border border-white/20 shadow-2xl shadow-slate-900/20 overflow-hidden animate-in zoom-in-95 duration-300">
            {/* Modal Header */}
            <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-[#0369a1]/5 to-transparent">
              <div className="flex items-center gap-3">
                <div className="p-2.5 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20">
                  <Plus size={20} />
                </div>
                <h3 className="text-xl font-normal text-[#1a1a1a]">
                  {t('admin.systemConfig.createNew')}
                </h3>
              </div>
              <button
                onClick={() => {
                  setIsCreating(false);
                  setNewKey('');
                  setNewValue('');
                  setNewDescription('');
                }}
                className="p-2 hover:bg-slate-100 rounded-xl transition-colors text-slate-400 hover:text-slate-600"
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
                  className="w-full px-5 py-4 border-2 border-slate-100 rounded-2xl bg-slate-50/50 outline-none focus:ring-4 focus:ring-[#0369a1]/10 focus:border-[#0369a1] transition-all text-left font-mono"
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
                  className="w-full px-5 py-4 border-2 border-slate-100 rounded-2xl bg-slate-50/50 outline-none focus:ring-4 focus:ring-[#0369a1]/10 focus:border-[#0369a1] transition-all text-left"
                />
              </div>

              <div className="space-y-2">
                <label className="block text-sm font-normal text-[#94a3b8] px-1 uppercase tracking-wider">
                  {t('admin.systemConfig.description')}
                </label>
                <textarea
                  value={newDescription}
                  onChange={(e) => setNewDescription(e.target.value)}
                  placeholder="Describe the purpose of this configuration..."
                  rows={3}
                  className="w-full px-5 py-4 border-2 border-slate-100 rounded-2xl bg-slate-50/50 outline-none focus:ring-4 focus:ring-[#0369a1]/10 focus:border-[#0369a1] transition-all resize-none text-left"
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="px-8 py-6 bg-slate-50/80 border-t border-slate-100 flex items-center justify-end gap-3">
              <button
                onClick={() => {
                  setIsCreating(false);
                  setNewKey('');
                  setNewValue('');
                  setNewDescription('');
                }}
                className="flex items-center gap-2 px-6 py-3 bg-white border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-all font-normal shadow-sm"
              >
                <X size={18} />
                {t('common.cancel')}
              </button>
              <button
                onClick={handleCreate}
                disabled={!newKey.trim() || !newValue.trim()}
                className="flex items-center gap-2 px-8 py-3 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all font-normal shadow-lg shadow-[#0369a1]/20 transform active:scale-95"
              >
                <Save size={18} />
                {t('common.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Configs Table */}
      {!isLoading && configs.length > 0 && (
        <div className="glass-panel overflow-hidden rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-start min-w-[800px]">
              <thead>
                <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-[14px] md:text-[16px] font-normal text-[#0369a1] uppercase">
                  <th className="px-6 py-5 font-normal w-1/4 text-start">{t('admin.systemConfig.key')}</th>
                  <th className="px-6 py-5 font-normal w-1/4 text-start">{t('admin.systemConfig.value')}</th>
                  <th className="px-6 py-5 font-normal w-1/3 text-start">{t('admin.systemConfig.description')}</th>
                  <th className="px-6 py-5 font-normal w-1/6 text-start">{t('admin.systemConfig.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#75C5F0]/5">
                {configs.map((config) => (
                  <tr key={config.key} className="hover:bg-[#e8f4f8]/20 transition-colors">
                    <td className="px-6 py-6">
                      <code className="text-sm font-mono bg-[#0369a1]/5 px-3 py-1 rounded-lg text-[#0369a1]">
                        {config.key}
                      </code>
                    </td>
                    <td className="px-6 py-6">
                      {editingKey === config.key ? (
                        <input
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          className="w-full px-3 py-2 border-2 border-[#0369a1] rounded-xl bg-white outline-none text-left"
                        />
                      ) : (
                        <span className="font-normal text-[#1a1a1a]">{config.value}</span>
                      )}
                    </td>
                    <td className="px-6 py-6">
                      {editingKey === config.key ? (
                        <textarea
                          value={editDescription}
                          onChange={(e) => setEditDescription(e.target.value)}
                          rows={2}
                          className="w-full px-3 py-2 border-2 border-[#0369a1] rounded-xl bg-white outline-none resize-none text-left"
                        />
                      ) : (
                        <span className="text-sm text-[#94a3b8]">
                          {config.description || <em className="opacity-50">No description</em>}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-6">
                      <div className="flex items-center justify-start gap-2">
                        {editingKey === config.key ? (
                          <>
                            <button
                              onClick={() => handleUpdate(config.key)}
                              className="p-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/10"
                              title={t('common.save')}
                            >
                              <Save size={18} />
                            </button>
                            <button
                              onClick={cancelEdit}
                              className="p-2.5 bg-slate-100 text-slate-600 rounded-xl hover:bg-slate-200 transition-all"
                              title={t('common.cancel')}
                            >
                              <X size={18} />
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => startEdit(config)}
                            className="p-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-xl hover:bg-[#0369a1] hover:text-white transition-all border border-[#0369a1]/5 hover:shadow-lg hover:shadow-[#0369a1]/20"
                            title={t('common.edit')}
                          >
                            <Edit2 size={18} />
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
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
          <Settings className="w-16 h-16 text-[#75C5F0] mb-6 opacity-30" />
          <h3 className="text-xl font-normal text-[#1a1a1a] mb-2">{t('admin.systemConfig.empty')}</h3>
          <p className="text-slate-500 font-normal mb-6">{t('admin.systemConfig.emptyDescription')}</p>
          <button
            onClick={() => setIsCreating(true)}
            className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/20"
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
