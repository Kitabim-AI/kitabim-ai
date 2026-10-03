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

  it('does NOT render hyperlinks on non-TOC pages (such as copyright/CIP catalog text) even when contentPageOffset is set', () => {
    const onTocPageClick = vi.fn();
    const cipContent = `
(CIP) كىتابلارنىڭ نەشرىياتتىن بۇرۇنقى تىزىملەش ماتېرىيالى
I. ها ... II. زە ... III. ئو ... - roman - لۇئان — يېقىنقى زامان IV. I378.44
2000-يىل 7-ئاي 1-نەشىر، 2000-يىل 7-ئاي 1-بېسىلىشى بېسىلىش سانى: 1 4060 —
`;
    render(
      <MarkdownContent
        content={cipContent}
        contentPageOffset={10}
        onTocPageClick={onTocPageClick}
      />
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/ماتېرىيالى/)).toBeInTheDocument();
  });

  it('does NOT render hyperlinks when isTocPage is explicitly false', () => {
    const onTocPageClick = vi.fn();
    render(
      <MarkdownContent
        content={tocContent}
        contentPageOffset={10}
        isTocPage={false}
        onTocPageClick={onTocPageClick}
      />
    );

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/مۇقەددىمە/)).toBeInTheDocument();
  });

  it('renders hyperlinks when isTocPage is explicitly true', () => {
    const onTocPageClick = vi.fn();
    render(
      <MarkdownContent
        content={tocContent}
        contentPageOffset={10}
        isTocPage={true}
        onTocPageClick={onTocPageClick}
      />
    );

    expect(screen.getByRole('button', { name: /مۇقەددىمە/ })).toBeInTheDocument();
  });

  it('correctly extracts page number 28 instead of section number 9 from table row "| 9 . قېرىنداش ۋە ئويۇن | 28 |"', () => {
    const onTocPageClick = vi.fn();
    const sectionPrefixedTableToc = `
# مۇندەرىجە

| 9 . قېرىنداش ۋە ئويۇن | 28 |
`;
    render(
      <MarkdownContent
        content={sectionPrefixedTableToc}
        contentPageOffset={10}
        onTocPageClick={onTocPageClick}
      />
    );

    const rowText = screen.getByText(/قېرىنداش ۋە ئويۇن/);
    expect(rowText).toBeInTheDocument();

    const rowTr = rowText.closest('tr');
    expect(rowTr).not.toBeNull();
    fireEvent.click(rowTr!);

    // Should navigate to page 28 + 10 (offset) = 38, NOT 9 + 10 = 19
    expect(onTocPageClick).toHaveBeenCalledWith(38);
  });
});

