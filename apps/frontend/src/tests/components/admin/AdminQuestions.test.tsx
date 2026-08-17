import { AdminQuestions } from '@/src/components/admin/AdminQuestions';
import * as authService from '@/src/services/authService';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/authService', () => ({
  authFetch: vi.fn(),
}));

test('renders book title under the question for reader chat questions', async () => {
  const mockQuestions = [
    {
      id: 1,
      question: 'بۇ كىتابتا nə بار؟',
      isGlobal: false,
      bookId: 'book-123',
      bookTitle: 'ئېچىلغان بولاق',
      userId: 'user-1',
      userDisplayName: 'Ali',
      isFirstTurn: true,
      showOnHomepage: false,
      userFeedback: null,
      ts: '2026-08-16T12:00:00Z',
      evalStatus: 'completed',
      faithfulnessScore: 0.9,
      answerRelevanceScore: 0.85,
      contextPrecisionScore: 0.8,
    },
    {
      id: 2,
      question: 'ئۇيغۇرلار ھەققىدە سوئال',
      isGlobal: true,
      bookId: null,
      bookTitle: null,
      userId: null,
      userDisplayName: null,
      isFirstTurn: true,
      showOnHomepage: true,
      userFeedback: null,
      ts: '2026-08-16T11:00:00Z',
      evalStatus: 'skipped',
      faithfulnessScore: null,
      answerRelevanceScore: null,
      contextPrecisionScore: null,
    },
  ];

  vi.spyOn(authService, 'authFetch').mockResolvedValue({
    ok: true,
    json: async () => ({
      items: mockQuestions,
      total: 2,
      offset: 0,
      limit: 25,
    }),
  } as Response);

  render(<AdminQuestions />);

  await waitFor(() => {
    expect(screen.getByText('بۇ كىتابتا nə بار؟')).toBeInTheDocument();
  });

  // Book title should be rendered under reader chat question
  expect(screen.getByText('ئېچىلغان بولاق')).toBeInTheDocument();

  // Global question text rendered
  expect(screen.getByText('ئۇيغۇرلار ھەققىدە سوئال')).toBeInTheDocument();
});
