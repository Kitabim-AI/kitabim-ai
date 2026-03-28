# UI Code Review Skill — Kitabim AI Frontend

You are performing a code review on kitabim-ai frontend code. Review all changed files in `apps/frontend/src/`. Be direct and specific — cite file paths and line numbers. Distinguish blocking issues (must fix) from suggestions (nice to have).

---

## Review Checklist

Work through these categories in order. Skip categories that don't apply to the change.

---

### 1. Correctness

- [ ] No broken React imports (`import React from 'react'` required for JSX in this project)
- [ ] All props destructured in component signature match the declared `interface`
- [ ] `useEffect` cleanup functions are returned for all subscriptions, intervals, and observers (see `LibraryView.tsx` IntersectionObserver pattern)
- [ ] `useCallback` / `useEffect` dependency arrays are complete — no missing deps that would cause stale closures
- [ ] Async functions in `useEffect` are defined inside and called, not passed directly
- [ ] `authFetch` is used for all API calls — never raw `fetch` with manual auth headers
- [ ] `if (!res.ok) throw new Error(...)` present after every `authFetch` call that needs the result
- [ ] No state updates on unmounted components — cancelled flags or `useRef` guards are used where needed (see `AppContext.tsx` polling pattern)
- [ ] Portal modals use `createPortal(..., document.body)` and clean up `document.body.style.overflow` on unmount

---

### 2. i18n

- [ ] Zero hardcoded user-visible strings — every display string uses `t('key')` from `useI18n()`
- [ ] New translation keys are added to **both** `locales/ug.json` and `locales/en.json`
- [ ] Parameterised translations use `t('key', { param: value })` — not string concatenation
- [ ] `lang="ug"` and `dir="rtl"` are present on containers with Uyghur text content
- [ ] `uyghur-text` class is applied to Uyghur body text elements

---

### 3. State & Architecture

- [ ] No state that duplicates what's already in `useAppContext()` — check for overlap with `view`, `selectedBook`, `books`, `modal`, `chat`, `fontSize`, `activeTab`
- [ ] Navigation uses `setView()` from `useAppContext()` — not `window.location.href` or direct `history.pushState`
- [ ] API calls live in `services/` — components and hooks call service functions, not `authFetch` directly (exception: small one-off fetches in dedicated hooks)
- [ ] Hooks have a single concern and a typed return interface
- [ ] No prop drilling beyond 2 levels — shared state belongs in context
- [ ] Admin/editor-only UI is guarded with `useIsEditor()` or `useIsAdmin()`, matching the guard pattern in `App.tsx`

---

### 4. Design System Compliance

- [ ] **Primary colour** is `#0369a1` — not a Tailwind blue (e.g. `blue-600`) unless it matches exactly
- [ ] **Glass morphism** surfaces use `bg-white/80 backdrop-blur-xl` (cards) or `bg-white/90 backdrop-blur-2xl` (modals) — not solid white
- [ ] **Borders** use `border-[#0369a1]/10` (default) or `border-[#0369a1]/30` (hover) — not `border-gray-*`
- [ ] **Rounded corners** follow the scale: cards `rounded-2xl sm:rounded-3xl`, modals `rounded-[24px] sm:rounded-[32px] md:rounded-[40px]`, buttons `rounded-2xl`, pills `rounded-full`
- [ ] **Shadows** match: cards `shadow-md`, hover `shadow-[0_12px_24px_rgba(3,105,161,0.1)]`, modals `shadow-[0_32px_128px_rgba(0,0,0,0.3)]`
- [ ] **Transitions** use `transition-all duration-300` — not bare `transition` or custom durations unless intentional
- [ ] **Button press** has `active:scale-95` — tactile feedback on all interactive elements
- [ ] **Status badges** use the established colour pairs (`bg-*-50 text-*-600`) — not arbitrary colours
- [ ] No inline `style={{}}` for values that can be expressed as Tailwind utilities
- [ ] No magic spacing numbers — use Tailwind scale tokens; arbitrary values (`w-[300px]`) only when the design requires exact precision

