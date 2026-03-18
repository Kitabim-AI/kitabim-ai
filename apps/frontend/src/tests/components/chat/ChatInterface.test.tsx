import { screen, fireEvent } from '@testing-library/react';
import { render } from '@testing-library/react';
import { ChatInterface } from '@/src/components/chat/ChatInterface';
import { expect, test, vi, beforeEach } from 'vitest';
import React from 'react';
import { Message } from '@shared/types';
import * as AuthModule from '@/src/hooks/useAuth';
import * as AppContextModule from '@/src/context/AppContext';
import { I18nContext } from '@/src/i18n/I18nContext';

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

  expect(screen.getByText('chat.globalAssistant')).toBeInTheDocument();
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

  const sendBtn = screen.getAllByRole('button').at(-1)!;
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

  expect(screen.getAllByRole('button').at(-1)).toBeDisabled();
});

test('ChatInterface renders global chat messages and close button', () => {
  const onClose = vi.fn();
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
      onClose={onClose}
      chatContainerRef={ref}
    />
  );

  expect(screen.getByText('Hello')).toBeInTheDocument();
  expect(screen.getByText('Salam')).toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('button')[0]);
  expect(onClose).toHaveBeenCalled();
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

  expect(screen.getAllByRole('button').at(-1)).toBeDisabled();
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
