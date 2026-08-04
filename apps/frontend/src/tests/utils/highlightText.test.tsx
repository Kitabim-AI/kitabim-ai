import { highlightText } from '@/src/utils/highlightText';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { expect, test } from 'vitest';

test('wraps matched substring in a <mark> element', () => {
  render(<div>{highlightText('Hello world', 'world')}</div>);
  const mark = screen.getByText('world');
  expect(mark.tagName).toBe('MARK');
});

test('matches case-insensitively', () => {
  render(<div>{highlightText('Hello World', 'world')}</div>);
  const mark = screen.getByText('World');
  expect(mark.tagName).toBe('MARK');
});

test('highlights every occurrence of the query', () => {
  render(<div>{highlightText('cat sat on the cat mat', 'cat')}</div>);
  expect(screen.getAllByText('cat')).toHaveLength(2);
});

test('returns the original text unchanged when the query is empty', () => {
  render(<div>{highlightText('Hello world', '')}</div>);
  expect(screen.queryByText('world')?.tagName).not.toBe('MARK');
  expect(screen.getByText('Hello world')).toBeInTheDocument();
});

test('escapes regex special characters in the query', () => {
  render(<div>{highlightText('a (b) c', '(b)')}</div>);
  const mark = screen.getByText('(b)');
  expect(mark.tagName).toBe('MARK');
});
