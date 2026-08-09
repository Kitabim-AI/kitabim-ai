import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MarkdownContent } from '@/src/components/common/MarkdownContent';

describe('MarkdownContent Table of Contents hyperlinks', () => {
  const tocContent = `
مۇقەددىمە ................................................ 5
1-باپ: كىرىش سۆز ......................... 12
`;

  it('renders TOC items as clickable hyperlinks when contentPageOffset is set (> 0)', () => {
    const onTocPageClick = vi.fn();
    render(
      <MarkdownContent
        content={tocContent}
        contentPageOffset={10}
        onTocPageClick={onTocPageClick}
      />
    );

    const firstTocItem = screen.getByRole('button', { name: /مۇقەددىمە/ });
    expect(firstTocItem).toBeInTheDocument();

    const secondTocItem = screen.getByRole('button', { name: /1-باپ/ });
    expect(secondTocItem).toBeInTheDocument();

    // Click on second TOC item (content page 12 + offset 10 = physical page 22)
    fireEvent.click(secondTocItem);
    expect(onTocPageClick).toHaveBeenCalledWith(22);
  });

  it('renders TOC items as plain text when contentPageOffset is not set (0 or undefined)', () => {
    const onTocPageClick = vi.fn();
    render(
      <MarkdownContent
        content={tocContent}
        contentPageOffset={0}
        onTocPageClick={onTocPageClick}
      />
    );

    // Should NOT render buttons for TOC lines when offset is 0
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/مۇقەددىمە/)).toBeInTheDocument();
  });

  it('renders bullet-prefixed and number-prefixed TOC entries as hyperlinks', () => {
    const onTocPageClick = vi.fn();
    const bulletContent = `
* جۇنۇپ ئادەمنىڭ «قۇرئان كەرىم»نى تۇتۇشى ............................................. 301
* 380 مۇناپىقلار بىلەن يەھۇدىيلارنىڭ رەزىللىكى
- 463 ................................................................................... ئىددەت نېمە ئۈچۈن بۇيرۇلغان؟
`;
    render(
      <MarkdownContent
        content={bulletContent}
        contentPageOffset={10}
        onTocPageClick={onTocPageClick}
      />
    );

    const item1 = screen.getByRole('button', { name: /جۇنۇپ ئادەمنىڭ/ });
    expect(item1).toBeInTheDocument();
    fireEvent.click(item1);
    expect(onTocPageClick).toHaveBeenLastCalledWith(311);

    const item2 = screen.getByRole('button', { name: /مۇناپىقلار/ });
    expect(item2).toBeInTheDocument();
    fireEvent.click(item2);
    expect(onTocPageClick).toHaveBeenLastCalledWith(390);

    const item3 = screen.getByRole('button', { name: /ئىددەت/ });
    expect(item3).toBeInTheDocument();
    fireEvent.click(item3);
    expect(onTocPageClick).toHaveBeenLastCalledWith(473);
  });

  it('renders markdown table TOC rows as clickable hyperlinked rows when offset is set', () => {
    const onTocPageClick = vi.fn();
    const tableTocContent = `
# مۇندەرىجە

| ئەلچى قۇش ھېكايىسى | 1 |
| ئەخمەق كەكلىكنىڭ ھېكايىسى | 5 |
`;
    render(
      <MarkdownContent
        content={tableTocContent}
        contentPageOffset={10}
        onTocPageClick={onTocPageClick}
      />
    );

    const firstRowText = screen.getByText('ئەلچى قۇش ھېكايىسى');
    expect(firstRowText).toBeInTheDocument();

    const rowTr = firstRowText.closest('tr');
    expect(rowTr).not.toBeNull();
    expect(rowTr?.className).toContain('cursor-pointer');

    // Click table row (content page 1 + offset 10 = physical page 11)
    fireEvent.click(rowTr!);
    expect(onTocPageClick).toHaveBeenCalledWith(11);
  });
});

