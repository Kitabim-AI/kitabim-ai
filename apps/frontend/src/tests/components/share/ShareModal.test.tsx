import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ShareModal } from '../../../components/share/ShareModal';
import { Book } from '@shared/types';

vi.mock('../../../i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}));

const mockBook = {
  id: 'book-123',
  title: 'Test Book Title',
  author: 'Test Author',
  volume: 1,
  coverUrl: 'https://example.com/cover.jpg',
} as unknown as Book;

describe('ShareModal', () => {
  const onCloseMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('open', vi.fn());
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('renders book title and share buttons including X (Twitter)', () => {
    render(<ShareModal book={mockBook} onClose={onCloseMock} />);

    expect(screen.getByText('share.shareBook')).toBeInTheDocument();
    expect(screen.getByText('share.copyLink')).toBeInTheDocument();
    expect(screen.getByText('share.postToX')).toBeInTheDocument();
    expect(screen.getByText('share.postToFacebook')).toBeInTheDocument();
  });

  it('opens X Web Intent URL when Post to X is clicked', () => {
    render(<ShareModal book={mockBook} onClose={onCloseMock} />);

    const xButton = screen.getByText('share.postToX');
    fireEvent.click(xButton);

    expect(window.open).toHaveBeenCalledWith(
      expect.stringContaining('https://x.com/intent/tweet?text='),
      '_blank',
      'noopener,noreferrer,width=550,height=420'
    );
  });
});
