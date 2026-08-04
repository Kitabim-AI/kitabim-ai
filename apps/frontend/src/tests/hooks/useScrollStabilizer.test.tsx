import { useScrollStabilizer } from '@/src/hooks/useScrollStabilizer';
import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';

class FakeResizeObserver {
  static instances: FakeResizeObserver[] = [];
  callback: ResizeObserverCallback;
  observed: Element[] = [];
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    FakeResizeObserver.instances.push(this);
  }
  observe(el: Element) {
    this.observed.push(el);
  }
  unobserve(el: Element) {
    this.observed = this.observed.filter(o => o !== el);
  }
  disconnect() {
    this.observed = [];
  }
}

const setRect = (el: HTMLElement, top: number, height: number) => {
  el.getBoundingClientRect = () =>
    ({ top, height, bottom: top + height, left: 0, right: 0, width: 0, x: 0, y: top, toJSON() {} } as DOMRect);
};

const fireResize = (observer: FakeResizeObserver, target: Element, height: number) => {
  observer.callback(
    [{ target, contentRect: { height } } as unknown as ResizeObserverEntry],
    observer as unknown as ResizeObserver
  );
};

beforeEach(() => {
  FakeResizeObserver.instances = [];
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test('scrolls down to compensate when an item fully above the viewport grows taller', () => {
  const container = document.createElement('div');
  setRect(container, 500, 0);
  container.scrollTop = 1000;

  const itemAbove = document.createElement('div');
  setRect(itemAbove, 100, 200); // bottom = 300, well above containerTop (500)

  renderHook(() =>
    useScrollStabilizer({
      containerRef: { current: container },
      itemsRef: { current: new Map([[1, itemAbove]]) },
    })
  );

  const observer = FakeResizeObserver.instances[0];
  fireResize(observer, itemAbove, 200); // establishes baseline height, no compensation yet
  expect(container.scrollTop).toBe(1000);

  fireResize(observer, itemAbove, 600); // grew by 400 while still fully above the viewport
  expect(container.scrollTop).toBe(1400);
});

test('does not adjust scroll when a partially/fully visible item grows taller', () => {
  const container = document.createElement('div');
  setRect(container, 500, 0);
  container.scrollTop = 1000;

  const itemBelow = document.createElement('div');
  setRect(itemBelow, 600, 200); // top is below containerTop (500) — visible or below viewport

  renderHook(() =>
    useScrollStabilizer({
      containerRef: { current: container },
      itemsRef: { current: new Map([[1, itemBelow]]) },
    })
  );

  const observer = FakeResizeObserver.instances[0];
  fireResize(observer, itemBelow, 200);
  fireResize(observer, itemBelow, 400);

  expect(container.scrollTop).toBe(1000);
});

test('skips compensation while suppressed, but keeps tracking heights for later resizes', () => {
  const container = document.createElement('div');
  setRect(container, 500, 0);
  container.scrollTop = 1000;

  const itemAbove = document.createElement('div');
  setRect(itemAbove, 100, 200);

  const suppressedRef = { current: true };

  renderHook(() =>
    useScrollStabilizer({
      containerRef: { current: container },
      itemsRef: { current: new Map([[1, itemAbove]]) },
      suppressedRef,
    })
  );

  const observer = FakeResizeObserver.instances[0];
  fireResize(observer, itemAbove, 200); // baseline
  fireResize(observer, itemAbove, 250); // grew by 50 while suppressed — no compensation
  expect(container.scrollTop).toBe(1000);

  suppressedRef.current = false;
  fireResize(observer, itemAbove, 300); // grew by 50 more, no longer suppressed
  expect(container.scrollTop).toBe(1050);
});
