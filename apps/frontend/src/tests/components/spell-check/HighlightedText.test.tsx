import { screen } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { HighlightedText } from '@/src/components/spell-check/HighlightedText';
import { expect, test } from 'vitest';
import React from 'react';

const correction = {
  original: 'bad',
  corrected: 'good',
  confidence: 0.9,
  reason: 'typo',
  context: 'bad text'
};

test('HighlightedText renders plain text without corrections', () => {
  render(<HighlightedText text="plain text" corrections={[]} />);
  expect(screen.getByText('plain text')).toBeInTheDocument();
});

test.skip('HighlightedText renders highlighted segments with titles', () => {
  const { container } = render(<HighlightedText text="bad text" corrections={[correction]} />);

  const highlighted = screen.getByText('bad');
  expect(highlighted).toHaveAttribute('title', 'typo');
  expect(container.textContent).toContain('bad text');
});

test('HighlightedText supports layer mode', () => {
  const { container } = render(
    <HighlightedText text="layer text" corrections={[]} isLayer={true} />
  );

  expect(container.firstChild).toHaveClass('text-transparent');
});
