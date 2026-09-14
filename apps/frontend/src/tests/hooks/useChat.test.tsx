import { useChat } from '@/src/hooks/useChat';
import { chatWithBookStream, getChatUsage } from '@/src/services/geminiService';
import { Book } from '@shared/types';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/services/geminiService', () => ({
  chatWithBook: vi.fn(),
  chatWithBookStream: vi.fn(),
  getChatUsage: vi.fn(),
  getUserConversations: vi.fn(() => Promise.resolve([])),
  getConversationMessages: vi.fn(() => Promise.resolve([])),
  deleteConversation: vi.fn(() => Promise.resolve(true)),
}));

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    isAuthenticated: true,
  })),
}));

vi.mock('../context/NotificationContext', () => ({
  useNotification: vi.fn(() => ({
    addNotification: vi.fn(),
    removeNotification: vi.fn(),
  })),
}));

vi.mock('@/src/context/NotificationContext', () => ({
  useNotification: vi.fn(() => ({
    addNotification: vi.fn(),
    removeNotification: vi.fn(),
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
  vi.mocked(chatWithBookStream).mockImplementation(async (_params, callbacks) => {
    callbacks.onChunk('AI ');
    callbacks.onChunk('Response');
    callbacks.onComplete();
  });

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  await waitFor(() => {
    expect(result.current.isLoadingMessages).toBe(false);
  });

  act(() => {
    result.current.setChatInput('سالام');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(result.current.chatMessages).toHaveLength(2);
  });

  expect(result.current.chatMessages[0].text).toBe('سالام');
  expect(result.current.chatMessages[1].text).toBe('AI Response');
  expect(chatWithBookStream).toHaveBeenCalled();
  const [params] = vi.mocked(chatWithBookStream).mock.calls[0];
  expect(params.question).toBe('سالام');
  expect(params.bookId).toBe('1');
  expect(params.currentPage).toBe(1);
});

test('useChat handles global chat', async () => {
  vi.mocked(chatWithBookStream).mockImplementation(async (_params, callbacks) => {
    callbacks.onChunk('Global Answer');
    callbacks.onComplete();
  });

  const { result } = renderHook(() => useChat('global-chat', null, null));

  act(() => {
    result.current.setChatInput('دۇنيادىكى سوئال');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(result.current.chatMessages.at(-1)?.text).toBe('Global Answer');
  });

  expect(chatWithBookStream).toHaveBeenCalled();
  const [globalParams] = vi.mocked(chatWithBookStream).mock.calls[0];
  expect(globalParams.question).toBe('دۇنيادىكى سوئال');
  expect(globalParams.bookId).toBe('global');
  expect(globalParams.currentPage).toBeUndefined();
});

test('useChat handles error state', async () => {
  vi.mocked(chatWithBookStream).mockImplementation(async (_params, callbacks) => {
    callbacks.onError('كەچۈرۈڭ، جاۋاب بېرەلمىدىم.');
  });

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  await waitFor(() => {
    expect(result.current.isLoadingMessages).toBe(false);
  });

  act(() => {
    result.current.setChatInput('سالام');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(result.current.chatMessages.at(-1)?.text).toBe('كەچۈرۈڭ، جاۋاب بېرەلمىدىم.');
  });
});

test('useChat carries the server-assigned conversationId to the next message and resets it on book switch', async () => {
  vi.mocked(chatWithBookStream).mockImplementation(async (_params, callbacks) => {
    callbacks.onConversationId?.('conv-123');
    callbacks.onChunk('Answer');
    callbacks.onComplete();
  });

  const { result, rerender } = renderHook(
    ({ book }) => useChat('reader', book, 1),
    { initialProps: { book: mockBook } }
  );

  act(() => {
    result.current.setChatInput('بىرىنچى سوئال');
  });
  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(vi.mocked(chatWithBookStream)).toHaveBeenCalledTimes(1);
  });

  act(() => {
    result.current.setChatInput('ئىككىنچى سوئال');
  });
  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(vi.mocked(chatWithBookStream)).toHaveBeenCalledTimes(2);
  });
  const [secondParams] = vi.mocked(chatWithBookStream).mock.calls[1];
  expect(secondParams.conversationId).toBe('conv-123');

  const otherBook: Book = { ...mockBook, id: '2' };
  rerender({ book: otherBook });

  act(() => {
    result.current.setChatInput('ئۈچىنچى سوئال');
  });
  await act(async () => {
    await result.current.handleSendMessage();
  });

  await waitFor(() => {
    expect(vi.mocked(chatWithBookStream)).toHaveBeenCalledTimes(3);
  });
  const [thirdParams] = vi.mocked(chatWithBookStream).mock.calls[2];
  expect(thirdParams.conversationId).toBeUndefined();
});

test('useChat loads conversation messages preserving cost and feedback', async () => {
  const { getUserConversations, getConversationMessages } = await import('@/src/services/geminiService');
  vi.mocked(getUserConversations).mockResolvedValue([
    {
      id: 'conv-test-1',
      userId: 'user-1',
      isGlobal: false,
      createdAt: '2026-09-13T00:00:00Z',
      updatedAt: '2026-09-13T00:00:00Z',
    },
  ]);
  vi.mocked(getConversationMessages).mockResolvedValue([
    {
      id: 'm1',
      conversationId: 'conv-test-1',
      role: 'user',
      content: 'سۇئال',
      createdAt: '2026-09-13T00:00:00Z',
    },
    {
      id: 'm2',
      conversationId: 'conv-test-1',
      role: 'model',
      content: 'جاۋاب',
      evalId: 42,
      cost: {
        inputTokens: 1200,
        outputTokens: 300,
        costUsd: 0.00045,
      },
      feedback: 'positive',
      createdAt: '2026-09-13T00:00:01Z',
    },
  ]);

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  await waitFor(() => {
    expect(result.current.isLoadingMessages).toBe(false);
  });

  await waitFor(() => {
    expect(result.current.chatMessages).toHaveLength(2);
  });

  const modelMsg = result.current.chatMessages[1];
  expect(modelMsg.cost).toEqual({
    inputTokens: 1200,
    outputTokens: 300,
    costUsd: 0.00045,
  });
  expect(modelMsg.feedback).toBe('positive');
  expect(modelMsg.evalId).toBe(42);
});

