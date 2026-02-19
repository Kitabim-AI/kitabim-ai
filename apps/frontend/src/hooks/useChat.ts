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

  // Fetch usage status on mount and when messages change (after sending)
  useEffect(() => {
    if (isAuthenticated) {
      getChatUsage().then(setUsageStatus);
    } else {
      setUsageStatus(null);
    }
  }, [isAuthenticated, chatMessages]);

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    if (view !== 'global-chat' && !selectedBook) return;
    if (usageStatus?.hasReachedLimit) return;

    const userMsg: Message = { role: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');
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
          // Use ref to get the latest value
          const finalMessage = streamingMessageRef.current;
          setChatMessages(prev => [...prev, { role: 'model', text: finalMessage }]);
          setStreamingMessage('');
          setIsChatting(false);
        },
        // onError
        (error: string) => {
          setChatMessages(prev => [...prev, { role: 'model', text: error }]);
          setStreamingMessage('');
          setIsChatting(false);
        }
      );
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم." }]);
      setStreamingMessage('');
      setIsChatting(false);
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
