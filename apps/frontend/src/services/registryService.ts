import { OcrSuspect, OcrRegistryStats } from '@shared/types';

const API_BASE = (import.meta as any).env?.VITE_API_TARGET || '';

export const RegistryService = {
  async getStats(): Promise<OcrRegistryStats> {
    const res = await fetch(`${API_BASE}/api/registry/stats`);
    if (!res.ok) throw new Error('Failed to fetch registry stats');
    return res.json();
  },

  async rebuildRegistry(): Promise<any> {
    const res = await fetch(`${API_BASE}/api/registry/rebuild`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to start registry rebuild');
    return res.json();
  },

  async generateCandidates(limit: number = 50): Promise<OcrSuspect[]> {
    const res = await fetch(`${API_BASE}/api/registry/generate-candidates?limit=${limit}`, { method: 'POST' });
    if (!res.ok) throw new Error('Failed to generate candidates');
    return res.json();
  },

  async getCandidates(limit: number = 50, minConfidence: number = 0.7): Promise<OcrSuspect[]> {
    const res = await fetch(`${API_BASE}/api/registry/candidates?limit=${limit}&min_confidence=${minConfidence}`);
    if (!res.ok) throw new Error('Failed to fetch candidates');
    return res.json();
  },

  async getTokens(status: string, limit: number = 100): Promise<OcrSuspect[]> {
    const res = await fetch(`${API_BASE}/api/registry/tokens?status=${status}&limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch tokens');
    return res.json();
  },

  async getTokenContext(token: string, limit: number = 5): Promise<any[]> {
    const res = await fetch(`${API_BASE}/api/registry/context?token=${encodeURIComponent(token)}&limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch token context');
    return res.json();
  },

  async verifyToken(token: string): Promise<any> {
    const res = await fetch(`${API_BASE}/api/registry/verify?token=${encodeURIComponent(token)}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to verify token');
    return res.json();
  },

  async applyGlobalCorrection(token: string, correction: string): Promise<any> {
    const res = await fetch(`${API_BASE}/api/registry/correct?token=${encodeURIComponent(token)}&correction=${encodeURIComponent(correction)}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to apply global correction');
    return res.json();
  }
};
