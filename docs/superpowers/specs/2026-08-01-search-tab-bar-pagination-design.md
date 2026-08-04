# Search Tab Bar Pagination — UX & Design Spec

## Overview
This document specifies pagination for the Home Search Tab Bar (`SearchTabBar.tsx`). There are 10 fixed search tabs (`SEARCH_TABS` in `searchTabsConfig.ts`); today all 10 are rendered in a single horizontally-scrollable row with a hidden scrollbar. This spec replaces that scroll-to-discover pattern with explicit pagination so no more than a bounded set of tabs is shown per page, at any viewport width.

## Problem
- All 10 tabs render in one row; tabs beyond the visible width are only reachable by swiping/scrolling, which is not discoverable and doesn't scale as more tabs are added.
- Requirement: desktop view must show **at most 7 tabs** at once. The rest must be paginated, not merely scrollable.

## Design

### 1. Fixed-size pagination
- Tabs are split into fixed-size pages of **`PAGE_SIZE = 6`** content tabs each, computed from `SEARCH_TABS` (not a hardcoded list of keys), so the split adapts automatically if tabs are added/removed later.
- With the current 10 tabs:
  - **Page 1**: `ask, books, quran, content, dictionary, names` (6 tabs) + toggle control = 7 slots total (matches the 7-tab desktop cap).
  - **Page 2**: `history, proverbs, spell-check, en-ug` (4 tabs) + toggle control = 5 slots total.
- This pagination applies at **all viewport widths** (mobile included) — there is no separate "mobile keeps scrolling" behavior. Reaching tabs 7–10 always goes through the toggle, never through swipe/scroll discovery.

### 2. Toggle control (not a dropdown, not prev/next arrows)
- A single toggle button occupies the **last slot** in the row (visually leftmost, since the bar is RTL and tabs render right-to-left).
- **On page 1**: label is `t('common.more')` ("More") with a small hidden-count badge (e.g. "More · 4") and a chevron pointing further into the row (away from the start, i.e. `ChevronLeft` in RTL — consistent with the RTL-flipped chevron convention already used in `QuranView.tsx` / `ReferenceModal.tsx`).
- **On page 2**: label is `t('common.back')` ("Back") with the chevron reversed (`ChevronRight`), in the **same slot position** as "More" was, so the control doesn't visually jump when toggled.
- Visually styled as a distinct, neutral pill using the existing inactive-tab styling family (not styled like an active/selectable content tab, so it reads as a control rather than a destination).
- Clicking the toggle only changes which page of tabs is rendered — it never itself becomes the `activeTab` and never calls `onChange`.

### 3. State & persistence
- `SearchTabBar` owns a local `currentPage` state (`0 | 1`), private to the component.
- `currentPage` always initializes to `0` on mount. It is **not** synced to `activeTab` and **not** persisted (no localStorage, no auto-jump-to-page-containing-active-tab, no "active tab is hidden" indicator on the toggle). If the active tab is on page 2, the tab bar still opens on page 1; the user must click "More" to see it highlighted.
- Selecting a tab (`onChange`) behaves exactly as today — pagination is purely a rendering concern in `SearchTabBar` and does not change `HomeView`'s tab-selection logic or props.

### 4. Fallback safety net
- Each page's row keeps the existing `overflow-x-auto` + hidden-scrollbar styling (`[scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden`) as a graceful-degradation fallback only, in case a single page's tabs are ever too wide for an unusually narrow viewport. This is not the primary way to reach hidden tabs — pagination is.

## Out of Scope
- No dropdown/popover menu for overflow tabs.
- No numbered page indicators ("1 of 2") or dot indicators.
- No syncing of visible page to the currently active tab.
- No changes to `HomeView.tsx`'s tab state management or the visual style of individual tab buttons beyond adding the toggle control.

## Verification
1. On both desktop and mobile widths, confirm at most 7 slots (tabs + toggle) render on page 1.
2. Confirm clicking "More" swaps to the 4 remaining tabs plus a "Back" control in the same slot position.
3. Confirm clicking "Back" returns to page 1, and that the page always starts at page 1 on mount regardless of which tab is active.
4. Confirm selecting a tab (on either page) still calls `onChange` with the correct key and marks it active via `aria-pressed`.
5. Confirm the toggle control itself never receives `aria-pressed="true"` and never triggers `onChange`.
