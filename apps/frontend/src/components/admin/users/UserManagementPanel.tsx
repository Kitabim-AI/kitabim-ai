/**
 * User Management Panel for Admins
 */

import React, { useState, useEffect, useCallback } from 'react';
import { UserService, UserPublic, PaginatedUsers } from '../../../services/userService';
import { useIsAdmin } from '../../../hooks/useAuth';

interface UserRowProps {
  user: UserPublic;
  onRoleChange: (userId: string, newRole: 'admin' | 'editor' | 'reader') => Promise<void>;
  onStatusChange: (userId: string, isActive: boolean) => Promise<void>;
  isUpdating: boolean;
}

function UserRow({ user, onRoleChange, onStatusChange, isUpdating }: UserRowProps) {
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);

  const roleColors: Record<string, { bg: string; text: string }> = {
    admin: { bg: 'rgba(239, 68, 68, 0.15)', text: '#ef4444' },
    editor: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3b82f6' },
    reader: { bg: 'rgba(16, 185, 129, 0.15)', text: '#10b981' },
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  return (
    <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
      {/* Avatar and Name */}
      <td style={{ padding: '12px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        {user.avatar_url ? (
          <img
            src={user.avatar_url}
            alt={user.display_name}
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              objectFit: 'cover',
            }}
          />
        ) : (
          <div
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              backgroundColor: '#6366f1',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
              fontWeight: 'bold',
              color: 'white',
            }}
          >
            {user.display_name?.charAt(0).toUpperCase() || '?'}
          </div>
        )}
        <div>
          <div style={{ fontWeight: 500, color: '#f8fafc' }}>{user.display_name}</div>
          <div style={{ fontSize: '12px', color: 'rgba(255, 255, 255, 0.5)' }}>{user.email}</div>
        </div>
      </td>

      {/* Role */}
      <td style={{ padding: '12px', position: 'relative' }}>
        <button
          onClick={() => setShowRoleDropdown(!showRoleDropdown)}
          disabled={isUpdating}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 12px',
            backgroundColor: roleColors[user.role]?.bg || 'rgba(107, 114, 128, 0.15)',
            color: roleColors[user.role]?.text || '#6b7280',
            border: 'none',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 'bold',
            textTransform: 'uppercase',
            cursor: 'pointer',
            opacity: isUpdating ? 0.5 : 1,
          }}
        >
          {user.role}
          <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
            <path d="M6 8L2 4h8L6 8z" />
          </svg>
        </button>

        {showRoleDropdown && (
          <div
            style={{
              position: 'absolute',
              top: '100%',
              left: '12px',
              zIndex: 100,
              backgroundColor: '#1f2937',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '8px',
              minWidth: '120px',
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.3)',
              overflow: 'hidden',
            }}
          >
            {(['admin', 'editor', 'reader'] as const).map((role) => (
              <button
                key={role}
                onClick={() => {
                  setShowRoleDropdown(false);
                  if (role !== user.role) {
                    onRoleChange(user.id, role);
                  }
                }}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  backgroundColor: role === user.role ? 'rgba(99, 102, 241, 0.2)' : 'transparent',
                  border: 'none',
                  color: roleColors[role].text,
                  textAlign: 'left',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: 'bold',
                  textTransform: 'uppercase',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor =
                    role === user.role ? 'rgba(99, 102, 241, 0.2)' : 'transparent';
                }}
              >
                {role}
              </button>
            ))}
          </div>
        )}
      </td>

      {/* Status */}
      <td style={{ padding: '12px' }}>
        <button
          onClick={() => onStatusChange(user.id, !user.is_active)}
          disabled={isUpdating}
          style={{
            padding: '4px 12px',
            backgroundColor: user.is_active
              ? 'rgba(16, 185, 129, 0.15)'
              : 'rgba(239, 68, 68, 0.15)',
            color: user.is_active ? '#10b981' : '#ef4444',
            border: 'none',
            borderRadius: '6px',
            fontSize: '12px',
            fontWeight: 'bold',
            cursor: 'pointer',
            opacity: isUpdating ? 0.5 : 1,
          }}
        >
          {user.is_active ? 'Active' : 'Disabled'}
        </button>
      </td>

      {/* Joined */}
      <td style={{ padding: '12px', color: 'rgba(255, 255, 255, 0.5)', fontSize: '13px' }}>
        {formatDate(user.created_at)}
      </td>
    </tr>
  );
}

