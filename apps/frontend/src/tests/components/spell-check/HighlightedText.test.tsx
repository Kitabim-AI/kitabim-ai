import { screen } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { HighlightedText } from '@/src/components/spell-check/HighlightedText';
import { expect, test } from 'vitest';
import React from 'react';

const issue = {
  id: 1,
  word: 'bad',
  char_offset: 0,
  char_end: 3,
  ocr_corrections: ['good'],
  status: 'open' as const,
};

test('HighlightedText renders plain text without corrections', () => {
  render(<HighlightedText text="plain text" issues={[]} />);
  expect(screen.getByText('plain text')).toBeInTheDocument();
});

test('HighlightedText renders highlighted segments with titles', () => {
  const { container } = render(<HighlightedText text="bad text" issues={[issue]} />);

  const highlighted = screen.getByText('bad');
  expect(highlighted).toHaveAttribute('title', 'bad');
  expect(container.textContent).toContain('bad text');
});

test('HighlightedText supports layer mode', () => {
  const { container } = render(
    <HighlightedText text="layer text" issues={[]} isLayer={true} />
  );

  expect(container.firstChild).toHaveClass('text-transparent');
});