---

### 5. Responsiveness & RTL

- [ ] All layouts are **mobile-first** — base classes target small screens, `sm:`/`md:`/`lg:` add larger-screen variants
- [ ] No hardcoded `px-*` values that would clip on small screens — use responsive padding
- [ ] **RTL-safe layout** — no `ml-*`/`mr-*` that assume LTR; use `gap-*` and `flex` instead; or use `ms-*`/`me-*` logical properties if needed
- [ ] Icon size responsive where relevant: small icon with `className="sm:hidden"` + larger with `className="hidden sm:block"`
- [ ] `dir="rtl"` present on all text containers; not only on the root `Shell` wrapper

---

### 6. Accessibility

- [ ] Every `<button>` without visible text has an `aria-label` or `title`
- [ ] Icon-only buttons have a descriptive `title` attribute
- [ ] `aria-hidden="true"` on purely decorative icons
- [ ] Loading spinners have `aria-label` or accompanying visible text
- [ ] Modal backdrops call `onClose` on click — keyboard users can dismiss with Escape (or note if not yet implemented)
- [ ] Interactive elements have focus-visible styles — not suppressed with `outline-none` without a replacement

---

### 7. TypeScript

- [ ] No `any` types unless wrapping genuinely unknown external data (flag for future typing)
- [ ] Props interfaces are defined inline, not inlined as object types in `React.FC<{...}>`
- [ ] No non-null assertions (`!`) without a comment explaining why it's safe
- [ ] Event handler types are correct (`React.MouseEvent`, `React.ChangeEvent<HTMLInputElement>`, etc.)
- [ ] Shared types imported from `@shared/types` — not redefined locally

---

### 8. Performance

- [ ] No object or array literals created inline in JSX props that would cause unnecessary re-renders (e.g. `style={{ color: 'red' }}` in a frequently-rendered list item)
- [ ] `useCallback` wraps functions passed as props to child components that are re-rendered on every parent render
- [ ] Expensive computations inside render are `useMemo`-ed if they depend on stable inputs
- [ ] `IntersectionObserver` and other DOM APIs are cleaned up in `useEffect` return (see `LibraryView.tsx`)
- [ ] No polling intervals left running after unmount

---

### 9. Testing

- [ ] New components and non-trivial hooks have at least one test
- [ ] Tests use `renderWithProviders` from `tests/test-utils.tsx` — never bare `render` from `@testing-library/react`
- [ ] Test assertions use translation **keys** (e.g. `'common.save'`), not translated strings — the i18n mock returns the key as-is
- [ ] `vi.spyOn` is used to mock service calls — no direct `fetch` mocking
- [ ] Tests clean up side effects (timers, mocks) with `afterEach` / `vi.restoreAllMocks()`

---

## How to Report

For each issue found, state:

1. **File and line** — e.g. `apps/frontend/src/components/library/BookCard.tsx:42`
2. **Severity** — `blocking` (incorrect behaviour, broken design, missing i18n) or `suggestion` (improvement, minor style drift)
3. **What's wrong** — one sentence
4. **How to fix** — concrete change or example snippet

Group issues by file. End with a brief overall verdict: **Approve**, **Approve with suggestions**, or **Request changes**.

---

## Saving the Report

After completing the review, write the report to:

```
docs/<branch-name>/code-review-ui-<YYYY-MM-DD>.md
```

1. Get the branch name: `git branch --show-current`
2. Use today's date in `YYYY-MM-DD` format.
3. Create the file with this structure:

```markdown
# UI Code Review — <YYYY-MM-DD>

**Branch:** <branch-name>
**Verdict:** Approve | Approve with suggestions | Request changes

## Issues

### `path/to/file.tsx`

- **[blocking]** Line 42 — What's wrong. How to fix.
- **[suggestion]** Line 87 — What's wrong. How to fix.

### `path/to/other.tsx`

- **[suggestion]** Line 12 — What's wrong. How to fix.

## Summary

<1–3 sentence summary of the overall state of the change.>
```

If no issues are found, the Issues section should say "No issues found."
