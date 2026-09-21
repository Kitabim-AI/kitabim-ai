import { UserMenu } from '@/src/components/auth/AuthButton';
import * as AppContextModule from '@/src/context/AppContext';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', async () => {
  const actual = await vi.importActual('@/src/hooks/useAuth');
  return {
    ...(actual as any),
    useAuth: vi.fn(() => ({
      user: { displayName: 'Test User', email: 't@example.com', avatarUrl: null, role: 'reader' },
      logout: vi.fn(),
      isLoading: false,
    })),
  };
});

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return {
    ...actual as any,
    useAppContext: vi.fn(),
  };
});

const renderMenu = () => {
  const setView = vi.fn();
  const setActiveTab = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ setView, setActiveTab } as any);
  render(<UserMenu />);
  return { setView, setActiveTab };
};

beforeEach(() => vi.clearAllMocks());

test('shows Bookmarks shortcut for signed-in users', () => {
  renderMenu();
  fireEvent.click(screen.getByRole('button'));

  expect(screen.queryByText('nav.continueReading')).not.toBeInTheDocument();
  expect(screen.getByText('nav.bookmarks')).toBeInTheDocument();
});

test('Bookmarks shortcut navigates to the Library reading-bookmarks tab', () => {
  const { setView, setActiveTab } = renderMenu();
  fireEvent.click(screen.getByRole('button'));
  fireEvent.click(screen.getByText('nav.bookmarks'));

  expect(setView).toHaveBeenCalledWith('library');
  expect(setActiveTab).toHaveBeenCalledWith('reading-bookmarks');
});
