import { renderHook, act } from '@testing-library/react';
import { useChat } from '@/src/hooks/useChat';
import { chatWithBook } from '@/src/services/geminiService';
import { expect, test, vi, beforeEach } from 'vitest';
import { Book } from '@shared/types';

vi.mock('@/src/services/geminiService', () => ({
  chatWithBook: vi.fn()
}));

const mockBook: Book = {
  id: '1', title: 'T', author: 'A', totalPages: 10, pages: [], status: 'ready', uploadDate: new Date(), lastUpdated: new Date(), contentHash: 'h'
};

beforeEach(() => {
  vi.clearAllMocks();
});

test.skip('useChat handles sending message', async () => {
  (chatWithBook as any).mockResolvedValue('AI Response');

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  act(() => {
    result.current.setChatInput('Hello');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  expect(result.current.chatMessages).toHaveLength(2);
  expect(result.current.chatMessages[1].text).toBe('AI Response');
  expect(chatWithBook).toHaveBeenCalledWith('Hello', '1', 1, expect.any(Array));
});

test.skip('useChat handles global chat', async () => {
  (chatWithBook as any).mockResolvedValue('Global Answer');

  const { result } = renderHook(() => useChat('global-chat', null, null));

  act(() => {
    result.current.setChatInput('Global query');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  expect(chatWithBook).toHaveBeenCalledWith('Global query', 'global', undefined, expect.any(Array));
});

test.skip('useChat handles error state', async () => {
  (chatWithBook as any).mockRejectedValue(new Error('Fail'));

  const { result } = renderHook(() => useChat('reader', mockBook, 1));

  act(() => {
    result.current.setChatInput('Fail me');
  });

  await act(async () => {
    await result.current.handleSendMessage();
  });

  expect(result.current.chatMessages[1].text).toContain('جاۋاب بېرەلمىدىم');
});
