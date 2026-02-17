/**
 * Admin Tabs - Tabbed interface for admin panels
 */

import React, { useState } from 'react';
import { Book, Users } from 'lucide-react';
import { useIsAdmin } from '../../hooks/useAuth';
import { UserManagementPanel } from './users/UserManagementPanel';
import { useI18n } from '../../i18n/I18nContext';

interface AdminTabsProps {
  bookManagementPanel: React.ReactNode;
}

type TabId = 'books' | 'users';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

export function AdminTabs({ bookManagementPanel }: AdminTabsProps) {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<TabId>('books');
  const isAdmin = useIsAdmin();

  const tabs: Tab[] = [
    { id: 'books', label: t('admin.bookManagement'), icon: <Book size={18} /> },
    { id: 'users', label: t('admin.userManagement'), icon: <Users size={18} />, adminOnly: true },
  ];

  const visibleTabs = tabs.filter((tab) => !tab.adminOnly || isAdmin);

  return (
    <div className="space-y-8 animate-fade-in" dir="rtl" lang="ug">
      {/* Tab Navigation */}
      <div className="flex items-center gap-4 border-b border-[#0369a1]/10">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-3 px-8 py-4 text-[16px] font-normal uppercase
              border-b-4 transition-all active:scale-95
              ${activeTab === tab.id
                ? 'border-[#0369a1] text-[#1a1a1a]'
                : 'border-transparent text-slate-400 hover:text-[#0369a1] hover:border-[#0369a1]/30'
              }
            `}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="animate-fade-in">
        {activeTab === 'books' && bookManagementPanel}
        {activeTab === 'users' && isAdmin && <UserManagementPanel />}
      </div>
    </div>
  );
}

export default AdminTabs;
