import { ContactSubmissionsPanel } from '@/src/components/admin/ContactSubmissionsPanel';
import * as authService from '@/src/services/authService';
import { renderWithProviders } from '@/src/tests/test-utils';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/src/services/authService')>();
  return {
    ...actual,
    authFetch: vi.fn(),
    refreshAccessToken: vi.fn().mockResolvedValue(false),
    AuthService: {
      ...actual.AuthService,
      getCurrentUser: vi.fn().mockResolvedValue(null),
      logout: vi.fn(),
    },
  };
});

const sampleSubmissions = [
  {
    id: 101,
    name: 'SecTest_ContactRateLimit',
    email: 'sectest@example.com',
    interest: 'other' as const,
    message:
      'Authorized security test: verifying absence of rate limiting / CAPTCHA on public contact endpoint.',
    status: 'new' as const,
    adminNotes: null,
    reviewedBy: null,
    reviewedAt: null,
    createdAt: '2026-11-14T20:27:00Z',
  },
  {
    id: 102,
    name: 'ئەخمەت',
    email: 'ahmet@example.com',
    interest: 'editor' as const,
    message: 'مەن كىتاب تەھرىرلەشكە قاتناشماقچى ئىدىم.',
    status: 'reviewed' as const,
    adminNotes: 'Good candidate',
    reviewedBy: 'admin-1',
    reviewedAt: '2026-11-15T10:00:00Z',
    createdAt: '2026-11-13T12:00:00Z',
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

test('opens detail modal to read full contact message and updates status and notes', async () => {
  const authFetchMock = vi.spyOn(authService, 'authFetch');
  authFetchMock.mockImplementation(async (url, options) => {
    const method = options?.method || 'GET';
    if (url === '/api/contact/admin/submissions' && method === 'GET') {
      return {
        ok: true,
        json: async () => sampleSubmissions,
      } as Response;
    }
    if (url === '/api/contact/admin/submissions/101' && method === 'PATCH') {
      const body = JSON.parse(String(options?.body || '{}'));
      return {
        ok: true,
        json: async () => ({
          ...sampleSubmissions[0],
          status: body.status ?? 'archived',
          adminNotes:
            body.adminNotes !== undefined
              ? body.adminNotes
              : sampleSubmissions[0].adminNotes,
        }),
      } as Response;
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });

  renderWithProviders(<ContactSubmissionsPanel />);

  await waitFor(() => {
    expect(screen.getByText('SecTest_ContactRateLimit')).toBeInTheDocument();
  });

  // Click read message button on row 101
  fireEvent.click(
    screen.getByRole('button', {
      name: /admin\.contacts\.viewMessage.*SecTest_ContactRateLimit/,
    })
  );

  const dialog = await screen.findByRole('dialog');
  expect(
    within(dialog).getByText(/Authorized security test: verifying absence/)
  ).toBeInTheDocument();

  // Change status to archived inside modal
  fireEvent.click(
    within(dialog).getByRole('button', {
      name: 'admin.contacts.statusArchived',
    })
  );

  await waitFor(() => {
    expect(authFetchMock).toHaveBeenCalledWith(
      '/api/contact/admin/submissions/101',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ status: 'archived' }),
      })
    );
  });

  // Edit and save admin notes
  const notesInput = within(dialog).getByLabelText('admin.contacts.adminNotes');
  fireEvent.change(notesInput, { target: { value: 'PoC from Nov 14 audit' } });
  fireEvent.click(
    within(dialog).getByRole('button', { name: 'admin.contacts.saveNotes' })
  );

  await waitFor(() => {
    expect(authFetchMock).toHaveBeenCalledWith(
      '/api/contact/admin/submissions/101',
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ adminNotes: 'PoC from Nov 14 audit' }),
      })
    );
  });
});

test('deletes contact message from inside detail modal after confirmation', async () => {
  const authFetchMock = vi.spyOn(authService, 'authFetch');
  authFetchMock.mockImplementation(async (url, options) => {
    const method = options?.method || 'GET';
    if (url === '/api/contact/admin/submissions' && method === 'GET') {
      return {
        ok: true,
        json: async () => sampleSubmissions,
      } as Response;
    }
    if (url === '/api/contact/admin/submissions/101' && method === 'DELETE') {
      return {
        ok: true,
        status: 204,
        json: async () => null,
      } as Response;
    }
    throw new Error(`Unexpected request: ${method} ${url}`);
  });

  renderWithProviders(<ContactSubmissionsPanel />);

  await waitFor(() => {
    expect(screen.getByText('SecTest_ContactRateLimit')).toBeInTheDocument();
  });

  // Open detail modal by clicking message preview
  fireEvent.click(
    screen.getByText(/Authorized security test: verifying absence/)
  );

  const dialog = await screen.findByRole('dialog');

  // First click reveals inline confirmation
  fireEvent.click(
    within(dialog).getByRole('button', { name: 'common.delete' })
  );
  expect(
    within(dialog).getByText('admin.contacts.confirmDelete')
  ).toBeInTheDocument();

  // Confirm delete
  fireEvent.click(
    within(dialog).getByRole('button', { name: 'common.delete' })
  );

  await waitFor(() => {
    expect(authFetchMock).toHaveBeenCalledWith(
      '/api/contact/admin/submissions/101',
      expect.objectContaining({ method: 'DELETE' })
    );
  });

  await waitFor(() => {
    expect(
      screen.queryByText('SecTest_ContactRateLimit')
    ).not.toBeInTheDocument();
  });
});
