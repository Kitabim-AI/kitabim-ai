import { useEffect, useRef } from 'react';

interface UseScrollStabilizerOptions {
  containerRef: React.RefObject<HTMLElement>;
  itemsRef: React.RefObject<Map<number, HTMLElement>>;
  /** While true, resize events are observed (heights kept up to date) but scroll is not adjusted. */
  suppressedRef?: React.RefObject<boolean>;
  /** Include values here that mean the rendered item set changed (e.g. total page count), so the observer re-subscribes. */
  resubscribeKey?: unknown;
}

/**
 * Keeps the visually displayed content stationary while items above the
 * current viewport change height asynchronously (e.g. a loading placeholder
 * resolving to real content). Without this, growth above the viewport shifts
 * everything below it down by the same amount, which reads as the whole page
 * jumping while the user scrolls — CSS scroll anchoring alone doesn't reliably
 * catch this because the placeholder is a full element swap, not an in-place resize.
 */
export function useScrollStabilizer({ containerRef, itemsRef, suppressedRef, resubscribeKey }: UseScrollStabilizerOptions) {
  const heightsRef = useRef<Map<Element, number>>(new Map());

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new ResizeObserver(entries => {
      const containerTop = container.getBoundingClientRect().top;
      let delta = 0;

      entries.forEach(entry => {
        const target = entry.target;
        const newHeight = entry.contentRect.height;
        const prevHeight = heightsRef.current.get(target);
        heightsRef.current.set(target, newHeight);

        if (prevHeight === undefined || prevHeight === newHeight) return;
        if (suppressedRef?.current) return;

        const elTop = target.getBoundingClientRect().top;
        if (elTop + prevHeight <= containerTop) {
          delta += newHeight - prevHeight;
        }
      });

      if (delta !== 0) {
        container.scrollTop += delta;
      }
    });

    itemsRef.current.forEach(el => { if (el) observer.observe(el); });
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [containerRef, itemsRef, suppressedRef, resubscribeKey]);
}
