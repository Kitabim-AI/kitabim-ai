import { Navbar } from '@/src/components/layout/Navbar';
import * as AppContextModule from '@/src/context/AppContext';
import * as AuthModule from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: vi.fn(),
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
  useIsEditor: vi.fn(),
}));

vi.mock('@/src/components/auth', () => ({
  AuthButton: () => <div>auth-button</div>,
}));

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const createContextValue = () => ({
  view: 'library',
  setView: vi.fn(),
  searchQuery: '',
  setSearchQuery: vi.fn(),
  homeSearchQuery: '',
  setHomeSearchQuery: vi.fn(),
  bookActions: { isCheckingGlobal: false, handleFileUpload: vi.fn() },
  chat: { clearChat: vi.fn() },
  setPage: vi.fn(),
  isLoading: false,
});

const renderNavbar = () =>
  render(
    <I18nContext.Provider value={i18nValue}>
      <Navbar />
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
  vi.mocked(AuthModule.useAuth).mockReturnValue({ isAuthenticated: true } as any);
  vi.mocked(AuthModule.useIsEditor).mockReturnValue(true);
});

test('Navbar renders correctly and handles view changes', () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);

  renderNavbar();

  expect(screen.getByText(/Kitabim/i)).toBeInTheDocument();

  fireEvent.click(screen.getByTitle('nav.library'));
  expect(context.setView).toHaveBeenCalledWith('library');

  fireEvent.click(screen.getByTitle('nav.globalChat'));
  expect(context.setView).toHaveBeenCalledWith('global-chat');
  expect(context.chat.clearChat).toHaveBeenCalled();

  fireEvent.click(screen.getByTitle('nav.admin'));
  expect(context.setView).toHaveBeenCalledWith('admin');
  expect(context.setPage).toHaveBeenCalledWith(1);
});

test('Navbar handles search input', () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);

  renderNavbar();

  const input = screen.getByPlaceholderText('library.searchPlaceholder');
  fireEvent.change(input, { target: { value: 'new query' } });
  vi.advanceTimersByTime(300);

  expect(context.setSearchQuery).toHaveBeenCalledWith('new query');
});

test('Navbar handles file upload trigger', () => {
  const context = createContextValue();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue(context as any);

  const { container } = renderNavbar();
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['%PDF'], 'book.pdf', { type: 'application/pdf' });

  fireEvent.change(fileInput, { target: { files: [file] } });
  expect(context.bookActions.handleFileUpload).toHaveBeenCalled();
});
