import { useChat } from '@/src/hooks/useChat';
import { chatWithBookStream, getChatUsage } from '@/src/services/geminiService';
import { Book } from '@shared/types';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/geminiService', () => ({
  chatWithBook: vi.fn(),
  chatWithBookStream: vi.fn(),
  getChatUsage: vi.fn(),
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    isAuthenticated: true,
  })),
}));

const mockBook: Book = {
  id: '1',
  title: 'T',
  author: 'A',
  totalPages: 10,
  pages: [],
  status: 'ready',
  uploadDate: new Date(),
  lastUpdated: new Date(),
  contentHash: 'h',
  readCount: 0,
  hasSummary: false,
  hasGraph: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getChatUsage).mockResolvedValue({ usage: 0, limit: 10, hasReachedLimit: false });
});

test('useChat handles sending message', async () => {
  vi.mocked(chatWithBookStream).mockImplementation(
    async (_question, _bookId, _page, _history, onChunk, onComplete) => {
      onChunk('AI ');
      onChunk('Response');
      onComplete();
    }
  );

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  act(() => {
    result.current.setChatInput('Hello');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(result.current.chatMessages).toHaveLength(2);
  });

  expect(result.current.chatMessages[0].text).toBe('Hello');
  expect(result.current.chatMessages[1].text).toBe('AI Response');
  expect(chatWithBookStream).toHaveBeenCalled();
  const args = vi.mocked(chatWithBookStream).mock.calls[0];
  expect(args[0]).toBe('Hello');
  expect(args[1]).toBe('1');
  expect(args[2]).toBe(1);
});

test('useChat handles global chat', async () => {
  vi.mocked(chatWithBookStream).mockImplementation(
    async (_question, _bookId, _page, _history, onChunk, onComplete) => {
      onChunk('Global Answer');
      onComplete();
    }
  );

  const { result } = renderHook(() => useChat('global-chat', null, null));

  act(() => {
    result.current.setChatInput('Global query');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(result.current.chatMessages.at(-1)?.text).toBe('Global Answer');
  });

  expect(chatWithBookStream).toHaveBeenCalled();
  const globalArgs = vi.mocked(chatWithBookStream).mock.calls[0];
  expect(globalArgs[0]).toBe('Global query');
  expect(globalArgs[1]).toBe('global');
  expect(globalArgs[2]).toBeUndefined();
});

test('useChat handles error state', async () => {
  vi.mocked(chatWithBookStream).mockImplementation(
    async (_question, _bookId, _page, _history, _onChunk, _onComplete, onError) => {
      onError('كەچۈرۈڭ، جاۋاب بېرەلمىدىم.');
    }
  );

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  act(() => {
    result.current.setChatInput('Fail me');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(result.current.chatMessages.at(-1)?.text).toContain('جاۋاب بېرەلمىدىم');
  });
});
