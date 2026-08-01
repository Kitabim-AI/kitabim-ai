# Search Tab Bar Pagination Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Home Search Tab Bar's scroll-to-discover pattern with pagination, capping every page at a fixed set of tabs (6 content tabs + a toggle control = 7 slots max) instead of relying on horizontal swipe/scroll to reach hidden tabs.

**Architecture:** `SearchTabBar.tsx` gains a local `currentPage` state and a module-level `TAB_PAGES` array (the 10 `SEARCH_TABS` chunked into groups of 6). It renders only the tabs in `TAB_PAGES[currentPage]`, plus a single toggle button (label "More"/"Back") that flips between page 0 and the last page. No other files change behavior — `HomeView.tsx`'s tab-selection logic is untouched, and `searchTabsConfig.ts` keeps owning only tab metadata (order/icons/labels), not pagination.

**Tech Stack:** React 19, TypeScript, Vitest + Testing Library, existing `useI18n()` translation hook, Tailwind utility classes, `lucide-react` icons.

## Global Constraints

- Pagination applies at **every viewport width** — no separate "mobile keeps scrolling" behavior (per spec §1).
- Page size is **6 content tabs per page**, computed from `SEARCH_TABS.length` (not a hardcoded key list), so it adapts if tabs are added/removed later (per spec §1).
- The toggle control is a single button (not a dropdown, not prev/next arrow pair) occupying the last slot in the row; on page 1 it reads "More" with a hidden-tab count badge, on the last page it reads "Back", always in the same slot position (per spec §2).
- The toggle never sets `aria-pressed` and never calls `onChange` — it only changes local page state (per spec §2, §3).
- `currentPage` always starts at `0` on mount; it is not synced to `activeTab`, not persisted, and there is no "active tab is hidden" indicator (per spec §3).
- Per-page rows keep the existing hidden-scrollbar `overflow-x-auto` styling as a fallback only, not the primary navigation mechanism (per spec §4).
- No `print()`, no hardcoded user-visible strings — use `t("...")` from `useI18n()` (project-wide rule).
- Do not silently add machine-translated Uyghur copy — new Uyghur-facing strings default to an English placeholder pending the user's own review (per user's standing preference on this codebase).

---

### Task 1: Add the `common.more` translation key

**Files:**
- Modify: `apps/frontend/src/locales/en.json`
- Modify: `apps/frontend/src/locales/ug.json`

**Interfaces:**
- Produces: a `common.more` key resolvable via `t('common.more')` in both locale files, alongside the existing `common.back` key already present in both files.

- [ ] **Step 1: Add the English value**

In `apps/frontend/src/locales/en.json`, inside the `"common"` object, add a `"more"` key right after `"back"` (line 19):

```json
    "back": "Back",
    "more": "More",
```

- [ ] **Step 2: Add the Uyghur-locale placeholder**

In `apps/frontend/src/locales/ug.json`, find the `"common"` object's `"back"` entry and add a `"more"` key directly after it, using the same English text as a placeholder (per the global constraint above — do not machine-translate Uyghur copy unprompted):

```json
    "back": "قايتىش",
    "more": "More",
```

- [ ] **Step 3: Verify both files are valid JSON with the new key**

Run:
```bash
node -e "console.log(require('./apps/frontend/src/locales/en.json').common.more, require('./apps/frontend/src/locales/ug.json').common.more)"
```
Expected output: `More More`

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/locales/en.json apps/frontend/src/locales/ug.json
git commit -m "$(cat <<'EOF'
i18n: add common.more key for search tab pagination toggle

