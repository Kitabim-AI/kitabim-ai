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

  it('strips reference IDs like (ref:...) from answer text and sends full text when sharing to X', () => {
    render(
      <ShareChatModal
        question="باشقىچە پىكىر بارمۇ؟"
        answer="ئەلۋەتتە **مەنبە:** [باھادىرنامە](ref:427a5621d325:summary)"
        onClose={onCloseMock}
      />
    );

    const xButton = screen.getByText('share.postToX');
    fireEvent.click(xButton);

    const calledUrl = (window.open as any).mock.calls[0][0];
    expect(calledUrl).not.toContain('ref:427a5621d325');
    expect(calledUrl).toContain(encodeURIComponent('سوئال: باشقىچە پىكىر بارمۇ؟'));
    expect(calledUrl).toContain(encodeURIComponent('باھادىرنامە'));
  });

  it('copies full Q&A content to clipboard when Copy Content button is clicked', async () => {
    render(
      <ShareChatModal
        question="What is the key takeaway?"
        answer="Knowledge is power."
        bookTitle="Sample Book"
        onClose={onCloseMock}
      />
    );

    const copyButton = screen.getByText('share.copyContent');
    fireEvent.click(copyButton);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining('Knowledge is power.')
    );
  });
});
