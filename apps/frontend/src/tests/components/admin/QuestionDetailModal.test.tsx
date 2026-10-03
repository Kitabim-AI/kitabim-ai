import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QuestionDetailModal } from '@/src/components/admin/QuestionDetailModal';

const mockQuestion = {
  id: 1,
  question: 'ئۇيغۇر تارىخى ھەققىدە سۆزلەپ بېرىڭ',
  answer: 'بۇ ئۇيغۇر تارىخى ھەققىدىكى تەپسىلىي جاۋاب.',
  retrievedContext: 'تارىخىي ماتېرىياللار',
  isGlobal: false,
  bookId: 'book-1',
  bookTitle: 'ئۇيغۇرلار تارىخى',
  userId: 'user-1',
  userDisplayName: 'ئۆمەرجان',
  isFirstTurn: true,
  showOnHomepage: false,
  userFeedback: 'positive',
  ts: '2026-08-16T12:00:00Z',
  evalStatus: 'completed',
  faithfulnessScore: 0.95,
  answerRelevanceScore: 0.9,
  contextPrecisionScore: 0.88,
  inputTokens: 1200,
  outputTokens: 400,
  costUsd: 0.0025,
};

describe('QuestionDetailModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders question, answer, book title, and user info', () => {
    render(<QuestionDetailModal question={mockQuestion} onClose={vi.fn()} />);

    expect(screen.getByText('ئۇيغۇر تارىخى ھەققىدە سۆزلەپ بېرىڭ')).toBeInTheDocument();
    expect(screen.getByText('بۇ ئۇيغۇر تارىخى ھەققىدىكى تەپسىلىي جاۋاب.')).toBeInTheDocument();
    expect(screen.getByText(/ئۇيغۇرلار تارىخى/)).toBeInTheDocument();
    expect(screen.getByText('ئۆمەرجان')).toBeInTheDocument();
  });

  it('renders fallback when answer is missing', () => {
    const questionWithoutAnswer = {
      ...mockQuestion,
      answer: null,
    };
    render(<QuestionDetailModal question={questionWithoutAnswer} onClose={vi.fn()} />);

    expect(screen.getByText('admin.questions.noAnswer')).toBeInTheDocument();
  });

  it('calls onClose when close button or backdrop is clicked', () => {
    const onClose = vi.fn();
    render(<QuestionDetailModal question={mockQuestion} onClose={onClose} />);

    // Click close icon button
    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);

    // Click backdrop
    const backdrop = document.querySelector('.modal-backdrop');
    if (backdrop) {
      fireEvent.click(backdrop);
      expect(onClose).toHaveBeenCalledTimes(2);
    }
  });

  it('copies answer to clipboard when copy button is clicked', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(<QuestionDetailModal question={mockQuestion} onClose={vi.fn()} />);

    const copyBtn = screen.getByTitle('admin.questions.copyAnswer');
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith('بۇ ئۇيغۇر تارىخى ھەققىدىكى تەپسىلىي جاۋاب.');
  });

  it('calls onToggleHomepage when toggle button is clicked', () => {
    const onToggleHomepage = vi.fn();
    render(
      <QuestionDetailModal
        question={mockQuestion}
        onClose={vi.fn()}
        onToggleHomepage={onToggleHomepage}
      />
    );

    const toggleBtn = screen.getByRole('button', { name: 'admin.questions.showOnHome' });
    fireEvent.click(toggleBtn);

    expect(onToggleHomepage).toHaveBeenCalledWith(mockQuestion);
  });
});
