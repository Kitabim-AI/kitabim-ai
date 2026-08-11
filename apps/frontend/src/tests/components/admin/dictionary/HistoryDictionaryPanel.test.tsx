import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { HistoryDictionaryPanel } from '@/src/components/admin/dictionary/HistoryDictionaryPanel';
import * as AppContextModule from '@/src/context/AppContext';
import * as AuthModule from '@/src/hooks/useAuth';
import * as authService from '@/src/services/authService';

vi.mock('@/src/context/AppContext', async () => {
  const actual = await vi.importActual('@/src/context/AppContext');
  return { ...(actual as any), useAppContext: vi.fn() };
});

vi.mock('@/src/hooks/useAuth', async () => {
  const actual = await vi.importActual('@/src/hooks/useAuth');
  return { ...(actual as any), useIsAdmin: vi.fn() };
});

vi.mock('@/src/services/authService', async () => {
  const actual = await vi.importActual('@/src/services/authService');
  return { ...(actual as any), authFetch: vi.fn() };
});

const mockEntry = { id: 1, term: 'تارىخ سۆزى', letter_group: 'ت' };

function mockListResponses(writeResponse?: Response) {
  vi.mocked(authService.authFetch).mockImplementation(async (url: string, opts?: any) => {
    if (opts?.method === 'DELETE') return { ok: true } as Response;
    if (opts?.method === 'POST' || opts?.method === 'PATCH') {
      return writeResponse ?? ({ ok: true, json: async () => ({ id: 2, term: 'يېڭى سۆز', letter_group: 'ي' }) } as Response);
    }
    if (url.includes('/api/history-dictionary/stats')) {
      return { ok: true, json: async () => ({ total_entries: 1 }) } as Response;
    }
    if (url.includes('/api/history-dictionary?')) {
      return { ok: true, json: async () => [mockEntry] } as Response;
    }
    return { ok: true, json: async () => [] } as Response;
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ setModal: vi.fn() } as any);
});

test('does not show a delete button for non-admin users but displays record source badge', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(false);
  mockListResponses();

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  expect(screen.queryByTitle('common.delete')).not.toBeInTheDocument();
  expect(screen.getByText('admin.historyDictionary.sourceWeb')).toBeInTheDocument();
});

test('admin can delete an entry after confirming', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  const setModal = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ setModal } as any);
  mockListResponses();

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('common.delete'));

  expect(setModal).toHaveBeenCalledWith(
    expect.objectContaining({
      isOpen: true,
      type: 'confirm',
      destructive: true,
      message: 'admin.historyDictionary.confirmDelete',
    })
  );

  const config = setModal.mock.calls[0][0];
  await act(async () => {
    await config.onConfirm();
  });

  expect(authService.authFetch).toHaveBeenCalledWith('/api/history-dictionary/1', { method: 'DELETE' });
  await waitFor(() => expect(screen.queryByText('تارىخ سۆزى')).not.toBeInTheDocument());
});

test('does not show an add button for non-admin users', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(false);
  mockListResponses();

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  expect(screen.queryByTitle('admin.historyDictionary.addEntry')).not.toBeInTheDocument();
});

test('admin can create a new entry via the add modal', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  mockListResponses();

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('admin.historyDictionary.newEntry'));

  fireEvent.change(screen.getByPlaceholderText('admin.historyDictionary.term'), {
    target: { value: 'يېڭى سۆز' },
  });
  fireEvent.change(screen.getByPlaceholderText('admin.historyDictionary.definition'), {
    target: { value: 'تارىخىي مەنىسى' },
  });

  fireEvent.click(screen.getByText('common.save'));

  await waitFor(() =>
    expect(authService.authFetch).toHaveBeenCalledWith(
      '/api/history-dictionary',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ term: 'يېڭى سۆز', transliteration: null, definition: 'تارىخىي مەنىسى', is_ai_generated: true, aliases: [] }),
      })
    )
  );
  await waitFor(() =>
    expect(screen.queryByPlaceholderText('admin.historyDictionary.term')).not.toBeInTheDocument()
  );
});

test('shows an inline error when the add modal gets a duplicate-term response', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  mockListResponses({
    ok: false,
    status: 409,
    json: async () => ({
      detail: { message: 'An entry for this term already exists', existing_id: 1, existing_term: 'تارىخ سۆزى' },
    }),
  } as Response);

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('admin.historyDictionary.newEntry'));
  fireEvent.change(screen.getByPlaceholderText('admin.historyDictionary.term'), {
    target: { value: 'تارىخ سۆزى' },
  });
  fireEvent.change(screen.getByPlaceholderText('admin.historyDictionary.definition'), {
    target: { value: 'تارىخىي مەنىسى' },
  });
  fireEvent.click(screen.getByText('common.save'));

  await screen.findByText('An entry for this term already exists');
  expect(screen.getByPlaceholderText('admin.historyDictionary.term')).toBeInTheDocument();
});

test('admin can edit an existing entry via the edit modal', async () => {
  vi.mocked(AuthModule.useIsAdmin).mockReturnValue(true);
  mockListResponses({
    ok: true,
    json: async () => ({ id: 1, term: 'تارىخ سۆزى', transliteration: 'Tarikh sozi', definition: 'يېڭىلانغان', letter_group: 'ت', is_ai_generated: false, aliases: [] }),
  } as Response);

  render(<HistoryDictionaryPanel />);

  await screen.findByText('تارىخ سۆزى');
  fireEvent.click(screen.getByTitle('common.edit'));

  const termInput = screen.getByPlaceholderText('admin.historyDictionary.term') as HTMLInputElement;
  expect(termInput.value).toBe('تارىخ سۆزى');
  expect(termInput).toBeDisabled();

  const definitionInput = screen.getByPlaceholderText('admin.historyDictionary.definition');
  fireEvent.change(definitionInput, { target: { value: 'يېڭىلانغان' } });
  fireEvent.click(screen.getByText('common.save'));

  await waitFor(() =>
    expect(authService.authFetch).toHaveBeenCalledWith(
      '/api/history-dictionary/1',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ transliteration: null, definition: 'يېڭىلانغان', is_ai_generated: false, aliases: [] }),
      })
    )
  );
});