Uyghur value is an English placeholder pending translation review.
EOF
)"
```

---

### Task 2: Paginate `SearchTabBar` into fixed-size pages with a More/Back toggle

**Files:**
- Modify: `apps/frontend/src/components/library/SearchTabBar.tsx`
- Test: `apps/frontend/src/tests/components/library/SearchTabBar.test.tsx`

**Interfaces:**
- Consumes: `SEARCH_TABS: SearchTabDef[]`, `SearchTabDef` (`{ key: SearchTabKey; labelKey: string; icon: LucideIcon }`), and `SearchTabKey` from `./searchTabsConfig` (all already exported — no changes needed there). Consumes `t('common.more')` / `t('common.back')` added in Task 1.
- Produces: `SearchTabBar` keeps its existing public props (`activeTab: SearchTabKey`, `onChange: (tab: SearchTabKey) => void`) — no signature change for `HomeView.tsx`, which continues to call `<SearchTabBar activeTab={activeTab} onChange={setActiveTab} />` unmodified.

- [ ] **Step 1: Replace the test file with pagination-aware tests (this will fail against the current unpaginated component)**

Overwrite `apps/frontend/src/tests/components/library/SearchTabBar.test.tsx` with:

```tsx
import { SearchTabBar } from '@/src/components/library/SearchTabBar';
import { SEARCH_TABS } from '@/src/components/library/searchTabsConfig';
import { I18nContext } from '@/src/i18n/I18nContext';
import { fireEvent, render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

const i18nValue = {
  language: 'en' as const,
  setLanguage: vi.fn(),
  t: (key: string) => key,
};

const renderTabBar = (activeTab = 'ask') => {
  const onChange = vi.fn();
  render(
    <I18nContext.Provider value={i18nValue}>
      <SearchTabBar activeTab={activeTab as any} onChange={onChange} />
    </I18nContext.Provider>
  );
  return { onChange };
};

test('renders the first 6 tabs plus a page toggle on page 1', () => {
  renderTabBar();

  SEARCH_TABS.slice(0, 6).forEach((tabDef) => {
    expect(screen.getByText(tabDef.labelKey)).toBeInTheDocument();
  });
  SEARCH_TABS.slice(6).forEach((tabDef) => {
    expect(screen.queryByText(tabDef.labelKey)).not.toBeInTheDocument();
  });
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('common.more · 4');
});

test('marks the active tab as pressed', () => {
  renderTabBar('quran');
  expect(screen.getByText('home.tabs.quran').closest('button')).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByText('home.tabs.ask').closest('button')).toHaveAttribute('aria-pressed', 'false');
});

test('clicking a tab calls onChange with its key', () => {
  const { onChange } = renderTabBar('ask');
  fireEvent.click(screen.getByText('home.tabs.dictionary'));
  expect(onChange).toHaveBeenCalledWith('dictionary');
});

test('clicking the toggle swaps to page 2, revealing the remaining tabs with a back control', () => {
  renderTabBar();
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));

  SEARCH_TABS.slice(6).forEach((tabDef) => {
    expect(screen.getByText(tabDef.labelKey)).toBeInTheDocument();
  });
  SEARCH_TABS.slice(0, 6).forEach((tabDef) => {
    expect(screen.queryByText(tabDef.labelKey)).not.toBeInTheDocument();
  });
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('common.back');
});

test('clicking back on page 2 returns to page 1', () => {
  renderTabBar();
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));

  expect(screen.getByText('home.tabs.ask')).toBeInTheDocument();
  expect(screen.queryByText('home.tabs.enUg')).not.toBeInTheDocument();
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('common.more · 4');
});

test('selecting a tab on page 2 calls onChange correctly', () => {
  const { onChange } = renderTabBar();
  fireEvent.click(screen.getByTestId('search-tab-page-toggle'));
  fireEvent.click(screen.getByText('home.tabs.proverbs'));
  expect(onChange).toHaveBeenCalledWith('proverbs');
});

test('the page toggle never carries aria-pressed and never calls onChange', () => {
  const { onChange } = renderTabBar();
  const toggle = screen.getByTestId('search-tab-page-toggle');
  expect(toggle).not.toHaveAttribute('aria-pressed');
  fireEvent.click(toggle);
  expect(onChange).not.toHaveBeenCalled();
});

