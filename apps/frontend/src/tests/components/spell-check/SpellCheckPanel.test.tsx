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
  ocr_corrections: ['the', 'thee'],
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
  onIgnoreIssue: vi.fn(),
  onNextPage: vi.fn(),
  onPrevPage: vi.fn(),
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

test('Clicking OCR suggestion calls onAddPending with correct args', async () => {
  const onAddPending = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onAddPending={onAddPending}
    />
  );
  // Click the first "the" suggestion button (desktop view uses hidden sm:flex)
  const suggestionButtons = screen.getAllByText('the');
  fireEvent.click(suggestionButtons[0]);
  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledWith(
      1,
      'the',
      'teh',
      { range: [0, 3], isAutoCorrection: false }
    );
  });
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
  const input = screen.getByPlaceholderText('spellCheck.typeCorrection');
  fireEvent.change(input, { target: { value: 'the' } });
  const applyBtn = screen.getByRole('button', { name: 'spellCheck.apply' });
  fireEvent.click(applyBtn);
  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalledWith(1, 'the', 'teh', { range: [0, 3], isAutoCorrection: false });
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
  const input = screen.getByPlaceholderText('spellCheck.typeCorrection');
  fireEvent.change(input, { target: { value: 'the' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  await waitFor(() => {
    expect(onAddPending).toHaveBeenCalled();
  });
});

test('Clicking ignore calls onIgnoreIssue', async () => {
  const onIgnoreIssue = vi.fn();
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      onIgnoreIssue={onIgnoreIssue}
    />
  );
  const ignoreBtn = screen.getByRole('button', { name: 'spellCheck.ignore' });
  fireEvent.click(ignoreBtn);
  await waitFor(() => {
    expect(onIgnoreIssue).toHaveBeenCalledWith(1);
  });
});

test('Clicking skip moves to skipped state', async () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
    />
  );
  const skipBtn = screen.getByRole('button', { name: 'spellCheck.skipLater' });
  fireEvent.click(skipBtn);
  await waitFor(() => {
    expect(screen.getByRole('button', { name: 'spellCheck.undoSkip' })).toBeInTheDocument();
  });
});

test('Issue queued in pendingIssueIds shows queued card', () => {
  render(
    <SpellCheckPanel
      {...defaultProps}
      issues={[baseIssue]}
      pendingIssueIds={[1]}
    />
  );
  expect(screen.getByText('spellCheck.queued')).toBeInTheDocument();
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
