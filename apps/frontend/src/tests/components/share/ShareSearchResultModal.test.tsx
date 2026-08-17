import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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

  // Extracts the `text` (or `u`) query param via the URL API instead of manually
  // decodeURIComponent-ing the whole string — this content embeds an already-encoded
  // URL (the deep link's own ?quote= param), so a single blind decode of the outer
  // string leaves that inner encoding intact; parsing per-param avoids reasoning
  // about how many encoding layers are actually being unwound.
  const getOpenedQueryParam = (paramName: string): string => {
    const openCall = vi.mocked(window.open).mock.calls[0][0] as string;
    return new URL(openCall).searchParams.get(paramName) || '';
  };

  it('renders the page-share header label and deep link when bookId/pageNumber are given', () => {
    render(
      <ShareSearchResultModal
        title="My Book"
        content="Page text content here."
        bookId="book-1"
        pageNumber={5}
        variant="page"
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('share.sharePage')).toBeInTheDocument();

    fireEvent.click(screen.getByText('share.postToX'));
    const tweetText = getOpenedQueryParam('text');
    expect(tweetText).toContain(`${window.location.origin}/books/book-1/5`);
    expect(tweetText).not.toContain('quote=');
  });

  it('renders the quote-share header label and includes the quote query param when quote is given', () => {
    render(
      <ShareSearchResultModal
        title="My Book"
        content="a highlighted quote"
        bookId="book-1"
        pageNumber={5}
        quote="a highlighted quote"
        variant="quote"
        onClose={onCloseMock}
      />
    );

    expect(screen.getByText('share.shareQuote')).toBeInTheDocument();

    fireEvent.click(screen.getByText('share.postToX'));
    const tweetText = getOpenedQueryParam('text');
    expect(tweetText).toContain(
      `${window.location.origin}/books/book-1/5?quote=${encodeURIComponent('a highlighted quote')}`
    );
  });

  it('uses the /api/share/page OG-preview URL (not the plain deep link) for the Facebook sharer', async () => {
    render(
      <ShareSearchResultModal
        title="My Book"
        content="Page text content here."
        bookId="book-1"
        pageNumber={5}
        variant="page"
        onClose={onCloseMock}
      />
    );

    fireEvent.click(screen.getByText('share.postToFacebook'));
    await waitFor(() => expect(window.open).toHaveBeenCalled());
    expect(getOpenedQueryParam('u')).toBe(`${window.location.origin}/api/share/page/book-1/5`);
  });

  it('falls back to the plain url prop when bookId/pageNumber are not given (existing callers unaffected)', () => {
    render(
      <ShareSearchResultModal
        title="Dictionary Entry"
        content="definition text"
        url="https://kitabim.ai/dictionary/entry-1"
        onClose={onCloseMock}
      />
    );

    fireEvent.click(screen.getByText('share.postToX'));
    const tweetText = getOpenedQueryParam('text');
    expect(tweetText).toContain('https://kitabim.ai/dictionary/entry-1');
  });
});
