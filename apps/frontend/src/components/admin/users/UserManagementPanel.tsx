import React, { useState, useEffect, useCallback, useRef } from 'react';
import { UserService, UserPublic } from '../../../services/userService';
import { Users, Filter, Check, Search, X, Edit2, Save, Loader2 } from 'lucide-react';
import { useIsAdmin, useAuth } from '../../../hooks/useAuth';
import { useI18n } from '../../../i18n/I18nContext';
import { UserAvatar } from '../../common/UserAvatar';

interface UserRowProps {
  user: UserPublic;
  isEditing: boolean;
  editData: { role: 'admin' | 'editor' | 'reader'; isActive: boolean } | null;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  onRoleChange: (role: 'admin' | 'editor' | 'reader') => void;
  onStatusChange: (isActive: boolean) => void;
  isSaving: boolean;
  isOwnRecord: boolean;
}

const UserRow: React.FC<UserRowProps> = ({
  user,
  isEditing,
  editData,
  onEdit,
  onSave,
  onCancel,
  onRoleChange,
  onStatusChange,
  isSaving,
  isOwnRecord
}) => {
  const { t } = useI18n();
  const [showRoleDropdown, setShowRoleDropdown] = useState(false);
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);

  const roleColors: Record<string, { bg: string; text: string; label: string }> = {
    admin: { bg: 'bg-red-50', text: 'text-red-600', label: t('admin.users.admin') },
    editor: { bg: 'bg-blue-50', text: 'text-blue-600', label: t('admin.users.editor') },
    reader: { bg: 'bg-emerald-50', text: 'text-emerald-600', label: t('admin.users.reader') },
  };

  const statusColors: Record<string, { bg: string; text: string; label: string }> = {
    active: { bg: 'bg-emerald-50', text: 'text-emerald-600', label: t('admin.users.active') },
    inactive: { bg: 'bg-red-50', text: 'text-red-600', label: t('admin.users.suspended') },
  };

  const formatDate = (dateString?: string, includeTime: boolean = false) => {
    if (!dateString) return t('admin.users.unknown');
    const date = new Date(dateString);
    if (includeTime) {
      return `${date.toLocaleDateString()} ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    }
    return date.toLocaleDateString();
  };

  const currentRole = isEditing && editData ? editData.role : user.role;
  const currentStatus = isEditing && editData ? editData.isActive : user.is_active;

  return (
    <tr className={`border-b border-[#0369a1]/5 hover:bg-[#0369a1]/5 transition-colors group/row ${isEditing ? 'bg-[#0369a1]/5' : ''}`}>
      <td className="px-4 md:px-8 py-3 md:py-5">
        <div className="flex items-center gap-2 md:gap-4">
          <UserAvatar
            url={user.avatar_url}
            name={user.display_name}
            className="w-8 h-8 md:w-10 md:h-10 rounded-full object-cover ring-2 ring-[#0369a1]/20"
          />
          <div className="flex flex-col gap-1">
            <div className="font-normal text-[#1a1a1a] text-[14px] md:text-[16px] lg:text-[18px]">{user.display_name}</div>
            <div className="text-[11px] md:text-[13px] font-normal text-[#94a3b8] uppercase truncate max-w-[150px] md:max-w-none">{user.email}</div>

            {/* Mobile Role & Status Section */}
            <div className="flex lg:hidden items-center gap-2 mt-1.5 flex-wrap">
              <div className="relative">
                {isEditing ? (
                  <button
                    onClick={() => setShowRoleDropdown(!showRoleDropdown)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 ${roleColors[currentRole]?.bg || 'bg-slate-50'} ${roleColors[currentRole]?.text || 'text-slate-500'} rounded-lg text-[10px] font-normal uppercase border-2 border-[#0369a1] transition-all active:scale-95 shadow-sm`}
                  >
                    {roleColors[currentRole]?.label || currentRole}
                    <svg width="8" height="8" viewBox="0 0 12 12" fill="currentColor">
                      <path d="M6 8L2 4h8L6 8z" />
                    </svg>
                  </button>
                ) : (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 ${roleColors[currentRole]?.bg || 'bg-slate-50'} ${roleColors[currentRole]?.text || 'text-slate-500'} rounded-lg text-[9px] font-normal uppercase border border-current/10`}>
                    {roleColors[currentRole]?.label || currentRole}
                  </span>
                )}

                {isEditing && showRoleDropdown && (
                  <div className="absolute top-full right-0 mt-2 w-32 glass-panel shadow-2xl z-[100] overflow-hidden py-1.5 border border-[#0369a1]/10 rounded-xl" dir="rtl">
                    {(['admin', 'editor', 'reader'] as const).map((role) => (
                      <button
                        key={role}
                        onClick={() => {
                          setShowRoleDropdown(false);
                          onRoleChange(role);
                        }}
                        className={`w-full flex items-center justify-between px-4 py-2.5 text-[12px] font-normal uppercase transition-all ${role === currentRole ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                      >
                        {roleColors[role].label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="relative">
                {isEditing ? (
                  <button
                    onClick={() => setShowStatusDropdown(!showStatusDropdown)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 ${statusColors[currentStatus ? 'active' : 'inactive']?.bg || 'bg-slate-50'} ${statusColors[currentStatus ? 'active' : 'inactive']?.text || 'text-slate-500'} rounded-lg text-[10px] font-normal uppercase border-2 border-[#0369a1] transition-all active:scale-95 shadow-sm`}
                  >
                    {statusColors[currentStatus ? 'active' : 'inactive']?.label}
                    <svg width="8" height="8" viewBox="0 0 12 12" fill="currentColor">
                      <path d="M6 8L2 4h8L6 8z" />
                    </svg>
                  </button>
                ) : (
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 ${statusColors[currentStatus ? 'active' : 'inactive']?.bg || 'bg-slate-50'} ${statusColors[currentStatus ? 'active' : 'inactive']?.text || 'text-slate-500'} rounded-lg text-[9px] font-normal uppercase border border-current/10`}>
                    {statusColors[currentStatus ? 'active' : 'inactive']?.label}
                  </span>
                )}

                {isEditing && showStatusDropdown && (
                  <div className="absolute top-full right-0 mt-2 w-32 glass-panel shadow-2xl z-[100] overflow-hidden py-1.5 border border-[#0369a1]/10 rounded-xl" dir="rtl">
                    {([
                      { value: true, key: 'active' },
                      { value: false, key: 'inactive' }
                    ] as const).map((status) => (
                      <button
                        key={status.key}
                        onClick={() => {
                          setShowStatusDropdown(false);
                          onStatusChange(status.value);
                        }}
                        className={`w-full flex items-center justify-between px-4 py-2.5 text-[12px] font-normal uppercase transition-all ${status.value === currentStatus ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                      >
                        {statusColors[status.key].label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </td>

      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5">
        {isEditing ? (
          <div className="relative">
            <button
              onClick={() => setShowRoleDropdown(!showRoleDropdown)}
              className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${roleColors[currentRole]?.bg || 'bg-slate-50'} ${roleColors[currentRole]?.text || 'text-slate-500'} rounded-lg text-[11px] md:text-[14px] font-normal uppercase transition-all active:scale-95 border-2 border-[#0369a1]`}
            >
              {roleColors[currentRole]?.label || currentRole}
              <svg width="8" height="8" viewBox="0 0 12 12" fill="currentColor" className="md:w-[10px] md:h-[10px]">
                <path d="M6 8L2 4h8L6 8z" />
              </svg>
            </button>

            {showRoleDropdown && (
              <div className="absolute top-full left-0 mt-2 w-48 glass-panel shadow-2xl z-[100] overflow-hidden py-2" style={{ borderRadius: '16px' }}>
                {(['admin', 'editor', 'reader'] as const).map((role) => (
                  <button
                    key={role}
                    onClick={() => {
                      setShowRoleDropdown(false);
                      onRoleChange(role);
                    }}
                    className={`w-full flex items-center px-5 py-3 text-[14px] font-normal uppercase transition-all ${role === currentRole ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                  >
                    {roleColors[role].label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <span className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${roleColors[currentRole]?.bg || 'bg-slate-50'} ${roleColors[currentRole]?.text || 'text-slate-500'} rounded-lg text-[11px] md:text-[14px] font-normal uppercase border border-current/10`}>
            {roleColors[currentRole]?.label || currentRole}
          </span>
        )}
      </td>

      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5">
        {isEditing ? (
          <div className="relative">
            <button
              onClick={() => setShowStatusDropdown(!showStatusDropdown)}
              className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${statusColors[currentStatus ? 'active' : 'inactive']?.bg || 'bg-slate-50'} ${statusColors[currentStatus ? 'active' : 'inactive']?.text || 'text-slate-500'} rounded-lg text-[11px] md:text-[14px] font-normal uppercase transition-all active:scale-95 border-2 border-[#0369a1]`}
            >
              {statusColors[currentStatus ? 'active' : 'inactive']?.label || (currentStatus ? t('admin.users.active') : t('admin.users.suspended'))}
              <svg width="8" height="8" viewBox="0 0 12 12" fill="currentColor" className="md:w-[10px] md:h-[10px]">
                <path d="M6 8L2 4h8L6 8z" />
              </svg>
            </button>

            {showStatusDropdown && (
              <div className="absolute top-full left-0 mt-2 w-48 glass-panel shadow-2xl z-[100] overflow-hidden py-2" style={{ borderRadius: '16px' }}>
                {([
                  { value: true, key: 'active' },
                  { value: false, key: 'inactive' }
                ] as const).map((status) => (
                  <button
                    key={status.key}
                    onClick={() => {
                      setShowStatusDropdown(false);
                      onStatusChange(status.value);
                    }}
                    className={`w-full flex items-center px-5 py-3 text-[14px] font-normal uppercase transition-all ${status.value === currentStatus ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                  >
                    {statusColors[status.key].label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          <span className={`inline-flex items-center gap-1 md:gap-2 px-2 md:px-3 py-1 md:py-1.5 ${statusColors[currentStatus ? 'active' : 'inactive']?.bg || 'bg-slate-50'} ${statusColors[currentStatus ? 'active' : 'inactive']?.text || 'text-slate-500'} rounded-lg text-[11px] md:text-[14px] font-normal uppercase border border-current/10`}>
            {statusColors[currentStatus ? 'active' : 'inactive']?.label || (currentStatus ? t('admin.users.active') : t('admin.users.suspended'))}
          </span>
        )}
      </td>

      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-[13px] md:text-[16px] font-bold text-[#94a3b8]">
        {formatDate(user.created_at)}
      </td>

      <td className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-[13px] md:text-[14px] font-bold text-[#94a3b8]">
        {formatDate(user.last_login_at, true)}
      </td>

      <td className="px-4 md:px-8 py-3 md:py-5 text-left">
        <div className="flex items-center justify-end gap-1 md:gap-2">
          {isEditing ? (
            <>
              <button
                onClick={onSave}
                disabled={isSaving}
                className="p-1.5 md:p-2.5 bg-[#0369a1] text-white rounded-xl hover:bg-[#0369a1]/90 transition-all shadow-lg shadow-[#0369a1]/10 disabled:opacity-50"
                title={t('common.save')}
              >
                {isSaving ? <Loader2 size={16} className="animate-spin md:w-[18px] md:h-[18px]" /> : <Save size={16} className="md:w-[18px] md:h-[18px]" />}
              </button>
              <button
                onClick={onCancel}
                disabled={isSaving}
                className="p-1.5 md:p-2 bg-slate-100 text-slate-400 rounded-xl hover:bg-slate-200 active:scale-90 transition-all disabled:opacity-50"
                title={t('common.cancel')}
              >
                <X size={18} className="md:w-5 md:h-5" />
              </button>
            </>
          ) : (
            <button
              onClick={onEdit}
              disabled={isOwnRecord}
              className={`p-1.5 md:p-2 rounded-xl transition-all ${isOwnRecord
                ? 'bg-slate-100 text-slate-300 cursor-not-allowed'
                : 'bg-[#0369a1]/10 text-[#0369a1] hover:bg-[#0369a1] hover:text-white'
                }`}
              title={isOwnRecord ? t('admin.users.cannotEditSelf') : t('common.edit')}
            >
              <Edit2 size={16} className="md:w-[18px] md:h-[18px]" />
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

export function UserManagementPanel() {
  const { t } = useI18n();
  const isAdmin = useIsAdmin();
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<UserPublic[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isRoleFilterOpen, setIsRoleFilterOpen] = useState(false);
  const [isStatusFilterOpen, setIsStatusFilterOpen] = useState(false);
  const roleFilterRef = useRef<HTMLDivElement>(null);
  const statusFilterRef = useRef<HTMLDivElement>(null);
  const loaderRef = useRef<HTMLDivElement>(null);

  // Edit state
  const [editingUserId, setEditingUserId] = useState<string | null>(null);
  const [editData, setEditData] = useState<{ role: 'admin' | 'editor' | 'reader'; isActive: boolean } | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 500);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (roleFilterRef.current && !roleFilterRef.current.contains(event.target as Node)) {
        setIsRoleFilterOpen(false);
      }
      if (statusFilterRef.current && !statusFilterRef.current.contains(event.target as Node)) {
        setIsStatusFilterOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const loadUsers = useCallback(async (isInitial: boolean = false) => {
    if (!isAdmin) return;
    if (!isInitial && (isLoading || isLoadingMore || !hasMore)) return;

    if (isInitial) {
      setIsLoading(true);
      setPage(1);
    } else {
      setIsLoadingMore(true);
    }

    setError(null);
    try {
      const nextPage = isInitial ? 1 : page + 1;
      const data = await UserService.listUsers(nextPage, pageSize, roleFilter, statusFilter, debouncedSearch);

      if (isInitial) {
        setUsers(data.users);
      } else {
        setUsers(prev => {
          const existingIds = prev.map(u => u.id);
          const newUsers = data.users.filter(u => !existingIds.includes(u.id));
          return [...prev, ...newUsers];
        });
        setPage(nextPage);
      }

      setTotal(data.total);
      setHasMore(data.users.length === pageSize && (isInitial ? data.users.length : users.length + data.users.length) < data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.users.loadError'));
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [isAdmin, page, pageSize, roleFilter, statusFilter, debouncedSearch, isLoading, isLoadingMore, hasMore, users.length]);

  useEffect(() => {
    loadUsers(true);
  }, [isAdmin, roleFilter, statusFilter, debouncedSearch]); // Reload on filter or search change

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isLoading && !isLoadingMore && hasMore) {
          loadUsers(false);
        }
      },
      { threshold: 0.1, rootMargin: '200px' }
    );

    if (loaderRef.current) observer.observe(loaderRef.current);
    return () => observer.disconnect();
  }, [loadUsers, isLoading, isLoadingMore, hasMore]);

  const handleEdit = (user: UserPublic) => {
    setEditingUserId(user.id);
    setEditData({
      role: user.role,
      isActive: user.is_active
    });
  };

  const handleSave = async (userId: string) => {
    if (!editData) return;

    setIsSaving(true);
    try {
      const user = users.find(u => u.id === userId);
      if (!user) return;

      // Update role if changed
      if (editData.role !== user.role) {
        const updatedUser = await UserService.changeUserRole(userId, editData.role);
        setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: updatedUser.role } : u));
      }

      // Update status if changed
      if (editData.isActive !== user.is_active) {
        const updatedUser = await UserService.changeUserStatus(userId, editData.isActive);
        setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_active: updatedUser.is_active } : u));
      }

      setEditingUserId(null);
      setEditData(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.users.statusUpdateError'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setEditingUserId(null);
    setEditData(null);
  };

  if (!isAdmin) {
    return (
      <div className="glass-panel p-20 flex flex-col items-center justify-center text-center">
        <div className="p-4 bg-red-50 text-red-500 rounded-3xl mb-6">
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
        </div>
        <h3 className="text-xl font-normal text-[#1a1a1a] mb-2">{t('admin.users.accessRequired')}</h3>
        <p className="text-[#94a3b8] font-normal">{t('admin.users.accessRequiredDetail')}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 md:space-y-8 animate-fade-in" dir="rtl" lang="ug">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-6 border-b border-[#75C5F0]/20">
        <div className="flex items-center gap-3 md:gap-4 group">
          <div className="p-2 md:p-3 bg-[#0369a1] text-white rounded-xl shadow-lg shadow-[#0369a1]/20 transform transition-all duration-500 group-hover:-rotate-6">
            <Users size={20} className="md:w-6 md:h-6" />
          </div>
          <div>
            <h2 className="text-xl md:text-2xl lg:text-3xl font-normal text-[#1a1a1a]">{t('admin.users.title')}</h2>
            <div className="flex items-center gap-2 mt-1">
              <span className="w-6 md:w-8 h-[2px] bg-[#0369a1] rounded-full" />
              <p className="text-[11px] md:text-[14px] font-normal text-[#94a3b8] uppercase">{t('admin.users.subtitle')}</p>
            </div>
          </div>
        </div>

      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col md:flex-row gap-3 md:gap-4">
        <div className="relative flex-1 group">
          <div className="absolute inset-y-0 right-0 pr-3 md:pr-4 flex items-center pointer-events-none text-[#94a3b8] group-focus-within:text-[#0369a1] transition-colors">
            <Search size={16} strokeWidth={3} className="md:w-[18px] md:h-[18px]" />
          </div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('admin.users.searchPlaceholder') || "ئابونتلارنى ئىزدەش (نامى ياكى ئېلخەت)..."}
            className="w-full pr-10 md:pr-12 pl-8 md:pl-10 py-2 md:py-2.5 bg-white border-2 border-[#0369a1]/10 rounded-2xl outline-none focus:border-[#0369a1] focus:ring-4 focus:ring-[#0369a1]/10 transition-all uyghur-text-small shadow-sm text-sm md:text-base"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute inset-y-0 left-3 md:left-4 flex items-center text-[#94a3b8] hover:text-[#0369a1] transition-colors"
            >
              <X size={14} className="md:w-4 md:h-4" />
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-[12px] md:text-[14px] font-normal text-[#0369a1] bg-[#0369a1]/10 px-3 md:px-4 py-2 md:py-2.5 rounded-full border border-[#0369a1]/20 shadow-sm whitespace-nowrap self-start md:self-auto">
          <Users size={12} className="md:w-[14px] md:h-[14px]" />
          {t('admin.users.total', { count: total })}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="px-8 py-4 bg-red-50 border border-red-100 rounded-2xl flex items-center justify-between">
          <div className="flex items-center gap-3 text-red-600 text-sm font-normal">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
            </svg>
            {error}
          </div>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600 transition-colors">✕</button>
        </div>
      )}

      <div className="glass-panel rounded-[16px] md:rounded-[24px]" style={{ padding: 0, overflow: 'visible' }}>
        <div className="overflow-x-auto rounded-[16px] md:rounded-[24px]" style={{ overflow: 'hidden' }}>
          <table className="w-full text-right lg:min-w-[700px]" dir="rtl">
            <thead>
              <tr className="bg-[#0369a1]/5 text-[12px] md:text-[14px] lg:text-[16px] font-normal text-[#0369a1] uppercase border-b border-[#0369a1]/10">
                <th className="px-4 md:px-8 py-3 md:py-5 text-right font-normal">{t('admin.users.user')}</th>
                <th className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                  <div className="flex items-center gap-1 md:gap-2 relative">
                    {t('admin.users.role')}
                    <button
                      onClick={() => setIsRoleFilterOpen(!isRoleFilterOpen)}
                      className={`p-1.5 rounded-lg transition-all ${roleFilter !== 'all' ? 'bg-[#0369a1] text-white shadow-md' : 'hover:bg-[#0369a1]/10'}`}
                    >
                      <Filter size={14} strokeWidth={roleFilter !== 'all' ? 3 : 2} />
                    </button>

                    {isRoleFilterOpen && (
                      <div
                        ref={roleFilterRef}
                        className="absolute top-full left-0 mt-2 w-48 glass-panel shadow-2xl z-[100] overflow-hidden py-2 border border-[#0369a1]/10"
                        style={{ borderRadius: '16px' }}
                      >
                        {[
                          { id: 'all', label: t('admin.users.allRoles') },
                          { id: 'admin', label: t('admin.users.admins') },
                          { id: 'editor', label: t('admin.users.editors') },
                          { id: 'reader', label: t('admin.users.readers') }
                        ].map((role) => (
                          <button
                            key={role.id}
                            onClick={() => {
                              setRoleFilter(role.id);
                              setIsRoleFilterOpen(false);
                            }}
                            className={`w-full flex items-center justify-between px-5 py-3 text-[14px] font-normal uppercase transition-all ${roleFilter === role.id ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                          >
                            {role.label}
                            {roleFilter === role.id && <Check size={14} strokeWidth={3} />}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </th>
                <th className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">
                  <div className="flex items-center gap-1 md:gap-2 relative">
                    {t('admin.users.status')}
                    <button
                      onClick={() => setIsStatusFilterOpen(!isStatusFilterOpen)}
                      className={`p-1.5 rounded-lg transition-all ${statusFilter !== 'all' ? 'bg-[#0369a1] text-white shadow-md' : 'hover:bg-[#0369a1]/10'}`}
                    >
                      <Filter size={14} strokeWidth={statusFilter !== 'all' ? 3 : 2} />
                    </button>

                    {isStatusFilterOpen && (
                      <div
                        ref={statusFilterRef}
                        className="absolute top-full left-0 mt-2 w-48 glass-panel shadow-2xl z-[100] overflow-hidden py-2 border border-[#0369a1]/10"
                        style={{ borderRadius: '16px' }}
                      >
                        {[
                          { id: 'all', label: t('admin.users.allStatuses') },
                          { id: 'active', label: t('admin.users.active') },
                          { id: 'inactive', label: t('admin.users.suspended') }
                        ].map((status) => (
                          <button
                            key={status.id}
                            onClick={() => {
                              setStatusFilter(status.id);
                              setIsStatusFilterOpen(false);
                            }}
                            className={`w-full flex items-center justify-between px-5 py-3 text-[14px] font-normal uppercase transition-all ${statusFilter === status.id ? 'bg-[#0369a1]/10 text-[#0369a1]' : 'text-[#1a1a1a] hover:bg-[#0369a1]/5'}`}
                          >
                            {status.label}
                            {statusFilter === status.id && <Check size={14} strokeWidth={3} />}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </th>
                <th className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">{t('admin.users.joinedDate')}</th>
                <th className="hidden lg:table-cell px-4 md:px-8 py-3 md:py-5 text-right font-normal">{t('admin.users.lastLogin')}</th>
                <th className="px-4 md:px-8 py-3 md:py-5 text-left font-normal">{t('admin.table.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#0369a1]/5">
              {isLoading && users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-20 text-center">
                    <div className="w-10 h-10 border-4 border-[#0369a1]/5 border-t-[#0369a1] rounded-full animate-spin mx-auto"></div>
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-20 text-center font-bold text-[#94a3b8]">{t('admin.users.notFound')}</td>
                </tr>
              ) : (
                users.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    isEditing={editingUserId === user.id}
                    editData={editingUserId === user.id ? editData : null}
                    onEdit={() => handleEdit(user)}
                    onSave={() => handleSave(user.id)}
                    onCancel={handleCancel}
                    onRoleChange={(role) => setEditData(prev => prev ? { ...prev, role } : null)}
                    onStatusChange={(isActive) => setEditData(prev => prev ? { ...prev, isActive } : null)}
                    isSaving={isSaving}
                    isOwnRecord={currentUser?.id === user.id}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Infinite Scroll Trigger */}
        <div ref={loaderRef} className="px-8 py-8 border-t border-[#0369a1]/10 flex flex-col items-center justify-center bg-[#0369a1]/5 gap-4">
          {isLoadingMore ? (
            <div className="flex flex-col items-center gap-3 animate-fade-in">
              <div className="w-8 h-8 border-3 border-[#0369a1]/10 border-t-[#0369a1] rounded-full animate-spin"></div>
              <span className="text-[10px] font-black text-[#0369a1] uppercase animate-pulse">{t('common.loadingMore')}</span>
            </div>
          ) : !hasMore && users.length > 0 && (
            <div className="flex flex-col items-center gap-3 opacity-30">
              <div className="w-12 h-[1px] bg-[#94a3b8]" />
              <p className="text-[10px] font-black text-[#94a3b8] uppercase">{t('common.endOfList')}</p>
              <div className="w-12 h-[2px] bg-[#94a3b8]" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default UserManagementPanel;
