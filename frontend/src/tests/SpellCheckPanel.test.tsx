import { render, screen, fireEvent } from '@testing-library/react';
import { SpellCheckPanel, SpellCheckResult } from '../components/spell-check/SpellCheckPanel';
import { expect, test, vi } from 'vitest';
import React from 'react';

const baseResult: SpellCheckResult = {
  bookId: '1',
  pageNumber: 2,
  corrections: [],
  totalIssues: 0,
  checkedAt: 'now'
};

test('SpellCheckPanel runs spell check and shows empty state', () => {
  const onRunSpellCheck = vi.fn();
  render(
    <SpellCheckPanel
      bookId="1"
      pageNumber={2}
      pageText="Some text"
      isChecking={false}
      spellCheckResult={null}
      onRunSpellCheck={onRunSpellCheck}
      onApplyCorrection={vi.fn()}
      onIgnoreCorrection={vi.fn()}
      appliedCorrections={new Set()}
      ignoredCorrections={new Set()}
    />
  );

  const runButton = screen.getByRole('button', { name: /Run Spell Check/i });
  expect(runButton).toBeInTheDocument();
  fireEvent.click(runButton);
  expect(onRunSpellCheck).toHaveBeenCalled();
  expect(screen.getByText(/analyze this page/i)).toBeInTheDocument();
});

test('SpellCheckPanel shows no issues state', () => {
  render(
    <SpellCheckPanel
      bookId="1"
      pageNumber={2}
      pageText="Some text"
      isChecking={false}
      spellCheckResult={baseResult}
      onRunSpellCheck={vi.fn()}
      onApplyCorrection={vi.fn()}
      onIgnoreCorrection={vi.fn()}
      appliedCorrections={new Set()}
      ignoredCorrections={new Set()}
    />
  );

  expect(screen.getByText(/No spelling issues/i)).toBeInTheDocument();
});

test('SpellCheckPanel renders corrections and handles apply/ignore', () => {
  const onApplyCorrection = vi.fn();
  const onIgnoreCorrection = vi.fn();
  const result: SpellCheckResult = {
    ...baseResult,
    corrections: [
      { original: 'teh', corrected: 'the', confidence: 0.9, reason: 'typo', context: '...teh book...' }
    ],
    totalIssues: 1
  };

  render(
    <SpellCheckPanel
      bookId="1"
      pageNumber={2}
      pageText="Some text"
      isChecking={false}
      spellCheckResult={result}
      onRunSpellCheck={vi.fn()}
      onApplyCorrection={onApplyCorrection}
      onIgnoreCorrection={onIgnoreCorrection}
      appliedCorrections={new Set()}
      ignoredCorrections={new Set()}
    />
  );

  expect(screen.getByText(/1 Issue Found/i)).toBeInTheDocument();
  fireEvent.click(screen.getByText('the'));
  expect(onApplyCorrection).toHaveBeenCalled();

  fireEvent.click(screen.getByText(/Ignore/i));
  expect(onIgnoreCorrection).toHaveBeenCalled();
});

test('SpellCheckPanel shows applied/ignored footer', () => {
  render(
    <SpellCheckPanel
      bookId="1"
      pageNumber={2}
      pageText="Some text"
      isChecking={false}
      spellCheckResult={baseResult}
      onRunSpellCheck={vi.fn()}
      onApplyCorrection={vi.fn()}
      onIgnoreCorrection={vi.fn()}
      appliedCorrections={new Set(['a'])}
      ignoredCorrections={new Set(['b'])}
    />
  );

  expect(screen.getByText(/1 applied/i)).toBeInTheDocument();
  expect(screen.getByText(/1 ignored/i)).toBeInTheDocument();
});