export function UserManagementPanel() {
  const isAdmin = useIsAdmin();
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadUsers = useCallback(async () => {
    if (!isAdmin) return;

    setIsLoading(true);
    setError(null);
    try {
      const data = await UserService.listUsers(page, pageSize, roleFilter);
      setUsers(data.users);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    } finally {
      setIsLoading(false);
    }
  }, [isAdmin, page, pageSize, roleFilter]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleRoleChange = async (userId: string, newRole: 'admin' | 'editor' | 'reader') => {
    setIsUpdating(userId);
    try {
      const updatedUser = await UserService.changeUserRole(userId, newRole);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, role: updatedUser.role } : u))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change role');
    } finally {
      setIsUpdating(null);
    }
  };

  const handleStatusChange = async (userId: string, isActive: boolean) => {
    setIsUpdating(userId);
    try {
      const updatedUser = await UserService.changeUserStatus(userId, isActive);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, is_active: updatedUser.is_active } : u))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change status');
    } finally {
      setIsUpdating(null);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  if (!isAdmin) {
    return (
      <div
        style={{
          padding: '40px',
          textAlign: 'center',
          color: 'rgba(255, 255, 255, 0.5)',
        }}
      >
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{ margin: '0 auto 16px' }}
        >
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
          <path d="M7 11V7a5 5 0 0110 0v4" />
        </svg>
        <h3 style={{ margin: '0 0 8px', color: '#f8fafc' }}>Admin Access Required</h3>
        <p style={{ margin: 0, fontSize: '14px' }}>
          You need administrator privileges to manage users.
        </p>
      </div>
    );
  }

  return (
    <div
      style={{
        backgroundColor: '#111827',
        borderRadius: '12px',
        overflow: 'hidden',
        border: '1px solid rgba(255, 255, 255, 0.1)',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '20px 24px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div>
          <h2
            style={{
              margin: 0,
              fontSize: '18px',
              fontWeight: 'bold',
              color: '#f8fafc',
            }}
          >
            User Management
          </h2>
          <p
            style={{
              margin: '4px 0 0',
              fontSize: '13px',
              color: 'rgba(255, 255, 255, 0.5)',
            }}
          >
            {total} total users
          </p>
        </div>

        {/* Role Filter */}
        <select
          value={roleFilter}
          onChange={(e) => {
            setRoleFilter(e.target.value);
            setPage(1);
          }}
          style={{
            padding: '8px 12px',
            backgroundColor: 'rgba(255, 255, 255, 0.05)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '6px',
            color: '#f8fafc',
            fontSize: '13px',
            cursor: 'pointer',
          }}
        >
          <option value="all">All Roles</option>
          <option value="admin">Admins</option>
          <option value="editor">Editors</option>
          <option value="reader">Readers</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            padding: '12px 24px',
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            color: '#ef4444',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
          </svg>
          {error}
          <button
            onClick={() => setError(null)}
            style={{
              marginLeft: 'auto',
              padding: '4px',
              backgroundColor: 'transparent',
              border: 'none',
              color: 'inherit',
              cursor: 'pointer',
            }}
          >
            ✕
          </button>
        </div>
      )}

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: 'rgba(255, 255, 255, 0.02)' }}>
              <th
                style={{
                  padding: '12px',
                  textAlign: 'left',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: 'rgba(255, 255, 255, 0.4)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                User
              </th>
              <th
                style={{
                  padding: '12px',
                  textAlign: 'left',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: 'rgba(255, 255, 255, 0.4)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                Role
              </th>
              <th
                style={{
                  padding: '12px',
                  textAlign: 'left',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: 'rgba(255, 255, 255, 0.4)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                Status
              </th>
              <th
                style={{
                  padding: '12px',
                  textAlign: 'left',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  color: 'rgba(255, 255, 255, 0.4)',
                  textTransform: 'uppercase',
                  letterSpacing: '0.5px',
                }}
              >
                Joined
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={4} style={{ padding: '40px', textAlign: 'center' }}>
                  <div
                    style={{
                      display: 'inline-block',
                      width: '24px',
                      height: '24px',
                      border: '3px solid rgba(99, 102, 241, 0.2)',
                      borderTop: '3px solid #6366f1',
                      borderRadius: '50%',
                      animation: 'spin 1s linear infinite',
                    }}
                  />
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  style={{
                    padding: '40px',
                    textAlign: 'center',
                    color: 'rgba(255, 255, 255, 0.4)',
                  }}
                >
                  No users found
                </td>
              </tr>
            ) : (
              users.map((user) => (
                <UserRow
                  key={user.id}
                  user={user}
                  onRoleChange={handleRoleChange}
                  onStatusChange={handleStatusChange}
                  isUpdating={isUpdating === user.id}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div
          style={{
            padding: '16px 24px',
            borderTop: '1px solid rgba(255, 255, 255, 0.1)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ fontSize: '13px', color: 'rgba(255, 255, 255, 0.5)' }}>
            Showing {(page - 1) * pageSize + 1} to {Math.min(page * pageSize, total)} of {total}
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 1}
              style={{
                padding: '6px 12px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: page === 1 ? 'rgba(255, 255, 255, 0.3)' : '#f8fafc',
                cursor: page === 1 ? 'not-allowed' : 'pointer',
                fontSize: '13px',
              }}
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page === totalPages}
              style={{
                padding: '6px 12px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '6px',
                color: page === totalPages ? 'rgba(255, 255, 255, 0.3)' : '#f8fafc',
                cursor: page === totalPages ? 'not-allowed' : 'pointer',
                fontSize: '13px',
              }}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default UserManagementPanel;
