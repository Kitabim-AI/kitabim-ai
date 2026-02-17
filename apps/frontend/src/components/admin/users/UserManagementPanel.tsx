import React, { useState, useEffect, useCallback } from 'react';
import { UserService, UserPublic, PaginatedUsers } from '../../../services/userService';
import { Users } from 'lucide-react';
import { useIsAdmin } from '../../../hooks/useAuth';
import { useI18n } from '../../../i18n/I18nContext';
import { UserAvatar } from '../../common/UserAvatar';

interface UserRowProps {
  user: UserPublic;
  onRoleChange: (userId: string, newRole: 'admin' | 'editor' | 'reader') => Promise<void>;
  onStatusChange: (userId: string, isActive: boolean) => Promise<void>;
  isUpdating: boolean;
}

const UserRow: React.FC<UserRowProps> = ({ user, onRoleChange, onStatusChange, isUpdating }) => {
  const { t } = useI18n();
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);

  const roleColors: Record<string, { bg: string; text: string; label: string }> = {
    admin: { bg: 'bg-red-50', text: 'text-red-600', label: t('admin.users.admin') },
    editor: { bg: 'bg-blue-50', text: 'text-blue-600', label: t('admin.users.editor') },
    reader: { bg: 'bg-emerald-50', text: 'text-emerald-600', label: t('admin.users.reader') },
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return t('admin.users.unknown');
    return new Date(dateString).toLocaleDateString();
  };

  return (
    <tr className="border-b border-[#0369a1]/5 hover:bg-[#0369a1]/5 transition-colors">
      <td className="px-8 py-5">
        <div className="flex items-center gap-4">
          <UserAvatar
            url={user.avatar_url}
            name={user.display_name}
            className="w-10 h-10 rounded-full object-cover ring-2 ring-[#0369a1]/20"
          />
          <div>
            <div className="font-black text-[#1a1a1a] text-sm">{user.display_name}</div>
            <div className="text-[14px] font-bold text-[#94a3b8] uppercase tracking-wider">{user.email}</div>
          </div>
        </div>
      </td>

      <td className="px-8 py-5 relative">
        <button
          onClick={() => setShowRoleDropdown(!showRoleDropdown)}
          disabled={isUpdating}
          className={`inline-flex items-center gap-2 px-3 py-1.5 ${roleColors[user.role]?.bg || 'bg-slate-50'} ${roleColors[user.role]?.text || 'text-slate-500'} rounded-lg text-[14px] font-black uppercase tracking-wider transition-all active:scale-95 disabled:opacity-50 border border-current/10`}
        >
          {roleColors[user.role]?.label || user.role}
          <svg width="10" height="10" viewBox="0 0 12 12" fill="currentColor">
            <path d="M6 8L2 4h8L6 8z" />
          </svg>
        </button>

        {showRoleDropdown && (
          <div className="absolute top-full right-8 mt-2 w-48 glass-panel shadow-2xl z-50 overflow-hidden py-2" style={{ borderRadius: '16px' }}>
            {(['admin', 'editor', 'reader'] as const).map((role) => (
              <button
                key={role}
                onClick={() => {
                  setShowRoleDropdown(false);
                  if (role !== user.role) {
                    onRoleChange(user.id, role);
                  }
                }}
                className={`w-full flex items-center px-5 py-3 text-[14px] font-black uppercase tracking-wider transition-all ${role === user.role ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
              >
                {roleColors[role].label}
              </button>
            ))}
          </div>
        )}
      </td>

      <td className="px-8 py-5">
        <button
          onClick={() => onStatusChange(user.id, !user.is_active)}
          disabled={isUpdating}
          className={`px-3 py-1.5 rounded-lg text-[14px] font-black uppercase tracking-wider transition-all active:scale-95 disabled:opacity-50 border ${user.is_active
            ? 'bg-emerald-50 text-emerald-600 border-emerald-500/10'
            : 'bg-red-50 text-red-600 border-red-500/10'}`}
        >
          {user.is_active ? t('admin.users.active') : t('admin.users.suspended')}
        </button>
      </td>

      <td className="px-8 py-5 text-[14px] font-bold text-[#94a3b8]">
        {formatDate(user.created_at)}
      </td>
    </tr>
  );
}

export function UserManagementPanel() {
  const { t } = useI18n();
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
      setError(err instanceof Error ? err.message : t('admin.users.loadError'));
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
      setError(err instanceof Error ? err.message : t('admin.users.roleUpdateError'));
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
      setError(err instanceof Error ? err.message : t('admin.users.statusUpdateError'));
    } finally {
      setIsUpdating(null);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  if (!isAdmin) {
    return (
      <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
        <div className="p-4 bg-red-50 text-red-500 rounded-3xl mb-6">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
        </div>
        <h3 className="text-xl font-black text-[#1a1a1a] mb-2">{t('admin.users.accessRequired')}</h3>
        <p className="text-[#94a3b8] font-bold">{t('admin.users.accessRequiredDetail')}</p>
      </div>
    );
  }

  return (
    <div className="glass-panel overflow-hidden" style={{ borderRadius: '24px', padding: 0 }} dir="rtl">
      <div className="px-8 py-6 border-b border-[#0369a1]/10 flex items-center justify-between bg-[#0369a1]/5">
        <div className="flex items-center gap-4 group">
          <div className="p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
            <Users size={24} />
          </div>
          <div>
            <h2 className="text-3xl font-black text-[#1a1a1a] tracking-tight">{t('admin.users.title')}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <p className="text-[14px] font-black text-[#94a3b8] uppercase tracking-[0.2em]">
                {t('admin.users.total', { count: total })}
              </p>
            </div>
          </div>
        </div>

        {/* Role Filter */}
        <select
          value={roleFilter}
          onChange={(e) => {
            setRoleFilter(e.target.value);
            setPage(1);
          }}
          className="bg-white/50 backdrop-blur-md border border-[#0369a1]/20 rounded-xl px-4 py-2 text-sm font-black outline-none focus:ring-4 focus:ring-[#0369a1]/5 text-[#1a1a1a] cursor-pointer hover:bg-white transition-all shadow-sm"
        >
          <option value="all">{t('admin.users.allRoles')}</option>
          <option value="admin">{t('admin.users.admins')}</option>
          <option value="editor">{t('admin.users.editors')}</option>
          <option value="reader">{t('admin.users.readers')}</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="px-8 py-4 bg-red-50 border-b border-red-100 flex items-center justify-between">
          <div className="flex items-center gap-3 text-red-600 text-sm font-black">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
            {error}
          </div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 transition-colors">✕</button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-right" dir="rtl">
          <thead>
            <tr className="bg-[#0369a1]/5 text-[14px] font-black text-[#0369a1] uppercase tracking-[0.2em] border-b border-[#0369a1]/10">
              <th className="px-8 py-4">{t('admin.users.user')}</th>
              <th className="px-8 py-4">{t('admin.users.role')}</th>
              <th className="px-8 py-4">{t('admin.users.status')}</th>
              <th className="px-8 py-4">{t('admin.users.joinedDate')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#0369a1]/5">
            {isLoading ? (
              <tr>
                <td colSpan={4} className="py-20 text-center">
                  <div className="w-10 h-10 border-4 border-[#0369a1]/5 border-t-[#0369a1] rounded-full animate-spin mx-auto"></div>
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-20 text-center font-bold text-[#94a3b8]">{t('admin.users.notFound')}</td>
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
        <div className="px-8 py-5 border-t border-[#0369a1]/10 flex items-center justify-between bg-[#0369a1]/5">
          <div className="text-[14px] font-black text-slate-400 uppercase tracking-widest">
            {t('admin.users.pagination', {
              total: total,
              start: (page - 1) * pageSize + 1,
              end: Math.min(page * pageSize, total)
            })}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => p - 1)}
              disabled={page === 1}
              className="p-2 rounded-xl bg-white/50 border border-[#0369a1]/10 hover:bg-[#0369a1]/10 hover:text-[#0369a1] disabled:opacity-20 transition-all text-[#1a1a1a] shadow-sm active:scale-90"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M9 18l6-6-6-6" /></svg>
            </button>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page === totalPages}
              className="p-2 rounded-xl bg-white/50 border border-[#0369a1]/10 hover:bg-[#0369a1]/10 hover:text-[#0369a1] disabled:opacity-20 transition-all text-[#1a1a1a] shadow-sm active:scale-90"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M15 18l-6-6 6-6" /></svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default UserManagementPanel;
