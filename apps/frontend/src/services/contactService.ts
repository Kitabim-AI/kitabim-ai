/**
 * Contact form service for handling contact submission API calls.
 */
import { authFetch } from './authService';

const API_BASE = '/api/contact';

export type ContactInterest = 'editor' | 'developer' | 'other';
export type ContactStatus = 'new' | 'reviewed' | 'contacted' | 'archived';

export interface ContactSubmission {
  name: string;
  email: string;
  interest: ContactInterest;
  message: string;
}

export interface ContactSubmissionResponse {
  id: number;
  status: string;
  createdAt: string;
}

export interface ContactSubmissionAdminItem {
  id: number;
  name: string;
  email: string;
  interest: ContactInterest;
  message: string;
  status: ContactStatus;
  adminNotes?: string | null;
  reviewedBy?: string | null;
  reviewedAt?: string | null;
  createdAt: string;
}

export interface ContactSubmissionUpdatePayload {
  status?: ContactStatus;
  adminNotes?: string | null;
}

function extractErrorMessage(errorData: any, fallback: string): string {
  if (errorData?.detail) {
    if (typeof errorData.detail === 'string') {
      return errorData.detail;
    }
    if (Array.isArray(errorData.detail)) {
      return errorData.detail.map((err: any) => err.msg).join(', ');
    }
  }
  return fallback;
}

/**
 * Submit a contact form from the Join Us page.
 *
 * @param submission - Contact form data
 * @returns Promise with submission response
 * @throws Error if submission fails
 */
export async function submitContactForm(
  submission: ContactSubmission
): Promise<ContactSubmissionResponse> {
  const response = await authFetch(`${API_BASE}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(submission),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(errorData, 'Failed to submit contact form'));
  }

  return response.json();
}

/**
 * Fetch contact submissions for admin panel.
 */
export async function getAdminContactSubmissions(
  status?: ContactStatus
): Promise<ContactSubmissionAdminItem[]> {
  const queryParams = status ? `?status=${encodeURIComponent(status)}` : '';
  const response = await authFetch(`${API_BASE}/admin/submissions${queryParams}`);

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(errorData, 'Failed to fetch submissions'));
  }

  return response.json();
}

/**
 * Update status and/or admin notes of a contact submission (Admin-only).
 */
export async function updateAdminContactSubmission(
  id: number,
  payload: ContactSubmissionUpdatePayload
): Promise<ContactSubmissionAdminItem> {
  const response = await authFetch(`${API_BASE}/admin/submissions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(errorData, 'Failed to update submission'));
  }

  return response.json();
}

/**
 * Delete a contact submission (Admin-only).
 */
export async function deleteAdminContactSubmission(id: number): Promise<void> {
  const response = await authFetch(`${API_BASE}/admin/submissions/${id}`, {
    method: 'DELETE',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    throw new Error(extractErrorMessage(errorData, 'Failed to delete submission'));
  }
}
