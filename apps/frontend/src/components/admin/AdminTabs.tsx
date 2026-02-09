/**
 * Admin Tabs - Tabbed interface for admin panels
 */

import React, { useState } from 'react';
import { Book, Users } from 'lucide-react';
import { useIsAdmin } from '../../hooks/useAuth';
import { UserManagementPanel } from './users';

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

const tabs: Tab[] = [
  { id: 'books', label: 'Books', icon: <Book size={16} /> },
  { id: 'users', label: 'Users', icon: <Users size={16} />, adminOnly: true },
];

export function AdminTabs({ bookManagementPanel }: AdminTabsProps) {
  const [activeTab, setActiveTab] = useState<TabId>('books');
  const isAdmin = useIsAdmin();

  // Filter tabs based on permissions
  const visibleTabs = tabs.filter((tab) => !tab.adminOnly || isAdmin);

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div className="flex items-center gap-2 border-b border-slate-200">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              flex items-center gap-2 px-4 py-3 text-sm font-medium
              border-b-2 transition-all
              ${activeTab === tab.id
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
              }
            `}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === 'books' && bookManagementPanel}
        {activeTab === 'users' && isAdmin && <UserManagementPanel />}
      </div>
    </div>
  );
}

export default AdminTabs;
