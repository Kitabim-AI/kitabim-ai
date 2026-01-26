import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInterface } from '../components/chat/ChatInterface';
import { expect, test, vi } from 'vitest';
import React from 'react';
import { Message } from '../types';

const mockMessages: Message[] = [
  { role: 'user', text: 'Hello' },
  { role: 'model', text: 'Salam' }
];

test('ChatInterface renders global chat correctly', () => {
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

  expect(screen.getByText('Kitabim Global Mind')).toBeInTheDocument();
  expect(screen.getByText(/Searching across 5 processed books/i)).toBeInTheDocument();
  expect(screen.getByText(/ئەلئامان كىتابخانىسىغا خۇش كەپسىز!/i)).toBeInTheDocument();
});

test('ChatInterface renders book chat correctly', () => {
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

  expect(screen.getByText('Hello')).toBeInTheDocument();
  expect(screen.getByText('Salam')).toBeInTheDocument();
  expect(screen.getByText(/FOCUS: PAGE 3/i)).toBeInTheDocument();
  expect(screen.getByDisplayValue('my question')).toBeInTheDocument();
});

test('ChatInterface handles input change and send message', () => {
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

  const input = screen.getByPlaceholderText(/Ask a question...|كۈتۈپخانىدىكى بارلىق كىتابلاردىن سوئال سوراش.../i);
  fireEvent.change(input, { target: { value: 'test' } });
  expect(setChatInput).toHaveBeenCalledWith('test');

  const sendBtn = screen.getByRole('button'); // Send button
  fireEvent.click(sendBtn);
  expect(onSendMessage).toHaveBeenCalled();
});

test('ChatInterface shows loading state', () => {
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
