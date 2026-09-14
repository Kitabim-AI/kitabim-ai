import { useScrollToPage } from '@/src/hooks/useScrollToPage';
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

const setRect = (el: HTMLElement, top: number) => {
  el.getBoundingClientRect = () =>
    ({ top, height: 0, bottom: top, left: 0, right: 0, width: 0, x: 0, y: top, toJSON() {} } as DOMRect);
};

const fireResize = (observer: FakeResizeObserver, target: Element) => {
  // A real (disconnected) ResizeObserver never fires for elements it's no
  // longer observing -- mirror that here rather than invoking the stored
  // callback unconditionally, or a disconnect() in the hook under test
  // would go undetected by this fake.
  if (!observer.observed.includes(target)) return;
  observer.callback(
    [{ target, contentRect: {} } as unknown as ResizeObserverEntry],
    observer as unknown as ResizeObserver
  );
};

function setUpContainerAndTarget(bookId: string, targetPage: number) {
  const container = document.createElement('div');
  setRect(container, 0);
  container.scrollTop = 0;
  container.scrollTo = vi.fn();

  const targetEl = document.createElement('div');
  targetEl.setAttribute('data-page-number', String(targetPage));
  setRect(targetEl, 500);

  // Pages 1..targetPage exist in the DOM (mirrors VirtualScrollReader mounting
  // every page container up front) so watchForShifts has something to observe.
  for (let p = 1; p <= targetPage; p++) {
    const el = p === targetPage ? targetEl : document.createElement('div');
    el.setAttribute('data-page-number', String(p));
    container.appendChild(el);
  }

  return { container, targetEl };
}

beforeEach(() => {
  FakeResizeObserver.instances = [];
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test('scrolls to the target page on mount', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);
  const onScrolled = vi.fn();

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
      onScrolled,
    })
  );

  expect(container.scrollTo).toHaveBeenCalledTimes(1);
  expect(onScrolled).toHaveBeenCalledWith(5);
});

test('re-aligns when a watched page resizes before the user scrolls', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  expect(container.scrollTo).toHaveBeenCalledTimes(1);

  const observer = FakeResizeObserver.instances[0];
  const page2 = container.querySelector('[data-page-number="2"]')!;
  fireResize(observer, page2);

  expect(container.scrollTo).toHaveBeenCalledTimes(2);
});

test('stops re-aligning the instant the user scrolls with the wheel, even if pages are still loading', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  expect(container.scrollTo).toHaveBeenCalledTimes(1);

  // The user tries to scroll away from the jumped-to page.
  container.dispatchEvent(new WheelEvent('wheel'));

  // A background page load resizes one of the watched pages afterwards --
  // this must NOT snap the view back to the target anymore.
  const observer = FakeResizeObserver.instances[0];
  const page2 = container.querySelector('[data-page-number="2"]')!;
  fireResize(observer, page2);

  expect(container.scrollTo).toHaveBeenCalledTimes(1);
});

test('stops re-aligning on touchmove', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  container.dispatchEvent(new TouchEvent('touchmove'));

  const observer = FakeResizeObserver.instances[0];
  const page2 = container.querySelector('[data-page-number="2"]')!;
  fireResize(observer, page2);

  expect(container.scrollTo).toHaveBeenCalledTimes(1);
});

test('stops re-aligning on a scroll-relevant key press', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  container.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown' }));

  const observer = FakeResizeObserver.instances[0];
  const page2 = container.querySelector('[data-page-number="2"]')!;
  fireResize(observer, page2);

  expect(container.scrollTo).toHaveBeenCalledTimes(1);
});

test('an unrelated key press does not cancel the settle window', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  container.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));

  const observer = FakeResizeObserver.instances[0];
  const page2 = container.querySelector('[data-page-number="2"]')!;
  fireResize(observer, page2);

  expect(container.scrollTo).toHaveBeenCalledTimes(2);
});

test('settles on its own after a quiet period with no resizes or user input', () => {
  vi.useFakeTimers();
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  const { result } = renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  expect(result.current.current).toBe(true);
  vi.advanceTimersByTime(300);
  expect(result.current.current).toBe(false);
});

test('is a no-op when the target already matches where the user is currently centered', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  const { rerender } = renderHook(
    ({ targetKey }: { targetKey: string }) =>
      useScrollToPage({
        containerRef: { current: container },
        getPageElement: () => targetEl,
        targetPage: 5,
        targetKey,
        currentCenterPage: 5,
      }),
    { initialProps: { targetKey: 'book-1:5' } }
  );

  expect(container.scrollTo).toHaveBeenCalledTimes(1);

  rerender({ targetKey: 'book-1:5-again' });

  expect(container.scrollTo).toHaveBeenCalledTimes(1);
});

test('stops re-aligning on user container scroll event', async () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  renderHook(() =>
    useScrollToPage({
      containerRef: { current: container },
      getPageElement: () => targetEl,
      targetPage: 5,
      targetKey: 'book-1:5',
    })
  );

  expect(container.scrollTo).toHaveBeenCalledTimes(1);

  // Allow programmatic scroll flag to settle
  await new Promise(r => setTimeout(r, 20));

  // Simulate user scroll via scrollbar / trackpad momentum
  container.dispatchEvent(new Event('scroll'));

  const observer = FakeResizeObserver.instances[0];
  const page2 = container.querySelector('[data-page-number="2"]')!;
  fireResize(observer, page2);

  expect(container.scrollTo).toHaveBeenCalledTimes(1);
});

test('scrolls on explicit jump (toc-jump:) even if targetPage matches currentCenterPage', () => {
  const { container, targetEl } = setUpContainerAndTarget('book-1', 5);

  const { rerender } = renderHook(
    ({ targetKey }: { targetKey: string }) =>
      useScrollToPage({
        containerRef: { current: container },
        getPageElement: () => targetEl,
        targetPage: 5,
        targetKey,
        currentCenterPage: 5,
      }),
    { initialProps: { targetKey: 'book-1:5' } }
  );

  expect(container.scrollTo).toHaveBeenCalledTimes(1);

  // Explicit toc jump to page 5 even though currentCenterPage is already 5
  rerender({ targetKey: 'toc-jump:book-1:5:123456789' });

  expect(container.scrollTo).toHaveBeenCalledTimes(2);
});

