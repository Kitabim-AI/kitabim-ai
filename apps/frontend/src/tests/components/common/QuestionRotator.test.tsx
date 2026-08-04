import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuestionRotator } from '../../../components/common/QuestionRotator';
import { PersistenceService } from '../../../services/persistenceService';

vi.mock('../../../i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => (key === 'home.recentQuestions' ? 'ئەڭ يېڭى جاۋاب بېرىلگەن سۇئاللار' : key),
  }),
}));

vi.mock('../../../services/persistenceService', () => ({
  PersistenceService: {
    getFeaturedQuestions: vi.fn(),
  },
}));

describe('QuestionRotator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches latest 20 featured questions and displays title and first question', async () => {
    const mockQuestions = [
      'ئەڭ يېڭى سوئال 1',
      'ئەڭ يېڭى سوئال 2',
      'ئەڭ يېڭى سوئال 3',
    ];
    (PersistenceService.getFeaturedQuestions as any).mockResolvedValue(mockQuestions);

    render(<QuestionRotator />);

    expect(PersistenceService.getFeaturedQuestions).toHaveBeenCalledWith(20);

    await waitFor(() => {
      expect(screen.getByText('ئەڭ يېڭى جاۋاب بېرىلگەن سوئاللار')).toBeInTheDocument();
      expect(screen.getByText('ئەڭ يېڭى سوئال 1')).toBeInTheDocument();
    });
  });
});
