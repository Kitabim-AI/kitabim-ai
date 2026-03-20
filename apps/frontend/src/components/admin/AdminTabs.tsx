/**
 * Admin Tabs - Tabbed interface for admin panels
 */

import React, { useState } from 'react';
import { Book, Users, Settings, BarChart3, Mail, Sparkles } from 'lucide-react';
import { useIsAdmin } from '../../hooks/useAuth';
import { UserManagementPanel } from './users/UserManagementPanel';
import { SystemConfigPanel } from './config/SystemConfigPanel';
import { AutoCorrectRulesPanel } from './rules/AutoCorrectRulesPanel';
import { StatsPanel } from './StatsPanel';
import { ContactSubmissionsPanel } from './ContactSubmissionsPanel';
import { DictionaryManagementPanel } from './dictionary/DictionaryManagementPanel';
import { useI18n } from '../../i18n/I18nContext';
import { useAppContext } from '../../context/AppContext';

interface AdminTabsProps {
  bookManagementPanel: React.ReactNode;
}

type TabId = 'books' | 'stats' | 'users' | 'contacts' | 'config' | 'rules' | 'dictionary';

interface Tab {
  id: TabId;
  label: string;
  icon: React.ReactNode;
  adminOnly?: boolean;
}

export function AdminTabs({ bookManagementPanel }: AdminTabsProps) {
  const { t } = useI18n();
  const { activeTab, setActiveTab } = useAppContext();
  const isAdmin = useIsAdmin();

  const tabs: Tab[] = [
    { id: 'books', label: t('admin.booksLabel'), icon: <Book size={18} /> },
    { id: 'users', label: t('admin.usersLabel'), icon: <Users size={18} />, adminOnly: true },
    { id: 'rules', label: t('admin.rulesLabel') || 'Auto-Correction', icon: <Sparkles size={18} />, adminOnly: false },
    { id: 'dictionary', label: t('admin.dictionaryLabel') || 'Dictionary', icon: <Book size={18} />, adminOnly: false },
    { id: 'stats', label: t('admin.statsLabel') || 'Statistics', icon: <BarChart3 size={18} />, adminOnly: true },
    { id: 'config', label: t('admin.configLabel'), icon: <Settings size={18} />, adminOnly: true },
    { id: 'contacts', label: t('admin.contactsLabel'), icon: <Mail size={18} />, adminOnly: true },
  ];

  const visibleTabs = tabs.filter((tab) => !tab.adminOnly || isAdmin);

  return (
    <div className="space-y-0 px-3 py-3 sm:px-6 md:px-0" dir="rtl" lang="ug">
      {/* Tab Navigation */}
      <div className="border-b border-slate-200">
        <div className="flex items-end overflow-x-auto overflow-y-hidden gap-1" style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
          {visibleTabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 md:gap-2.5 px-4 sm:px-5 md:px-6 py-2.5 md:py-3 transition-all duration-200
                text-[13px] md:text-[14px] whitespace-nowrap rounded-t-xl font-normal
                ${activeTab === tab.id
                  ? 'bg-[#0369a1] text-white shadow-sm'
                  : 'bg-white text-slate-600 border border-b-0 border-slate-200 hover:bg-slate-50 hover:text-slate-800'
                }
              `}
              title={tab.label}
            >
              <span className="transition-all duration-200">
                {React.cloneElement(tab.icon as React.ReactElement<any>, { size: 16, className: 'md:w-[17px] md:h-[17px]' })}
              </span>
              <span className="hidden lg:inline mt-[3px]">
                {tab.label}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div className="pt-6 md:pt-8">
        {activeTab === 'books' && bookManagementPanel}
        {activeTab === 'users' && isAdmin && <UserManagementPanel />}
        {activeTab === 'rules' && <AutoCorrectRulesPanel />}
        {activeTab === 'contacts' && isAdmin && <ContactSubmissionsPanel />}
        {activeTab === 'stats' && isAdmin && <StatsPanel />}
        {activeTab === 'config' && isAdmin && <SystemConfigPanel />}
        {activeTab === 'dictionary' && <DictionaryManagementPanel />}
      </div>
    </div>
  );
}

export default AdminTabs;
