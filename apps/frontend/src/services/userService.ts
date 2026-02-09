/**
 * User management service for admin functionality.
 */

import { authFetch } from './authService';

const API_BASE = '/api/users';

export interface UserPublic {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  role: 'admin' | 'editor' | 'reader';
  is_active: boolean;
  created_at?: string;
}

export interface PaginatedUsers {
  users: UserPublic[];
  total: number;
  page: number;
  page_size: number;
}

export const UserService = {
  /**
   * List all users with pagination.
   */
  async listUsers(
    page: number = 1,
    pageSize: number = 20,
    roleFilter?: string
  ): Promise<PaginatedUsers> {
    let url = `${API_BASE}/?page=${page}&page_size=${pageSize}`;
    if (roleFilter && roleFilter !== 'all') {
      url += `&role=${roleFilter}`;
    }

    const response = await authFetch(url);
    if (!response.ok) {
      if (response.status === 403) {
        throw new Error('Permission denied: Admin access required');
      }
      throw new Error('Failed to fetch users');
    }

    return await response.json();
  },

  /**
   * Get a specific user by ID.
   */
  async getUser(userId: string): Promise<UserPublic> {
    const response = await authFetch(`${API_BASE}/${userId}`);
    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('User not found');
      }
      throw new Error('Failed to fetch user');
    }

    return await response.json();
  },

  /**
   * Change a user's role.
   */
  async changeUserRole(
    userId: string,
    newRole: 'admin' | 'editor' | 'reader'
  ): Promise<UserPublic> {
    const response = await authFetch(`${API_BASE}/${userId}/role`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: newRole }),
    });

    if (!response.ok) {
      if (response.status === 400) {
        const data = await response.json();
        throw new Error(data.detail || 'Cannot change role');
      }
      if (response.status === 403) {
        throw new Error('Permission denied');
      }
      throw new Error('Failed to change role');
    }

    return await response.json();
  },

  /**
   * Enable or disable a user account.
   */
  async changeUserStatus(
    userId: string,
    isActive: boolean
  ): Promise<UserPublic> {
    const response = await authFetch(`${API_BASE}/${userId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: isActive }),
    });

    if (!response.ok) {
      if (response.status === 400) {
        const data = await response.json();
        throw new Error(data.detail || 'Cannot change status');
      }
      if (response.status === 403) {
        throw new Error('Permission denied');
      }
      throw new Error('Failed to change status');
    }

    return await response.json();
  },
};

export default UserService;
