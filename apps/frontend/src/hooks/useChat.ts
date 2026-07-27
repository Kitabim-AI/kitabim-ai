import { Book, Conversation, Message } from '@shared/types';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DEFAULT_CHARACTER_ID } from '../constants/characters';
import { useI18n } from '../i18n/I18nContext';
import {
  chatWithBookStream,
  deleteConversation,
  getChatUsage,
  getConversationMessages,
  getUserConversations,
  submitChatFeedback,
} from '../services/geminiService';
import { useNotification } from '../context/NotificationContext';
import { useAuth } from './useAuth';

export interface AgentStep {
  id: string;
  type: 'decomposing' | 'planning' | 'thinking' | 'tool' | 'grading' | 'generating';
  tool?: string;
  found?: number;
  kept?: number;
  total?: number;
  count?: number;
  status: 'active' | 'done';
}

export const useChat = (view: string, selectedBook: Book | null, currentPage: number | null) => {
  const { isAuthenticated } = useAuth();
  const { addNotification } = useNotification();
  const { t } = useI18n();
  const [selectedCharacterId, setSelectedCharacterId] = useState<string>(DEFAULT_CHARACTER_ID);
  const [chatMessages, setChatMessages] = useState<Message[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isChatting, setIsChatting] = useState(false);
  const [streamingMessage, setStreamingMessage] = useState('');
  const [streamingPartialResult, setStreamingPartialResult] = useState(false);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>([]);
  const streamingMessageRef = useRef('');
  const hasToolFailureRef = useRef(false);
  const [usageStatus, setUsageStatus] = useState<{ usage: number, limit: number | null, hasReachedLimit: boolean } | null>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const contextBookIdsRef = useRef<string[]>([]);
  const pendingEvalIdRef = useRef<number | null>(null);
  const streamUpdateTimerRef = useRef<number | null>(null);

  const scheduleStreamingUpdate = useCallback(() => {
    if (streamUpdateTimerRef.current !== null) return;
    streamUpdateTimerRef.current = requestAnimationFrame(() => {
      setStreamingMessage(streamingMessageRef.current);
      streamUpdateTimerRef.current = null;
    });
  }, []);

  const cancelStreamingUpdate = useCallback(() => {
    if (streamUpdateTimerRef.current !== null) {
      cancelAnimationFrame(streamUpdateTimerRef.current);
      streamUpdateTimerRef.current = null;
    }
  }, []);

  const fetchConversations = useCallback(async () => {
    if (!isAuthenticated) {
      setConversations([]);
      return;
    }
    setIsLoadingConversations(true);
    const list = await getUserConversations(50, 0);
    setConversations(list);
    setIsLoadingConversations(false);
  }, [isAuthenticated]);

  const handleAgentEvent = useCallback((event: Record<string, any>) => {
    const { type } = event;

    if (type === 'error' && event.code === 'tool_failure') {
      hasToolFailureRef.current = true;
      setStreamingPartialResult(true);
      return;
    }

    if (type === 'answer_start') {
      streamingMessageRef.current = '';
      setStreamingMessage('');
      setAgentSteps(prev => {
        const steps = prev.map(s => s.status === 'active' ? { ...s, status: 'done' as const } : s);
        return [...steps, { id: 'generating', type: 'generating' as const, status: 'active' as const }];
      });
      return;
    }

    setAgentSteps(prev => {
      if (type === 'tool_result') {
        let toolIdx = -1;
        for (let i = prev.length - 1; i >= 0; i--) {
          if (prev[i].type === 'tool' && prev[i].status === 'active') { toolIdx = i; break; }
        }
        if (toolIdx < 0) return prev;
        return prev.map((s, i) => i === toolIdx ? { ...s, status: 'done' as const, found: event.found } : s);
      }

      const steps = prev.map(s => s.status === 'active' ? { ...s, status: 'done' as const } : s);

      if (type === 'decompose') {
        return [...steps, { id: 'decompose', type: 'decomposing' as const, count: event.count, status: 'done' as const }];
      }
      if (type === 'planning') {
        return [...steps, { id: 'plan', type: 'planning' as const, status: 'done' as const }];
      }
      if (type === 'agent_thinking') {
        let thinkIdx = -1;
        for (let i = steps.length - 1; i >= 0; i--) {
          if (steps[i].type === 'thinking') { thinkIdx = i; break; }
        }
        const thinkStep: AgentStep = { id: 'think', type: 'thinking', status: 'active' };
        if (thinkIdx >= 0) {
          return [...steps.slice(0, thinkIdx), thinkStep, ...steps.slice(thinkIdx + 1)];
        }
        return [...steps, thinkStep];
      }
      if (type === 'tool_call') {
        return [...steps, { id: `tool-${event.tool}-${Date.now()}`, type: 'tool' as const, tool: event.tool, status: 'active' as const }];
      }
      if (type === 'grading') {
        return [...steps, { id: 'grade', type: 'grading' as const, kept: event.after, total: event.before, status: 'done' as const }];
      }
      return steps;
    });
  }, []);

  const scrollToBottom = useCallback((onlyIfNearBottom = true) => {
    const el = chatContainerRef.current;
    if (!el) return;
    if (onlyIfNearBottom) {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      if (distanceFromBottom > 140) return;
    }
    el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    // Force scroll during thinking phase (when isChatting is true but streamingMessage hasn't started yet),
    // or when chatMessages/view changes, so user question and thinking steps are always scrolled into view.
    const isThinkingPhase = isChatting && !streamingMessage;
    scrollToBottom(!isThinkingPhase);
  }, [chatMessages, isChatting, view, streamingMessage, agentSteps, scrollToBottom]);

  // Fetch usage status and conversation history when entering a chat view
  useEffect(() => {
    if (isAuthenticated && (view === 'global-chat' || view === 'reader')) {
      getChatUsage().then(setUsageStatus);
    } else if (!isAuthenticated) {
      setUsageStatus(null);
    }
    if (view === 'global-chat') {
      fetchConversations();
    }
  }, [isAuthenticated, view, fetchConversations]);

  const abortOngoingChat = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    streamingMessageRef.current = '';
    setIsChatting(false);
    setStreamingMessage('');
    setStreamingPartialResult(false);
    hasToolFailureRef.current = false;
    setAgentSteps([]);
  };

  // Terminate chat if context changes (view or book switches) & auto-load book conversation in reader
  useEffect(() => {
    abortOngoingChat();
    setConversationId(undefined);

    if (view === 'reader' && selectedBook?.id && isAuthenticated) {
      setIsLoadingMessages(true);
      getUserConversations(1, 0, selectedBook.id)
        .then(async list => {
          if (list.length > 0) {
            const latestConv = list[0];
            setConversationId(latestConv.id);
            const msgs = await getConversationMessages(latestConv.id);
            const formatted: Message[] = msgs.map(m => ({
              role: m.role,
              text: m.content,
              evalId: m.evalId ?? undefined,
            }));
            setChatMessages(formatted);
          } else {
            clearChat();
          }
        })
        .catch(err => {
          console.error('Failed to auto-load book conversation history:', err);
          clearChat();
        })
        .finally(() => {
          setIsLoadingMessages(false);
        });
    } else if (view !== 'reader') {
      clearChat();
    }
  }, [view, selectedBook?.id, isAuthenticated]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const selectConversation = async (convId: string) => {
    if (convId === conversationId) return;
    abortOngoingChat();
    setIsLoadingMessages(true);
    setConversationId(convId);
    try {
      const msgs = await getConversationMessages(convId);
      const formatted: Message[] = msgs.map(m => ({
        role: m.role,
        text: m.content,
        evalId: m.evalId ?? undefined,
      }));
      setChatMessages(formatted);
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const startNewChat = () => {
    abortOngoingChat();
    setConversationId(undefined);
    clearChat();
  };

  const deleteConversationHandler = async (convId: string) => {
    try {
      const success = await deleteConversation(convId);
      if (success) {
        setConversations(prev => prev.filter(c => c.id !== convId));
        if (conversationId === convId) {
          startNewChat();
        }
        addNotification(t('chat.deleteSuccess'), 'success');
      } else {
        addNotification(t('chat.deleteError'), 'error');
      }
    } catch {
      addNotification(t('chat.deleteError'), 'error');
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;
    if (view !== 'global-chat' && !selectedBook) return;
    if (usageStatus?.hasReachedLimit) return;

    const trimmedInput = chatInput.trim();
    if (trimmedInput.length > 500) {
      setChatMessages(prev => [
        ...prev,
        { role: 'user', text: chatInput },
        { role: 'model', text: t('chat.textTooLong'), characterId: selectedCharacterId }
      ]);
      setChatInput('');
      return;
    }

    const hasArabicScript = /[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]/.test(trimmedInput);
    if (!hasArabicScript) {
      setChatMessages(prev => [
        ...prev,
        { role: 'user', text: chatInput },
        { role: 'model', text: t('chat.invalidLanguage'), characterId: selectedCharacterId }
      ]);
      setChatInput('');
      return;
    }

    const userMsg: Message = { role: 'user', text: chatInput };
    setChatMessages(prev => [...prev, userMsg]);
    setChatInput('');

    // Abort any existing chat before starting new one
    abortOngoingChat();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    streamingMessageRef.current = '';
    setIsChatting(true);
    setStreamingMessage('');
    setStreamingPartialResult(false);
    hasToolFailureRef.current = false;
    setAgentSteps([{ id: 'initial-think', type: 'thinking', status: 'active' }]);

    try {
      const bookId = (view === 'global-chat') ? 'global' : selectedBook!.id;
      const historyToSend = [...chatMessages, userMsg];

      await chatWithBookStream(
        {
          question: userMsg.text,
          bookId,
          currentPage: view === 'reader' ? (currentPage || undefined) : undefined,
          history: historyToSend,
          characterId: selectedCharacterId,
          contextBookIds: view === 'global-chat' ? contextBookIdsRef.current : [],
          conversationId,
          signal: controller.signal,
        },
        {
          onChunk: (chunk: string) => {
            streamingMessageRef.current += chunk;
            scheduleStreamingUpdate();
          },
          onComplete: () => {
            cancelStreamingUpdate();
            const finalMessage = streamingMessageRef.current;
            const evalId = pendingEvalIdRef.current ?? undefined;
            pendingEvalIdRef.current = null;
            setChatMessages(prev => [...prev, {
              role: 'model',
              text: finalMessage,
              characterId: selectedCharacterId,
              evalId,
              partialResult: hasToolFailureRef.current
            }]);
            streamingMessageRef.current = '';
            setStreamingMessage('');
            setIsChatting(false);
            setStreamingPartialResult(false);
            hasToolFailureRef.current = false;
            fetchConversations();
          },
          onError: (error: string) => {
            cancelStreamingUpdate();
            if (controller.signal.aborted) return;
            setChatMessages(prev => [...prev, { role: 'model', text: error, characterId: selectedCharacterId }]);
            streamingMessageRef.current = '';
            setStreamingMessage('');
            setIsChatting(false);
            setStreamingPartialResult(false);
            hasToolFailureRef.current = false;
          },
          onCorrection: (correctedText: string) => {
            streamingMessageRef.current = correctedText;
            setStreamingMessage(correctedText);
          },
          onUsageUpdate: (usage: any) => {
            setUsageStatus(usage);
          },
          onContextBookIds: view === 'global-chat' ? (ids: string[]) => { contextBookIdsRef.current = ids; } : undefined,
          onAgentEvent: handleAgentEvent,
          onEvalId: (evalId: number) => { pendingEvalIdRef.current = evalId; },
          onConversationId: (convId: string) => { setConversationId(convId); },
        },
      );
    } catch (err: any) {
      cancelStreamingUpdate();
      if (err.name === 'AbortError') return;

      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم.", characterId: selectedCharacterId }]);
      streamingMessageRef.current = '';
      setStreamingMessage('');
      setIsChatting(false);
      setStreamingPartialResult(false);
      hasToolFailureRef.current = false;
    } finally {
      if (abortControllerRef.current === controller) {
        abortControllerRef.current = null;
      }
    }
  };

  const clearChat = () => {
    setChatMessages([]);
    contextBookIdsRef.current = [];
    pendingEvalIdRef.current = null;
  };

  const submitFeedback = async (messageIndex: number, feedback: 'positive' | 'negative') => {
    const msg = chatMessages[messageIndex];
    if (!msg || msg.role !== 'model' || !msg.evalId) return;
    setChatMessages(prev =>
      prev.map((m, i) => i === messageIndex ? { ...m, feedback } : m)
    );
    await submitChatFeedback(msg.evalId, feedback);
  };

  return {
    chatMessages,
    setChatMessages,
    chatInput,
    setChatInput,
    isChatting,
    streamingMessage,
    streamingPartialResult,
    agentSteps,
    usageStatus,
    handleSendMessage,
    clearChat,
    chatContainerRef,
    selectedCharacterId,
    setSelectedCharacterId,
    submitFeedback,
    conversationId,
    conversations,
    isLoadingConversations,
    isLoadingMessages,
    selectConversation,
    startNewChat,
    deleteConversation: deleteConversationHandler,
    fetchConversations,
  };
};

