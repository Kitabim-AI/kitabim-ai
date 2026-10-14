import { SpellCheckPanel } from '@/src/components/spell-check/SpellCheckPanel';
import { SpellIssue } from '@/src/hooks/useSpellCheck';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

// Mocks removed; rely on renderWithProviders

const baseIssue: SpellIssue = {
  id: 1,
  word: 'teh',
  char_offset: 0,
  char_end: 3,
  ocr_corrections: [
    { word: 'the', confidence: 0.8 },
    { word: 'thee', confidence: 0.5 },
  ],
  status: 'open',
};

const defaultProps = {
  pageNumber: 2,
  totalPages: 10,
  pageText: 'teh quick brown fox',
  fontSize: 16,
  issues: [] as SpellIssue[],
  isLoading: false,
  isScanning: false,
  hasLoaded: true,
  navigationMode: 'manual' as const,
  onUpdatePageText: vi.fn().mockResolvedValue(true),
  onAddPending: vi.fn(),
  pendingIssueIds: [] as number[],
  onRemoveFromPending: vi.fn(),
  onNextPage: vi.fn(),
  onPrevPage: vi.fn(),
  skippedIds: [] as number[],
  onToggleSkip: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

test('SpellCheckPanel shows spinner when loading before first load', () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      isLoading={true}
      hasLoaded={false}
    />
  );
  // Loading spinner renders; no issue cards
  expect(screen.queryByText('teh')).not.toBeInTheDocument();
});

test('SpellCheckPanel shows nothing when no issues and hasLoaded', () => {
  render(<SpellCheckPanel {...defaultProps} issues={[]} hasLoaded={true} />);
  // No issue cards; page header should show
  expect(screen.queryByText('teh')).not.toBeInTheDocument();
});

test('SpellCheckPanel renders active issue with OCR suggestions', () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      hasLoaded={true}
    />
  );
  // OCR suggestion buttons should be visible
  const buttons = screen.getAllByText('the');
  expect(buttons.length).toBeGreaterThan(0);
  expect(screen.getAllByText('thee').length).toBeGreaterThan(0);
});

const suggestionButton = (word: string) => {
  // The word sits in a <span> inside the suggestion <button>.
  const button = screen.getByText(word).closest('button');
  if (!button) throw new Error(`no suggestion button for ${word}`);
  return button;
};

test('Clicking an OCR suggestion applies that suggestion', async () => {
  const onAddPending = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onAddPending={onAddPending}
    />
  );

  fireEvent.click(suggestionButton('the'));

  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledWith(1, 'the', 'teh', { range: [0, 3] });
  });
});

test('Clicking a second suggestion applies that one, not the previous word', async () => {
  // Regression: the suggestion click used to set the custom input and then
  // apply the input's *previous* value (React state isn't updated yet), so
  // the first click did nothing and the next click applied the wrong word.
  const onAddPending = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onAddPending={onAddPending}
    />
  );

  fireEvent.click(suggestionButton('thee'));

  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledTimes(1);
  });
  expect(onAddPending).toHaveBeenCalledWith(1, 'thee', 'teh', { range: [0, 3] });
});

test('Custom input calls onAddPending on apply button click', async () => {
  const onAddPending = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onAddPending={onAddPending}
    />
  );
  // The placeholder is only shown when there are no OCR suggestions.
  const input = screen.getByRole('textbox');
  fireEvent.change(input, { target: { value: 'tea' } });
  fireEvent.click(screen.getByRole('button', { name: 'spellCheck.apply' }));
  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledWith(1, 'tea', 'teh', { range: [0, 3] });
  });
});

test('Custom input calls onAddPending on Enter key', async () => {
  const onAddPending = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onAddPending={onAddPending}
    />
  );
  const input = screen.getByRole('textbox');
  fireEvent.change(input, { target: { value: 'tea' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledWith(1, 'tea', 'teh', { range: [0, 3] });
  });
});

test('Custom input shows a placeholder when there are no OCR suggestions', () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[{ ...baseIssue, ocr_corrections: [] }]}
    />
  );
  expect(screen.getByPlaceholderText('spellCheck.typeCorrection')).toBeInTheDocument();
});

test('Accept original queues the word unchanged as an ignore', async () => {
  const onAddPending = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onAddPending={onAddPending}
    />
  );
  fireEvent.click(screen.getByRole('button', { name: 'spellCheck.acceptOriginal' }));
  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledWith(1, 'teh', 'teh', { isIgnore: true });
  });
});

test('A skipped issue shows the skipping card instead of the review controls', () => {
  // Skips (and their undo) are managed in ReviewPanel; the panel only shows a
  // transient card until it advances past the skipped issue.
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      skippedIds={[1]}
    />
  );
  expect(screen.getByText('spellCheck.skipping')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'spellCheck.apply' })).not.toBeInTheDocument();
});

test('An issue already queued in pendingIssueIds shows the applying card', () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      pendingIssueIds={[1]}
    />
  );
  expect(screen.getByText('spellCheck.applying')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'spellCheck.apply' })).not.toBeInTheDocument();
});

test('View page button opens page modal with full page text', async () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      pageText="teh quick brown fox"
    />
  );
  const viewPageButtons = screen.getAllByRole('button', { name: /spellCheck\.viewPage/i });
  fireEvent.click(viewPageButtons[0]);
  await waitFor(() => {
    expect(screen.getByText('teh quick brown fox')).toBeInTheDocument();
  });
  expect(screen.getByRole('button', { name: 'common.close' })).toBeInTheDocument();
});
