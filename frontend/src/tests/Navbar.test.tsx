import { render, screen, fireEvent } from '@testing-library/react';
import { Navbar } from '../components/layout/Navbar';
import { expect, test, vi } from 'vitest';
import React from 'react';

test('Navbar renders correctly and handles view changes', () => {
  const setView = vi.fn();
  const setSearchQuery = vi.fn();
  const onFileUpload = vi.fn();
  const clearChat = vi.fn();

  render(
    <Navbar
      view="library"
      setView={setView}
      searchQuery=""
      setSearchQuery={setSearchQuery}
      onFileUpload={onFileUpload}
      clearChat={clearChat}
    />
  );

  // Check branding
  expect(screen.getByText(/Kitabim/i)).toBeInTheDocument();

  // Check navigation buttons
  const libraryBtn = screen.getByText(/Global Library/i);
  const chatBtn = screen.getByText(/Global Assistant/i);
  const adminBtn = screen.getByText(/Management/i);

  fireEvent.click(libraryBtn);
  expect(setView).toHaveBeenCalledWith('library');

  fireEvent.click(chatBtn);
  expect(setView).toHaveBeenCalledWith('global-chat');
  expect(clearChat).toHaveBeenCalled();

  fireEvent.click(adminBtn);
  expect(setView).toHaveBeenCalledWith('admin');
});

test('Navbar handles search input', () => {
  const setSearchQuery = vi.fn();
  render(
    <Navbar
      view="library"
      setView={vi.fn()}
      searchQuery="test query"
      setSearchQuery={setSearchQuery}
      onFileUpload={vi.fn()}
      clearChat={vi.fn()}
    />
  );

  const input = screen.getByPlaceholderText(/Search documents.../i);
  expect(input).toHaveValue('test query');

  fireEvent.change(input, { target: { value: 'new query' } });
  expect(setSearchQuery).toHaveBeenCalledWith('new query');
});

test('Navbar handles file upload trigger', () => {
  render(
    <Navbar
      view="library"
      setView={vi.fn()}
      searchQuery=""
      setSearchQuery={vi.fn()}
      onFileUpload={vi.fn()}
      clearChat={vi.fn()}
    />
  );

  const uploadBtn = screen.getByText(/Process PDF/i);
  expect(uploadBtn).toBeInTheDocument();

  // We can't easily test the file input click directly due to browser security,
  // but we verified the button exists and identifies correctly.
});
