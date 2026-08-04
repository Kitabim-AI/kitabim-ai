import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { DictionaryPanel } from '@/src/components/admin/dictionary/DictionaryPanel';
import * as AppContextModule from '@/src/context/AppContext';
import * as AuthModule from '@/src/hooks/useAuth';
import * as authService from '@/src/services/authService';

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return {
    ...(actual as any),
    useAppContext: vi.fn(),
  };
});

vi.mock('@/src/hooks/useAuth', async () => {
  const actual = await vi.importActual('@/src/hooks/useAuth');
  return {
    ...(actual as any),
    useIsAdmin: vi.fn(),
  };
});

vi.mock('@/src/services/authService', async () => {
  const actual = await vi.importActual('@/src/services/authService');
  return {
    ...(actual as any),
    authFetch: vi.fn(),
  };
});

const mockEntry = { id: 1, word: 'كىتاب', definition: 'a book' };

function mockListResponses() {
  vi.mocked(authService.authFetch).mockImplementation(async (url: string, opts?: any) => {
    if (opts?.method === 'DELETE') {
      return { ok: true } as Response;
    }
    if (url.includes('/api/dictionary/stats')) {
      return { ok: true, json: async () => ({ total_words: 1 }) } as Response;
    }
    if (url.includes('/api/dictionary?')) {
      return { ok: true, json: async () => [mockEntry] } as Response;
    }
    return { ok: true, json: async () => [] } as Response;
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({
    setModal: vi.fn(),
  } as any);
});

test('does not show a delete button for non-admin users', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(false);
  mockListResponses();

  render(<DictionaryPanel />);

  await screen.findByText('كىتاب');
  expect(screen.queryByTitle('common.delete')).not.toBeInTheDocument();
});

test('admin can delete an entry after confirming', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  const setModal = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ setModal } as any);
  mockListResponses();

  render(<DictionaryPanel />);

  await screen.findByText('كىتاب');

  fireEvent.click(screen.getByTitle('common.delete'));

  expect(setModal).toHaveBeenCalledWith(
    expect.objectContaining({
      isOpen: true,
      type: 'confirm',
      destructive: true,
      message: 'admin.dictionary.confirmDelete',
    })
  );

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(authService.authFetch).toHaveBeenCalledWith('/api/dictionary/1', { method: 'DELETE' });
  await waitFor(() => expect(screen.queryByText('كىتاب')).not.toBeInTheDocument());
});
