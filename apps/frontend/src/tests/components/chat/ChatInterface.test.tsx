import { ChatInterface } from '@/src/components/chat/ChatInterface';
import * as AppContextModule from '@/src/context/AppContext';
import * as AuthModule from '@/src/hooks/useAuth';
import { I18nContext } from '@/src/i18n/I18nContext';
import { Message } from '@shared/types';
import { fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { beforeEach, expect, test, vi } from 'vitest';

vi.mock('@/src/hooks/useAuth', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/src/context/AppContext', () => ({
  useAppContext: vi.fn(),
}));

vi.mock('@/src/components/auth/AuthButton', () => ({
  OAuthButtonGroup: () => <div>oauth-buttons</div>,
}));

vi.mock('@/src/components/common/MarkdownContent', () => ({
  MarkdownContent: ({ content }: { content: string }) => <div>{content}</div>,
}));

vi.mock('@/src/components/chat/ReferenceModal', () => ({
  ReferenceModal: () => null,
}));

vi.mock('@/src/components/common/ProverbDisplay', () => ({
  ProverbDisplay: ({ defaultText }: { defaultText: string }) => <div>{defaultText}</div>,
}));

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string, params?: Record<string, string | number>) => {
    if (params) {
      return Object.entries(params).reduce(
        (value, [paramKey, paramValue]) => value.replace(`{{${paramKey}}}`, String(paramValue)),
        key
      );
    }
    return key;
  },
};

const mockMessages: Message[] = [
  { role: 'user', text: 'Hello' },
  { role: 'model', text: 'Salam' }
];

const renderChat = (ui: React.ReactElement) =>
  render(
    <I18nContext.Provider value={i18nValue}>
      {ui}
    </I18nContext.Provider>
  );

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(AuthModule.useAuth).mockReturnValue({ isAuthenticated: true } as any);
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ fontSize: 18 } as any);
});

test('ChatInterface renders global chat correctly', () => {
  const ref = { current: document.createElement('div') };
  renderChat(
    <ChatInterface
      type="global"
      totalReady={5}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByText('chat.welcome.title')).toBeInTheDocument();
  expect(screen.getByText('chat.welcome.message')).toBeInTheDocument();
});

test('ChatInterface renders book chat correctly', () => {
  const ref = { current: document.createElement('div') };
  renderChat(
    <ChatInterface
      type="book"
      chatMessages={mockMessages}
      chatInput="my question"
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      currentPage={3}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByText('Hello')).toBeInTheDocument();
  expect(screen.getByText('Salam')).toBeInTheDocument();
  expect(screen.getByDisplayValue('my question')).toBeInTheDocument();
});

test('ChatInterface handles input change and send message', () => {
  const setChatInput = vi.fn();
  const onSendMessage = vi.fn();
  const ref = { current: document.createElement('div') };

  const { rerender } = renderChat(
    <ChatInterface
      type="book"
      chatMessages={[]}
      chatInput=""
      setChatInput={setChatInput}
      onSendMessage={onSendMessage}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  const input = screen.getByPlaceholderText('chat.inputPlaceholderBook');
  fireEvent.change(input, { target: { value: 'test' } });
  expect(setChatInput).toHaveBeenCalledWith('test');

  rerender(
    <I18nContext.Provider value={i18nValue}>
      <ChatInterface
        type="book"
        chatMessages={[]}
        chatInput="test"
        setChatInput={setChatInput}
        onSendMessage={onSendMessage}
        isChatting={false}
        chatContainerRef={ref}
      />
    </I18nContext.Provider>
  );

  const sendBtn = screen.getByTestId('send-button');
  fireEvent.click(sendBtn);
  expect(onSendMessage).toHaveBeenCalled();
});

test('ChatInterface shows loading state', () => {
  const ref = { current: document.createElement('div') };
  renderChat(
    <ChatInterface
      type="book"
      chatMessages={[]}
      chatInput="question"
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={true}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByTestId('send-button')).toBeDisabled();
});

test('ChatInterface renders global chat messages and share button', () => {
  const ref = { current: document.createElement('div') };
  renderChat(
    <ChatInterface
      type="global"
      totalReady={1}
      chatMessages={mockMessages}
      chatInput="hello"
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByText('Hello')).toBeInTheDocument();
  expect(screen.getByText('Salam')).toBeInTheDocument();
  expect(screen.getByTitle('share.shareQA')).toBeInTheDocument();
});

test('ChatInterface global send button disables when input empty', () => {
  const ref = { current: document.createElement('div') };
  renderChat(
    <ChatInterface
      type="global"
      totalReady={1}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByTestId('send-button')).toBeDisabled();
});

test('ChatInterface global input sends on Enter', () => {
  const onSendMessage = vi.fn();
  const ref = { current: document.createElement('div') };

  renderChat(
    <ChatInterface
      type="global"
      totalReady={1}
      chatMessages={[]}
      chatInput="hi"
      setChatInput={vi.fn()}
      onSendMessage={onSendMessage}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  const input = screen.getByPlaceholderText('chat.inputPlaceholderBook');
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onSendMessage).toHaveBeenCalled();
});

test('ChatInterface shows book helper message when empty', () => {
  const ref = { current: document.createElement('div') };
  renderChat(
    <ChatInterface
      type="book"
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByText('chat.bookAssistantWelcome')).toBeInTheDocument();
});

test('ChatInterface triggers setModal when delete conversation button is clicked', () => {
  const setModal = vi.fn();
  const onDeleteConversation = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ fontSize: 18, setModal } as any);
  const ref = { current: document.createElement('div') };

  const conversations = [
    { id: 'conv-1', userId: 'user-1', title: 'Test Conv', createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), isGlobal: true }
  ];

  renderChat(
    <ChatInterface
      type="global"
      totalReady={1}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
      conversations={conversations}
      onDeleteConversation={onDeleteConversation}
    />
  );

  const deleteBtn = screen.getByTitle('chat.deleteConversation');
  fireEvent.click(deleteBtn);

  expect(setModal).toHaveBeenCalledWith(
    expect.objectContaining({
      isOpen: true,
      title: 'chat.deleteConversation',
      message: 'chat.confirmDeleteConversation',
      type: 'confirm',
      destructive: true,
    })
  );

  // Execute onConfirm callback
  const modalConfig = setModal.mock.calls[0][0];
  modalConfig.onConfirm();
  expect(onDeleteConversation).toHaveBeenCalledWith('conv-1');
});

