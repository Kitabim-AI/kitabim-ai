import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { useQuoteHighlight } from '@/src/hooks/useQuoteHighlight';

beforeEach(() => {
  document.body.innerHTML = '';
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

const makeContainer = (html: string): HTMLDivElement => {
  const div = document.createElement('div');
  div.innerHTML = html;
  document.body.appendChild(div);
  return div;
};

describe('useQuoteHighlight', () => {
  test('does nothing while renderedText is empty (page still loading) — onApplied is not called', () => {
    const container = makeContainer('<p></p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, 'some quote', '', onApplied));

    expect(onApplied).not.toHaveBeenCalled();
    expect(container.querySelector('mark')).toBeNull();
  });

  test('does nothing when quote is null/undefined — onApplied is not called', () => {
    const container = makeContainer('<p>Hello world</p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, null, 'Hello world', onApplied));

    expect(onApplied).not.toHaveBeenCalled();
  });

  test('wraps and scrolls to a match fully inside a single text node', () => {
    const container = makeContainer('<p>Hello world example text</p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() =>
      useQuoteHighlight(ref, 'world example', 'Hello world example text', onApplied)
    );

    const mark = container.querySelector('mark');
    expect(mark).not.toBeNull();
    expect(mark?.textContent).toBe('world example');
    expect(container.textContent).toBe('Hello world example text');
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith({
      block: 'center',
      behavior: 'smooth',
    });
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  test('wraps a match spanning multiple text nodes across an element boundary', () => {
    const container = makeContainer('<p>Hello <strong>bold</strong> world</p>');
    // Concatenated raw text: "Hello bold world" — pick a quote spanning all 3 text nodes.
    const quote = 'lo bold wo';
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, quote, 'Hello bold world', onApplied));

    const marks = container.querySelectorAll('mark');
    expect(marks.length).toBeGreaterThan(1);
    expect(container.textContent).toBe('Hello bold world');
    expect(Array.from(marks).map(m => m.textContent).join('')).toBe(quote);
    expect(onApplied).toHaveBeenCalledTimes(1);
  });

  test('no-op (no <mark>, no scroll) when the quote is not found, but onApplied still fires once', () => {
    const container = makeContainer('<p>Hello world</p>');
    const ref = { current: container };
    const onApplied = vi.fn();

    renderHook(() => useQuoteHighlight(ref, 'text that does not exist', 'Hello world', onApplied));

    expect(container.querySelector('mark')).toBeNull();
    expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled();
    expect(onApplied).toHaveBeenCalledTimes(1);
  });
});
