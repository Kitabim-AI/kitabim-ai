import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ShareChatModal } from '../../../components/share/ShareChatModal';

vi.mock('../../../i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}));

describe('ShareChatModal', () => {
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

  it('renders Q&A modal with X (Twitter) posting button', () => {
    render(
      <ShareChatModal
        question="What is the key takeaway?"
        answer="Knowledge is power."
        bookTitle="Sample Book"
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('share.shareQA')).toBeInTheDocument();
    expect(screen.getByText('share.postToX')).toBeInTheDocument();
  });

  it('triggers X Web Intent URL when Post to X is clicked', () => {
    render(
      <ShareChatModal
        question="What is the key takeaway?"
        answer="Knowledge is power."
        bookTitle="Sample Book"
        onClose={onCloseMock}
      />
    );

    const xButton = screen.getByText('share.postToX');
    fireEvent.click(xButton);

    expect(window.open).toHaveBeenCalledWith(
      expect.stringContaining('https://x.com/intent/tweet?text='),
      '_blank',
      'noopener,noreferrer,width=550,height=420'
    );
  });
});