test('ChatInterface focuses input when onStartNewChat button is clicked', async () => {
  vi.useFakeTimers();
  const ref = { current: document.createElement('div') };
  const onStartNewChat = vi.fn();
  renderChat(
    <ChatInterface
      type="global"
      totalReady={1}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
      onStartNewChat={onStartNewChat}
    />
  );

  const newChatBtn = screen.getByTitle('chat.newChat');
  const input = screen.getByRole('textbox');
  const focusSpy = vi.spyOn(input, 'focus');

  fireEvent.click(newChatBtn);
  expect(onStartNewChat).toHaveBeenCalledTimes(1);

  vi.advanceTimersByTime(100);
  expect(focusSpy).toHaveBeenCalled();
  vi.useRealTimers();
});

test('ChatInterface closes history card on mobile view when new chat button is clicked', () => {
  Object.defineProperty(window, 'innerWidth', { writable: true, configurable: true, value: 500 });
  const ref = { current: document.createElement('div') };
  const onStartNewChat = vi.fn();
  renderChat(
    <ChatInterface
      type="global"
      totalReady={1}
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
      onStartNewChat={onStartNewChat}
    />
  );

  // Open history on mobile first
  const openHistoryBtns = screen.getAllByTitle('chat.historyTitle');
  fireEvent.click(openHistoryBtns[0]);
  expect(screen.getByText('chat.historyTitle')).toBeInTheDocument();

  // Click new chat button inside history header
  const newChatBtns = screen.getAllByTitle('chat.newChat');
  fireEvent.click(newChatBtns[0]);

  expect(onStartNewChat).toHaveBeenCalledTimes(1);
  // History title should no longer be visible because history card is closed on mobile
  expect(screen.queryByText('chat.historyTitle')).not.toBeInTheDocument();
});

test('ChatInterface renders delete button in reader mode when conversationId is present and triggers modal', () => {
  const setModal = vi.fn();
  const onDeleteConversation = vi.fn();
  vi.mocked(AppContextModule.useAppContext).mockReturnValue({ fontSize: 18, setModal } as any);
  const ref = { current: document.createElement('div') };

  renderChat(
    <ChatInterface
      type="book"
      bookId="book-1"
      conversationId="conv-reader-1"
      chatMessages={[{ role: 'user', text: 'Hello' }]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={false}
      chatContainerRef={ref}
      onDeleteConversation={onDeleteConversation}
    />
  );

  const deleteBtn = screen.getByTitle('chat.deleteConversation');
  expect(deleteBtn).toBeInTheDocument();
  fireEvent.click(deleteBtn);

  expect(setModal).toHaveBeenCalledWith(
    expect.objectContaining({
      isOpen: true,
      title: 'chat.deleteConversation',
      message: 'chat.confirmDeleteConversation',
      type: 'confirm',
      destructive: true,
    })
  );

  // Execute onConfirm callback
  const modalConfig = setModal.mock.calls[0][0];
  modalConfig.onConfirm();
  expect(onDeleteConversation).toHaveBeenCalledWith('conv-reader-1');
});



