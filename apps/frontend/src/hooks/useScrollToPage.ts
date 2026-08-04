import { useEffect, useRef } from 'react';

interface UseScrollToPageOptions {
  containerRef: React.RefObject<HTMLElement>;
  getPageElement: (page: number) => Element | null | undefined;
  targetPage: number;
  /** Identifies a distinct jump request (e.g. `${bookId}:${page}`) — the same key is a no-op. */
  targetKey: string;
  topOffset?: number;
  onScrolled?: (page: number) => void;
}

const FIND_RETRY_MS = 40;
const FIND_MAX_ATTEMPTS = 15;
const SETTLE_QUIET_MS = 250;

/**
 * Scrolls a container to bring a target page element to `topOffset` from the top,
 * then keeps it aligned while nearby unloaded pages resolve to real content and
 * change height (a ResizeObserver on the pages up to the target, not a fixed
 * number of timed retries, decides when the layout has actually settled).
 *
 * Returns a ref that is true while a scroll/settle sequence for the current
 * target is in flight, so callers can suppress their own scroll-position
 * tracking during that window.
 */
export function useScrollToPage({
  containerRef,
  getPageElement,
  targetPage,
  targetKey,
  topOffset = 24,
  onScrolled,
}: UseScrollToPageOptions) {
  const isScrollingRef = useRef(false);
  const lastKeyRef = useRef<string | null>(null);

  const getPageElementRef = useRef(getPageElement);
  getPageElementRef.current = getPageElement;
  const onScrolledRef = useRef(onScrolled);
  onScrolledRef.current = onScrolled;

  useEffect(() => {
    if (lastKeyRef.current === targetKey) return;

    let cancelled = false;
    let findTimer: ReturnType<typeof setTimeout>;
    let quietTimer: ReturnType<typeof setTimeout>;
    let attempts = 0;
    let resizeObserver: ResizeObserver | null = null;

    const alignToTarget = (el: Element) => {
      const container = containerRef.current;
      if (!container) return;
      const containerTop = container.getBoundingClientRect().top;
      const elTop = el.getBoundingClientRect().top;
      container.scrollTo?.({
        top: container.scrollTop + (elTop - containerTop) - topOffset,
        behavior: 'instant',
      });
    };

    const stopSettling = () => {
      resizeObserver?.disconnect();
      resizeObserver = null;
      clearTimeout(quietTimer);
      isScrollingRef.current = false;
    };

    // Pages up to the target render as placeholders until their content fetch
    // resolves, which can land just after this jump and change their height —
    // silently pushing the target out of view. Re-align whenever one of them
    // actually resizes, and stop once nothing has changed for a quiet period.
    const watchForShifts = (el: Element) => {
      const container = containerRef.current;
      if (!container) return;

      resizeObserver = new ResizeObserver(() => {
        if (cancelled) return;
        alignToTarget(el);
        clearTimeout(quietTimer);
        quietTimer = setTimeout(stopSettling, SETTLE_QUIET_MS);
      });

      container.querySelectorAll('[data-page-number]').forEach((node) => {
        const pageNum = Number(node.getAttribute('data-page-number'));
        if (pageNum > 0 && pageNum <= targetPage) resizeObserver!.observe(node);
      });

      quietTimer = setTimeout(stopSettling, SETTLE_QUIET_MS);
    };

    const tryFind = () => {
      if (cancelled) return;
      const el = getPageElementRef.current(targetPage);
      const container = containerRef.current;
      if (el && container) {
        lastKeyRef.current = targetKey;
        isScrollingRef.current = true;
        alignToTarget(el);
        onScrolledRef.current?.(targetPage);
        watchForShifts(el);
      } else if (attempts < FIND_MAX_ATTEMPTS) {
        attempts++;
        findTimer = setTimeout(tryFind, FIND_RETRY_MS);
      }
    };

    tryFind();

    return () => {
      cancelled = true;
      clearTimeout(findTimer);
      stopSettling();
    };
  }, [targetKey, targetPage, containerRef, topOffset]);

  return isScrollingRef;
}