test('always starts on page 1 even when the active tab is on page 2', () => {
  renderTabBar('proverbs');
  expect(screen.getByText('home.tabs.ask')).toBeInTheDocument();
  expect(screen.queryByText('home.tabs.proverbs')).not.toBeInTheDocument();
  expect(screen.getByTestId('search-tab-page-toggle')).toHaveTextContent('common.more · 4');
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd apps/frontend && npx vitest run src/tests/components/library/SearchTabBar.test.tsx
```

Expected: several failures — e.g. `renders the first 6 tabs plus a page toggle on page 1` fails because all 10 tabs currently render and no element has `data-testid="search-tab-page-toggle"`.

- [ ] **Step 3: Implement pagination in `SearchTabBar.tsx`**

Replace the full contents of `apps/frontend/src/components/library/SearchTabBar.tsx` with:

```tsx
import React, { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';
import { SEARCH_TABS, SearchTabDef, SearchTabKey } from './searchTabsConfig';

interface SearchTabBarProps {
  activeTab: SearchTabKey;
  onChange: (tab: SearchTabKey) => void;
}

const TABS_PER_PAGE = 6;

const TAB_PAGES: SearchTabDef[][] = Array.from(
  { length: Math.ceil(SEARCH_TABS.length / TABS_PER_PAGE) },
  (_, pageIndex) => SEARCH_TABS.slice(pageIndex * TABS_PER_PAGE, (pageIndex + 1) * TABS_PER_PAGE)
);

export const SearchTabBar: React.FC<SearchTabBarProps> = ({ activeTab, onChange }) => {
  const { t } = useI18n();
  const [currentPage, setCurrentPage] = useState(0);

  const isLastPage = currentPage === TAB_PAGES.length - 1;
  const showToggle = TAB_PAGES.length > 1;
  const hiddenCount = TAB_PAGES.slice(currentPage + 1).reduce((sum, page) => sum + page.length, 0);

  const handleToggle = () => {
    setCurrentPage(isLastPage ? 0 : currentPage + 1);
  };

  return (
    <div className="w-full border-b border-slate-200 dark:border-slate-800 px-1" dir="rtl">
      <div
        className="flex items-end overflow-x-auto overflow-y-hidden gap-1 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
        dir="rtl"
      >
        {TAB_PAGES[currentPage].map(({ key, labelKey, icon: Icon }) => {
          const isActive = key === activeTab;

          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange(key)}
              aria-pressed={isActive}
              title={t(labelKey)}
              className={`flex items-center gap-2 px-3.5 sm:px-5 py-2.5 sm:py-3 transition-all duration-200 text-[13px] sm:text-[14px] whitespace-nowrap rounded-t-xl font-normal flex-shrink-0 active:scale-95 cursor-pointer ${
                isActive
                  ? 'bg-[#0369a1] dark:bg-[#38bdf8] text-white dark:text-slate-950 shadow-sm font-semibold'
                  : 'bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-b-0 border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200'
              }`}
            >
              <Icon size={16} strokeWidth={isActive ? 2.5 : 2} className="flex-shrink-0" />
              <span className="uyghur-text mt-[2px]">{t(labelKey)}</span>
            </button>
          );
        })}
        {showToggle && (
          <button
            type="button"
            data-testid="search-tab-page-toggle"
            onClick={handleToggle}
            title={isLastPage ? t('common.back') : t('common.more')}
            className="flex items-center gap-1.5 px-3.5 sm:px-5 py-2.5 sm:py-3 transition-all duration-200 text-[13px] sm:text-[14px] whitespace-nowrap rounded-t-xl font-normal flex-shrink-0 active:scale-95 cursor-pointer bg-white/80 dark:bg-slate-900/60 text-slate-600 dark:text-slate-400 border border-b-0 border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/80 hover:text-slate-800 dark:hover:text-slate-200"
          >
            {isLastPage ? (
              <ChevronRight size={16} strokeWidth={2} className="flex-shrink-0" />
            ) : (
              <ChevronLeft size={16} strokeWidth={2} className="flex-shrink-0" />
            )}
            <span className="uyghur-text mt-[2px]">
              {isLastPage ? t('common.back') : `${t('common.more')} · ${hiddenCount}`}
            </span>
          </button>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd apps/frontend && npx vitest run src/tests/components/library/SearchTabBar.test.tsx
```

Expected: all 8 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/components/library/SearchTabBar.tsx apps/frontend/src/tests/components/library/SearchTabBar.test.tsx
git commit -m "$(cat <<'EOF'
feat: paginate search tab bar into fixed 6-tab pages with More/Back toggle

Caps every page at 6 content tabs + a toggle control (7 slots max) at
all viewport widths, replacing scroll-to-discover for tabs 7-10.
EOF
)"
```

---

## Manual Verification (post-implementation)

1. Run `./deploy/local/rebuild-and-restart.sh frontend` and open http://localhost:30080.
2. Confirm the home search tab bar shows exactly 6 tabs (`Ask` through `Names`) plus a "More · 4" control.
3. Click "More" — confirm it swaps to `History Terms, Proverbs, Spell Check, EN↔UG` plus a "Back" control in the same position.
4. Click a tab on page 2 (e.g. Proverbs) — confirm it becomes active and the search results update as before.
5. Click "Back" — confirm it returns to page 1, and that the previously-selected page-2 tab is no longer visible but its selection state (if you reopen page 2) is still marked active.
6. Resize the browser to a narrow mobile width and repeat steps 2-5 to confirm the same paginated behavior (no reliance on swipe/scroll to reach hidden tabs).
