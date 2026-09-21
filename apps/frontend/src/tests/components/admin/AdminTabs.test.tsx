import React from 'react';
import { AdminTabs } from '@/src/components/admin/AdminTabs';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

const mockSetActiveTab = vi.fn();
let mockActiveTab = 'books';
let mockIsAdmin = true;
let mockIsEditor = true;

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: () => ({
    activeTab: mockActiveTab,
    setActiveTab: mockSetActiveTab,
  }),
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: () => ({
    isLoading: false,
    isAuthenticated: true,
  }),
  useIsAdmin: () => mockIsAdmin,
  useIsEditor: () => mockIsEditor,
}));

vi.mock('@/src/i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}));

// Mock sub-panels so we only test AdminTabs logic
vi.mock('@/src/components/admin/rules/AutoCorrectRulesPanel', () => ({
  AutoCorrectRulesPanel: () => <div data-testid="rules-panel">Rules Panel</div>,
}));
vi.mock('@/src/components/admin/users/UserManagementPanel', () => ({
  UserManagementPanel: () => <div data-testid="users-panel">Users Panel</div>,
}));

test('renders books panel when activeTab is books', () => {
  mockActiveTab = 'books';
  render(
    <AdminTabs bookManagementPanel={<div data-testid="books-panel">Books Panel</div>} />
  );

  expect(screen.getByTestId('books-panel')).toBeInTheDocument();
  const booksBtn = screen.getByTitle('admin.booksLabel');
  expect(booksBtn.className).toContain('bg-[#0369a1]');
});

test('falls back to books panel and syncs activeTab when activeTab is invalid', async () => {
  mockActiveTab = 'all-books'; // Stale or invalid tab from library view
  render(
    <AdminTabs bookManagementPanel={<div data-testid="books-panel">Books Panel</div>} />
  );

  // Even on first render, books panel should be displayed and books tab highlighted
  expect(screen.getByTestId('books-panel')).toBeInTheDocument();
  const booksBtn = screen.getByTitle('admin.booksLabel');
  expect(booksBtn.className).toContain('bg-[#0369a1]');

  await waitFor(() => {
    expect(mockSetActiveTab).toHaveBeenCalledWith('books');
  });
});

test('switching tabs triggers setActiveTab', () => {
  mockActiveTab = 'books';
  render(
    <AdminTabs bookManagementPanel={<div data-testid="books-panel">Books Panel</div>} />
  );

  const rulesBtn = screen.getByTitle('admin.rulesLabel');
  fireEvent.click(rulesBtn);
  expect(mockSetActiveTab).toHaveBeenCalledWith('rules');
});