describe('MarkdownContent numbered entries and ordered lists', () => {
  it('preserves couplet numbers like 6047 and 6048 without converting them to 1', () => {
    const qutadghuBilikPage = `
6047. ئودغۇرمىش جاۋاب بېرىپ دېدى: بۇ چۈشۈمنىڭ
تەبىرى مۇنداق ئەمەس، ئەي تەڭتۇش دوستۇم.

6048. بۇ چۈشنى سەن ئۇخلىغاندا كۆرگەن بولساڭ،
تەبىرى سەن ئېيتقاندەك ئوڭۇشلۇق بولغان بولاتتى.
`;
    const { container } = render(<MarkdownContent content={qutadghuBilikPage} />);

    // Should NOT have any ordered list elements (<ol>)
    expect(container.querySelector('ol')).toBeNull();

    // The text content should contain the original numbers 6047 and 6048
    expect(screen.getByText(/6047/)).toBeInTheDocument();
    expect(screen.getByText(/6048/)).toBeInTheDocument();

    // The couplet lines should be together
    expect(screen.getByText(/ئودغۇرمىش جاۋاب بېرىپ دېدى/)).toBeInTheDocument();
    expect(screen.getByText(/تەبىرى مۇنداق ئەمەس/)).toBeInTheDocument();
  });

  it('renders real consecutive numbered lists as <ol> with correct start attribute', () => {
    const listContent = `
1. بىرىنچى تاللاش
2. ئىككىنچى تاللاش
3. ئۈچىنچى تاللاش
`;
    const { container } = render(<MarkdownContent content={listContent} />);

    const ol = container.querySelector('ol');
    expect(ol).not.toBeNull();
    expect(ol?.getAttribute('start')).toBe('1');
    const items = container.querySelectorAll('li');
    expect(items).toHaveLength(3);
    expect(items[0].textContent).toContain('بىرىنچى تاللاش');
    expect(items[1].textContent).toContain('ئىككىنچى تاللاش');
    expect(items[2].textContent).toContain('ئۈچىنچى تاللاش');
  });

  it('renders ordered list starting at a number other than 1 with start attribute', () => {
    const listContent = `
4. تۆتىنچى نۇقتا
5. بەشىنچى نۇقتا
`;
    const { container } = render(<MarkdownContent content={listContent} />);

    const ol = container.querySelector('ol');
    expect(ol).not.toBeNull();
    expect(ol?.getAttribute('start')).toBe('4');
    const items = container.querySelectorAll('li');
    expect(items).toHaveLength(2);
    expect(items[0].textContent).toContain('تۆتىنچى نۇقتا');
    expect(items[1].textContent).toContain('بەشىنچى نۇقتا');
  });

  it('does NOT convert years at start of sentence to <ol>', () => {
    const yearText = `1949. يىلى شىنجاڭدا بىر مەكتەپ قۇرۇلدى.`;
    const { container } = render(<MarkdownContent content={yearText} />);

    expect(container.querySelector('ol')).toBeNull();
    expect(screen.getByText(/1949/)).toBeInTheDocument();
  });

  it('does NOT convert single chapter title followed by text to <ol>', () => {
    const chapterText = `
1. باب: كىرىش سۆز
بۇ بابتا كىتاب مەزمۇنى بايان قىلىنىدۇ.
`;
    const { container } = render(<MarkdownContent content={chapterText} />);

    expect(container.querySelector('ol')).toBeNull();
    expect(screen.getByText(/1\. باب/)).toBeInTheDocument();
  });

  it('correctly renders Page 40 of Qutadghu Bilik (couplets 1 to 7) without converting them to <ol>', () => {
    const page40Content = `## B

### (نەزمىي مۇقەددىمە)

1 . ئۇ قۇدرەتلىك، بىرلا خۇدا ھەممىدىن ئىلگىرىدۇر،
بارلىق شۈكۈر، مەدھىيلەر ئۇنىڭغىلا مەنسۇپتۇر.

2 . (ئۇ) ئۇلۇغلۇق ئىگىسى، قادىر ۋە زۇل جالال * ، 
ياراتقان، تۆرەلدۈرگەن، قادىر (ۋە) كامىلدۇر.

3 . يەر، كۆك بىلەن خالايىقنىڭ ئىگىسى (ھەممە ئۈچۈن) 
رىزقىنىمۇ تەييارلىدى، كۈلۈپ تۇرۇپ يېگىن.

4 . (خۇدا) ھەممىگە ھېسابسىز رىزىق بەرگۈچىدۇر، 
ھەممىنى يېگۈزىدۇ، (لېكىن) ئۆزى يېمەيدۇ.

5 . ھەممە جانلىقلارنى ھەرگىز ئاچ قويمايدۇ، 
ئىلكىدىكى ھەممىنى يېگۈزىدۇ، ئىچكۈزىدۇ.

6 . (ئۇ) قانداق خالىغان بولسا، ھەممە (نەرسە) شۇنداق بولدى. 
كىمنى خالىسا، (شۇنى) ئۇلۇغ قىلىدۇ.

7 . (ئاللا) تاللىغان پەيغەمبەرگە مەدھىيە ۋە سالام (بولسۇن)، 
يەنە ھەمراھلىرىغا داۋاملىق سالام – ئېھتىرام (بولسۇن).`;

    const { container } = render(<MarkdownContent content={page40Content} />);

    // No <ol> elements should be rendered
    expect(container.querySelector('ol')).toBeNull();

    // Headings
    expect(screen.getByRole('heading', { level: 2, name: 'B' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: '(نەزمىي مۇقەددىمە)' })).toBeInTheDocument();

    // Couplet numbers 1 through 7 must be preserved in text
    for (let c = 1; c <= 7; c++) {
      expect(screen.getByText(new RegExp(`${c}\\s*\\.`))).toBeInTheDocument();
    }
  });

  it('correctly renders Page 41 of Qutadghu Bilik (couplets 8 to 17) preserving numbers 8-17 instead of showing 1', () => {
    const page41Content = `8. مۇھەممەد پەيغەمبەر – خالايىقنىڭ باشچىسى،
(ئۇ) ھەممە (كىشىلەر)نىڭ كۆز ۋە قېشى.

9. يەنە، بۇ بەك ئەزىز بىر كىتابتۇر،
بىلگەنلەر ئۈچۈن بىلىم دېڭىزىدۇر.

10. (بۇ) قىممەتلىك بىلىملەر بىلەن بېزەلگەن،
شۇنداق ئىكەن، شۇكۈر قىل، قانائەت تىلە.

11. (كىتابنىڭ) ھەممە يېرىگە دانىشمەنلەر سۆزلىرىنىڭ
بارچىسى ئۈنچىدەك تەپتەكشى تىزىلغان.

12. شەرق پادىشاھى، ماچىنلار بېگى،
دۇنيادىكى بىلىملىك، ئىدراكلىق ياخشىلار –

13. بارلىقى بۇ كىتابنى (قولغا) ئېلىپ ئۆزلەشتۈرگەن،
خەزىنە ئىچىدە ساقلاپ، ئاسرىغان.

14. بىرىدىن – بىرىگە مىراس بولۇپ قالغان،
ئۆزى تۇتۇپ، باشقىلارغا بەرمىگەن.

15. بۇ (كىتاب) پايدىلىقتۇركى، ھېچ زىيىنى يوق،
كۆپلىگەن تۈركلەر بۇنىڭ مەنىسىنى چۈشەنمەيدۇ.

16. كىتابنى چۈشەنگەنلەرلا (مەزمۇنىنى) بىلەلەيدۇ،
ئوقۇغان، يازالايدىغان (ساۋاتلىق) بولسىلا چۈشەنمەيدۇ.

17. بۇ كىتابنىڭ سۆزلىرى قول ۋە كۆز (بولۇپ يول كۆرسىتىدۇ)،`;

    const { container } = render(<MarkdownContent content={page41Content} />);

    // No <ol> elements should be rendered (was previously rendering 10 separate <ol> lists all starting at 1)
    expect(container.querySelector('ol')).toBeNull();

    // Couplet numbers 8 through 17 must be preserved in text and NOT rendered as 1
    for (let c = 8; c <= 17; c++) {
      expect(screen.getByText(new RegExp(`${c}\\.`))).toBeInTheDocument();
    }
  });
});

