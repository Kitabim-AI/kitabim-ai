/**
 * Admin Tabs - Tabbed interface for admin panels
 */

import React, { useState } from 'react';
import { Book, Users, Settings, BarChart3 } from 'lucide-react';
import { useIsAdmin } from '../../hooks/useAuth';
import { UserManagementPanel } from './users/UserManagementPanel';
import { SystemConfigPanel } from './config/SystemConfigPanel';
import { StatsPanel } from './StatsPanel';
import { useI18n } from '../../i18n/I18nContext';

interface AdminTabsProps {
  bookManagementPanel: React.ReactNode;
}

type TabId = 'books' | 'stats' | 'users' | 'config';

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
    { id: 'books', label: t('admin.booksLabel'), icon: <Book size={18} /> },
    { id: 'users', label: t('admin.usersLabel'), icon: <Users size={18} />, adminOnly: true },
    { id: 'stats', label: t('admin.statsLabel') || 'Statistics', icon: <BarChart3 size={18} />, adminOnly: true },
    { id: 'config', label: t('admin.configLabel'), icon: <Settings size={18} />, adminOnly: true },
  ];

  const visibleTabs = tabs.filter((tab) => !tab.adminOnly || isAdmin);

  return (
    <div className="space-y-6 md:space-y-8" dir="rtl" lang="ug">
      {/* Tab Navigation */}
      <div className="flex items-end px-2 md:px-4 overflow-x-auto scrollbar-hide">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2 md:gap-3 px-3 sm:px-4 md:px-8 py-2.5 md:py-3.5 transition-all duration-300 relative
              rounded-t-[14px] md:rounded-t-[18px] text-[13px] md:text-[15px] font-normal whitespace-nowrap
              ${activeTab === tab.id
                ? 'bg-white text-[#0369a1] shadow-[0_-4px_12px_-4px_rgba(3,105,161,0.08)] z-10'
                : 'text-slate-500 hover:text-[#0369a1] hover:bg-[#0369a1]/5'
              }
            `}
            title={tab.label}
          >
            <span className={`transition-all duration-300 ${activeTab === tab.id ? 'scale-110' : 'opacity-60'}`}>
              {React.cloneElement(tab.icon as React.ReactElement, { size: 18, className: 'md:w-[20px] md:h-[20px]' })}
            </span>
            <span className={`hidden lg:inline transition-all duration-200 ${activeTab === tab.id ? 'font-bold' : ''}`}>
              {tab.label}
            </span>
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="">
        {activeTab === 'books' && bookManagementPanel}
        {activeTab === 'users' && isAdmin && <UserManagementPanel />}
        {activeTab === 'stats' && isAdmin && <StatsPanel />}
        {activeTab === 'config' && isAdmin && <SystemConfigPanel />}
      </div>
    </div>
  );
}

export default AdminTabs;
