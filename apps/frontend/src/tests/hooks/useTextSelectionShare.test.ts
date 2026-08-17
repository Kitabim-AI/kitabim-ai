import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, test } from 'vitest';
import { useTextSelectionShare } from '@/src/hooks/useTextSelectionShare';

const fireSelectionChange = () => {
  act(() => {
    document.dispatchEvent(new Event('selectionchange'));
  });
};

const selectTextIn = (el: Node, startOffset: number, endOffset: number) => {
  const range = document.createRange();
  range.setStart(el, startOffset);
  range.setEnd(el, endOffset);
  const selection = window.getSelection()!;
  selection.removeAllRanges();
  selection.addRange(range);
};

beforeEach(() => {
  document.body.innerHTML = '';
  window.getSelection()?.removeAllRanges();
  // jsdom doesn't implement Range.prototype.getBoundingClientRect at all (unlike
  // Element.prototype.getBoundingClientRect, which is stubbed to an all-zero rect) —
  // polyfill it the same way so the hook's real getBoundingClientRect() call works.
  Range.prototype.getBoundingClientRect = function (this: Range) {
    return { x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, toJSON() {} } as DOMRect;
  };
});

describe('useTextSelectionShare', () => {
  test('returns null when there is no selection', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Hello world</p>';
    document.body.appendChild(container);

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));
    expect(result.current).toBeNull();
  });

  test('returns the selected text and coordinates when the selection is inside the container', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Hello world example</p>';
    document.body.appendChild(container);
    const textNode = container.querySelector('p')!.firstChild!;

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));

    selectTextIn(textNode, 6, 11); // "world"
    fireSelectionChange();

    expect(result.current?.text).toBe('world');
    expect(typeof result.current?.top).toBe('number');
    expect(typeof result.current?.left).toBe('number');
  });

  test('returns null when the selection is outside the container', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Inside text</p>';
    document.body.appendChild(container);

    const outside = document.createElement('p');
    outside.textContent = 'Outside text';
    document.body.appendChild(outside);

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));

    selectTextIn(outside.firstChild!, 0, 7);
    fireSelectionChange();

    expect(result.current).toBeNull();
  });

  test('returns null once the selection is cleared', () => {
    const container = document.createElement('div');
    container.innerHTML = '<p>Hello world</p>';
    document.body.appendChild(container);
    const textNode = container.querySelector('p')!.firstChild!;

    const { result } = renderHook(() => useTextSelectionShare({ current: container }));

    selectTextIn(textNode, 0, 5);
    fireSelectionChange();
    expect(result.current?.text).toBe('Hello');

    window.getSelection()?.removeAllRanges();
    fireSelectionChange();
    expect(result.current).toBeNull();
  });
});
