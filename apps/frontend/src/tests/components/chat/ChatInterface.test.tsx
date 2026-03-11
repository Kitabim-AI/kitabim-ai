import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders as render } from '@/src/tests/test-utils';
import { ChatInterface } from '@/src/components/chat/ChatInterface';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Message } from '@shared/types';

const mockMessages: Message[] = [
  { role: 'user', text: 'Hello' },
  { role: 'model', text: 'Salam' }
];

test.skip('ChatInterface renders global chat correctly', () => {
  const ref = { current: document.createElement('div') };
  render(
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

  expect(screen.getByText('كىتابىم خەزىنىسى')).toBeInTheDocument();
  expect(screen.getByText(/ئىزدەۋاتىدۇ 5/i)).toBeInTheDocument();
  expect(screen.getByText(/خۇش كەپسىز/i)).toBeInTheDocument();
});

test.skip('ChatInterface renders book chat correctly', () => {
  const ref = { current: document.createElement('div') };
  render(
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

  expect(screen.getByText('كىتابىم ياردەمچىسى')).toBeInTheDocument();
  expect(screen.getByText('Hello')).toBeInTheDocument();
  expect(screen.getByText('Salam')).toBeInTheDocument();
  expect(screen.getByText(/بەت:\s*3/i)).toBeInTheDocument();
  expect(screen.getByDisplayValue('my question')).toBeInTheDocument();
});

test.skip('ChatInterface handles input change and send message', () => {
  const setChatInput = vi.fn();
  const onSendMessage = vi.fn();
  const ref = { current: document.createElement('div') };

  render(
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

  const input = screen.getByPlaceholderText(/سوئال سوراش/i);
  fireEvent.change(input, { target: { value: 'test' } });
  expect(setChatInput).toHaveBeenCalledWith('test');

  const sendBtn = screen.getByRole('button'); // Send button
  fireEvent.click(sendBtn);
  expect(onSendMessage).toHaveBeenCalled();
});

test.skip('ChatInterface shows loading state', () => {
  const ref = { current: document.createElement('div') };
  render(
    <ChatInterface
      type="book"
      chatMessages={[]}
      chatInput=""
      setChatInput={vi.fn()}
      onSendMessage={vi.fn()}
      isChatting={true}
      chatContainerRef={ref}
    />
  );

  // Loader should be present. Loader2 doesn't have text, but we can check if the button is disabled.
  expect(screen.getByRole('button')).toBeDisabled();
});

test('ChatInterface renders global chat messages and close button', () => {
  const onClose = vi.fn();
  const ref = { current: document.createElement('div') };
  render(
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

  const buttons = screen.getAllByRole('button');
  fireEvent.click(buttons[0]);
  expect(onClose).toHaveBeenCalled();
});

test.skip('ChatInterface global send button disables when input empty', () => {
  const ref = { current: document.createElement('div') };
  render(
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

  const sendButtons = screen.getAllByRole('button');
  const sendBtn = sendButtons[sendButtons.length - 1];
  expect(sendBtn).toBeDisabled();
});

test.skip('ChatInterface global input sends on Enter', () => {
  const onSendMessage = vi.fn();
  const ref = { current: document.createElement('div') };

  render(
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

  const input = screen.getByPlaceholderText(/سۇئال سوراڭ/i);
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onSendMessage).toHaveBeenCalled();
});

test.skip('ChatInterface shows book helper message when empty', () => {
  const ref = { current: document.createElement('div') };
  render(
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

  expect(screen.getByText(/مەزمۇنلارنى تېپىشقا ياردەم/i)).toBeInTheDocument();
});
