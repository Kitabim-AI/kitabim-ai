import { useState, useRef, useEffect } from 'react';
import { Message, Book } from '@shared/types';
import { chatWithBook, getChatUsage } from '../services/geminiService';
import { useAuth } from './useAuth';

export const useChat = (view: string, selectedBook: Book | null, currentPage: number | null) => {
  const { isAuthenticated } = useAuth();
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatting, setIsChatting] = useState(false);
  const [usageStatus, setUsageStatus] = useState<{ usage: number, limit: number | null, hasReachedLimit: boolean } | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, isChatting, view]);

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

    try {
      const bookId = (view === 'global-chat') ? 'global' : selectedBook!.id;
      const historyToSend = [...chatMessages, userMsg];

      const aiResponse = await chatWithBook(
        userMsg.text,
        bookId,
        view === 'reader' ? (currentPage || undefined) : undefined,
        historyToSend
      );
      setChatMessages(prev => [...prev, { role: 'model', text: aiResponse }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم." }]);
    } finally {
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
    usageStatus,
    handleSendMessage,
    clearChat,
    chatContainerRef,
  };
};
