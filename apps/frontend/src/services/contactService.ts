/**
 * Contact form service for handling contact submission API calls.
 */
import { APP_CLIENT_ID } from '../config';

const API_BASE = '/api/contact';

export interface ContactSubmission {
  name: string;
  email: string;
  interest: 'editor' | 'developer' | 'other';
  message: string;
}

export interface ContactSubmissionResponse {
  id: number;
  status: string;
  createdAt: string;
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
  const response = await fetch(`${API_BASE}/submit`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Kitabim-App-Id': APP_CLIENT_ID,
    },
    body: JSON.stringify(submission),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    let errorMessage = 'Failed to submit contact form';
    if (errorData?.detail) {
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        errorMessage = errorData.detail.map((err: any) => err.msg).join(', ');
      }
    }
    throw new Error(errorMessage);
  }

  return response.json();
}
