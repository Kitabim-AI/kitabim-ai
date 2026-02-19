/**
 * System Config Panel - CRUD interface for system configurations
 */

import React, { useState, useEffect } from 'react';
import { Settings, Plus, Save, X, Trash2, Edit2, RefreshCw } from 'lucide-react';
import { authFetch } from '../../../services/authService';
import { useI18n } from '../../../i18n/I18nContext';

interface SystemConfig {
  key: string;
  value: string;
  description: string | null;
  updated_at: string;
}

export function SystemConfigPanel() {
  const { t } = useI18n();
  const [configs, setConfigs] = useState<SystemConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

  useEffect(() => {
    loadConfigs();
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

  const handleDelete = async (key: string) => {
    if (!confirm(`Are you sure you want to delete the configuration "${key}"?`)) return;

    try {
      const response = await authFetch(`/api/system-configs/${key}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      await loadConfigs();
    } catch (err: any) {
      alert(err.message || 'Failed to delete configuration');
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
            className="flex items-center gap-2 px-4 py-2.5 bg-[#0369a1]/10 text-[#0369a1] rounded-xl border border-[#0369a1]/10 hover:bg-[#0369a1] hover:text-white transition-all"
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

      {/* Loading State */}
      {isLoading && (
        <div className="glass-panel p-20 flex flex-col items-center justify-center text-center animate-pulse">
          <Settings className="w-16 h-16 text-[#75C5F0] mb-6 animate-spin" />
          <h3 className="text-xl font-normal text-[#1a1a1a]">{t('common.loading')}</h3>
        </div>
      )}

      {/* Create Form */}
      {isCreating && (
        <div className="glass-panel p-6 rounded-[24px] border border-[#0369a1]/10 shadow-xl">
          <h3 className="text-lg font-normal text-[#1a1a1a] mb-4">{t('admin.systemConfig.createNew')}</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-normal text-[#94a3b8] mb-2">
                {t('admin.systemConfig.key')} <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder="e.g., llm_cb_failure_threshold"
                className="w-full px-4 py-3 border-2 border-[#0369a1]/20 rounded-xl bg-white outline-none focus:ring-4 focus:ring-[#0369a1]/10 focus:border-[#0369a1]"
              />
            </div>
            <div>
              <label className="block text-sm font-normal text-[#94a3b8] mb-2">
                {t('admin.systemConfig.value')} <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder="e.g., 5"
                className="w-full px-4 py-3 border-2 border-[#0369a1]/20 rounded-xl bg-white outline-none focus:ring-4 focus:ring-[#0369a1]/10 focus:border-[#0369a1]"
              />
            </div>
            <div>
              <label className="block text-sm font-normal text-[#94a3b8] mb-2">
                {t('admin.systemConfig.description')}
              </label>
              <textarea
                value={newDescription}
                onChange={(e) => setNewDescription(e.target.value)}
                placeholder="Description..."
                rows={2}
                className="w-full px-4 py-3 border-2 border-[#0369a1]/20 rounded-xl bg-white outline-none focus:ring-4 focus:ring-[#0369a1]/10 focus:border-[#0369a1] resize-none"
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleCreate}
                disabled={!newKey.trim() || !newValue.trim()}
                className="flex items-center gap-2 px-6 py-3 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
              >
                <Save size={16} />
                {t('common.save')}
              </button>
              <button
                onClick={() => {
                  setIsCreating(false);
                  setNewKey('');
                  setNewValue('');
                  setNewDescription('');
                }}
                className="flex items-center gap-2 px-6 py-3 bg-slate-100 text-slate-600 rounded-xl hover:bg-slate-200 transition-all"
              >
                <X size={16} />
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Configs Table */}
      {!isLoading && configs.length > 0 && (
        <div className="glass-panel overflow-hidden rounded-[24px] p-0 shadow-xl border border-[#0369a1]/10">
          <div className="overflow-x-auto custom-scrollbar">
            <table className="w-full text-left min-w-[800px]">
              <thead>
                <tr className="bg-[#0369a1]/5 border-b border-[#0369a1]/10 text-[14px] md:text-[16px] font-normal text-[#0369a1] uppercase">
                  <th className="px-6 py-5 font-normal w-1/4">{t('admin.systemConfig.key')}</th>
                  <th className="px-6 py-5 font-normal w-1/4">{t('admin.systemConfig.value')}</th>
                  <th className="px-6 py-5 font-normal w-1/3">{t('admin.systemConfig.description')}</th>
                  <th className="px-6 py-5 font-normal w-1/6">{t('admin.systemConfig.actions')}</th>
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
                          className="w-full px-3 py-2 border-2 border-[#0369a1] rounded-xl bg-white outline-none"
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
                          className="w-full px-3 py-2 border-2 border-[#0369a1] rounded-xl bg-white outline-none resize-none"
                        />
                      ) : (
                        <span className="text-sm text-[#94a3b8]">
                          {config.description || <em className="opacity-50">No description</em>}
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-6">
                      {editingKey === config.key ? (
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleUpdate(config.key)}
                            className="p-2 bg-[#0369a1] text-white rounded-lg hover:bg-[#0369a1]/90 transition-all"
                            title={t('common.save')}
                          >
                            <Save size={16} />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="p-2 bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 transition-all"
                            title={t('common.cancel')}
                          >
                            <X size={16} />
                          </button>
                        </div>
                      ) : (
                        <div className="flex gap-2">
                          <button
                            onClick={() => startEdit(config)}
                            className="p-2 bg-[#0369a1]/10 text-[#0369a1] rounded-lg hover:bg-[#0369a1] hover:text-white transition-all"
                            title={t('common.edit')}
                          >
                            <Edit2 size={16} />
                          </button>
                          <button
                            onClick={() => handleDelete(config.key)}
                            className="p-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-600 hover:text-white transition-all"
                            title={t('common.delete')}
                          >
                            <Trash2 size={16} />
                          </button>
                        </div>
                      )}
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
