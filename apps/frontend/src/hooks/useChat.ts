import { Book, Message } from '@shared/types';
import { useCallback, useEffect, useRef, useState } from 'react';
import { DEFAULT_CHARACTER_ID } from '../constants/characters';
import { chatWithBookStream, getChatUsage, submitChatFeedback } from '../services/geminiService';
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
  const contextBookIdsRef = useRef<string[]>([]);
  const pendingEvalIdRef = useRef<number | null>(null);

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

  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, isChatting, view, streamingMessage]);

  // Fetch usage status once when in a chat-capable view
  useEffect(() => {
    if (isAuthenticated && (view === 'global-chat' || view === 'reader')) {
      getChatUsage().then(setUsageStatus);
    } else if (!isAuthenticated) {
      setUsageStatus(null);
    }
  }, [isAuthenticated, view]);

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

  // Terminate chat if context changes (view or book switches)
  useEffect(() => {
    abortOngoingChat();
    // Also clear messages if we switch major views (e.g. from global to reader)
    if (view !== 'reader') {
      clearChat();
    }
  }, [view, selectedBook?.id]);

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

    streamingMessageRef.current = '';
    setIsChatting(true);
    setStreamingMessage('');
    setStreamingPartialResult(false);
    hasToolFailureRef.current = false;
    // Seed with an active "thinking" step immediately so the bubble is already
    // at AgentThinkingSteps size before the first real event arrives — prevents
    // the small-TypingCarousel → large-steps resize jitter.
    setAgentSteps([{ id: 'initial-think', type: 'thinking', status: 'active' }]);

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
          streamingMessageRef.current += chunk;
          setStreamingMessage(prev => prev + chunk);
        },
        // onComplete
        () => {
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
        },
        // onError
        (error: string) => {
          if (controller.signal.aborted) return;
          setChatMessages(prev => [...prev, { role: 'model', text: error, characterId: selectedCharacterId }]);
          setStreamingMessage('');
          setIsChatting(false);
          setStreamingPartialResult(false);
          hasToolFailureRef.current = false;
        },
        controller.signal,
        selectedCharacterId,
        // onCorrection
        (correctedText: string) => {
          setStreamingMessage(correctedText);
          streamingMessageRef.current = correctedText;
        },
        // onUsageUpdate
        (usage: any) => {
          setUsageStatus(usage);
        },
        // contextBookIds — carry forward the book context from the previous response
        view === 'global-chat' ? contextBookIdsRef.current : [],
        // onContextBookIds — store new context for the next request
        view === 'global-chat' ? (ids: string[]) => { contextBookIdsRef.current = ids; } : undefined,
        // onAgentEvent — live agent step events
        handleAgentEvent,
        // onEvalId — capture eval id from done event
        (evalId: number) => { pendingEvalIdRef.current = evalId; },
      );
    } catch (err: any) {
      if (err.name === 'AbortError') return;

      setChatMessages(prev => [...prev, { role: 'model', text: "كەچۈرۈڭ، جاۋاب بېرەلمىدىم.", characterId: selectedCharacterId }]);
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
    // Optimistically update UI state
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
  };
};
