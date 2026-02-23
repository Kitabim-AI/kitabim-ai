import { useState, useRef, useEffect } from 'react';
import { Message, Book } from '@shared/types';
import { chatWithBook, chatWithBookStream, getChatUsage } from '../services/geminiService';
import { useAuth } from './useAuth';

export const useChat = (view: string, selectedBook: Book | null, currentPage: number | null) => {
  const { isAuthenticated } = useAuth();
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatting, setIsChatting] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState('');
  const streamingMessageRef = useRef('');
  const [usageStatus, setUsageStatus] = useState<{ usage: number, limit: number | null, hasReachedLimit: boolean } | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    streamingMessageRef.current = streamingMessage;
  }, [streamingMessage]);

  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, isChatting, view, streamingMessage]);

  // Fetch usage status on mount and when chatting status changes
  useEffect(() => {
    if (isAuthenticated) {
      if (!isChatting && !streamingMessage) {
        getChatUsage().then(setUsageStatus);
      }
    } else {
      setUsageStatus(null);
    }
  }, [isAuthenticated, chatMessages, isChatting, streamingMessage]);

  const abortOngoingChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsChatting(false);
    setStreamingMessage('');
  };

  // Terminate chat if context changes (view, book, or page unmounts/switches)
  useEffect(() => {
    abortOngoingChat();
    // Also clear messages if we switch major views (e.g. from global to reader)
    if (view !== 'reader') {
      clearChat();
    }
  }, [view, selectedBook?.id, currentPage]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    if (view !== 'global-chat' && !selectedBook) return;
    if (usageStatus?.hasReachedLimit) return;

    const userMsg: Message = { role: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');

    // Abort any existing chat before starting new one
    abortOngoingChat();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsChatting(true);
    setStreamingMessage('');

    try {
      const bookId = (view === 'global-chat') ? 'global' : selectedBook!.id;
      const historyToSend = [...chatMessages, userMsg];

      await chatWithBookStream(
        userMsg.text,
        bookId,
        view === 'reader' ? (currentPage || undefined) : undefined,
        historyToSend,
        // onChunk
        (chunk: string) => {
          setStreamingMessage(prev => prev + chunk);
        },
        // onComplete
        () => {
          const finalMessage = streamingMessageRef.current;
          setChatMessages(prev => [...prev, { role: 'model', text: finalMessage }]);
          setStreamingMessage('');
          setIsChatting(false);
        },
        // onError
        (error: string) => {
          if (controller.signal.aborted) return;
          setChatMessages(prev => [...prev, { role: 'model', text: error }]);
          setStreamingMessage('');
          setIsChatting(false);
        },
        controller.signal
      );
    } catch (err: any) {
      if (err.name === 'AbortError') return;

      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم." }]);
      setStreamingMessage('');
      setIsChatting(false);
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
    }
  };

  const clearChat = () => setChatMessages([]);

  return {
    chatMessages,
    setChatMessages,
    chatInput,
    setChatInput,
    isChatting,
    streamingMessage,
    usageStatus,
    handleSendMessage,
    clearChat,
    chatContainerRef,
  };
};
