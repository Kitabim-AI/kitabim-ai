import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ShareSearchResultModal } from '../../../components/share/ShareSearchResultModal';

vi.mock('../../../i18n/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}));

describe('ShareSearchResultModal', () => {
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

  it('renders search result title, content, and X share button', () => {
    render(
      <ShareSearchResultModal
        title="Sample Entry"
        content="Sample definition content text."
        sourceLabel="Dictionary"
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('share.shareSearchResult')).toBeInTheDocument();
    expect(screen.getByText('Sample Entry')).toBeInTheDocument();
    expect(screen.getByText('share.postToX')).toBeInTheDocument();
  });

  it('triggers X Web Intent URL when Post to X is clicked', () => {
    render(
      <ShareSearchResultModal
        title="Sample Entry"
        content="Sample definition content text."
        sourceLabel="Dictionary"
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

  it('formats proverb shares without volume or page numbers', () => {
    const proverbText = 'مىڭ ئاڭلىغاندىن بىر كۆرگەن ئەلا';
    render(
      <ShareSearchResultModal
        title={proverbText}
        content=""
        onClose={onCloseMock}
      />
    );

    const xButton = screen.getByText('share.postToX');
    fireEvent.click(xButton);

    const openCall = vi.mocked(window.open).mock.calls[0][0];
    const decodedUrl = decodeURIComponent(openCall as string);

    expect(decodedUrl).toContain(proverbText);
    expect(decodedUrl).not.toContain('volume');
    expect(decodedUrl).not.toContain('page');
    expect(decodedUrl).not.toContain('بەت');
  });
});
