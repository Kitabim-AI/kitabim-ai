# Spell Check UI — Feature Spec & Rewrite Plan

> **v3** — Updated with 4 product decisions: no reader sync from standalone view, book metadata in reader tab, no auto-rescan after correction, active-finding context refresh + scroll-to.
> Source of truth for a full UI rewrite. Backend unchanged.

---

## Overview

The spell check feature is a **quality-assurance tool for editors**. It surfaces OCR errors in digitized Uyghur books and lets editors apply corrections, ignore false positives, or skip unknowns. It exists in **three distinct surfaces**:

1. **Standalone Spell Check View** — dedicated full-page workspace (`/spell-check` route, `SpellCheckView.tsx`)
2. **Reader Sidebar — Spell Check Tab, desktop** — spell check tab visible side-by-side with the reader (`ReaderView.tsx`, desktop xl+)
3. **Reader Sidebar — Spell Check Tab, mobile** — spell check tab active, reader not visible (`ReaderView.tsx`, mobile)

All three surfaces share `SpellCheckPanel` as their core component.

Access is restricted to users with **editor or admin roles**. Readers and unauthenticated users see a sign-in prompt.

---

## Design System Reference

The rewrite must follow the app's existing design language precisely. Key tokens:

### Colors
| Role | Value | Usage |
|---|---|---|
| Primary | `#0369a1` | Buttons, active tabs, icons, borders |
| Primary hover | `#0284c7` | Button hover state |
| Primary light | `bg-[#0369a1]/10` | Tab inactive bg, badge bg, input border |
| Text primary | `#1a1a1a` | Body text |
| Text muted | `#94a3b8` | Labels, counts, secondary info |
| Text placeholder | `#64748b` | Input placeholders |
| Error red | `text-red-500 bg-red-50` | Flagged words, error alerts |
| Success emerald | `text-emerald-500 bg-emerald-50` | "All clean" state |
| Warning amber | `text-amber-500 bg-amber-50` | Network errors (new) |

### Border Radius
| Size | Class | Use |
|---|---|---|
| Icon button | `rounded-xl` | Small icon-only controls |
| Action button / input | `rounded-2xl` | Standard buttons, inputs |
| Panel / card | `rounded-3xl` or `rounded-[32px]` | Issue cards, main panels |
| Large container | `rounded-[40px]` | Outer glass panel wrapper |

### Glass Panel
Use the existing `.glass-panel` utility class for the outer container:
```
bg: rgba(255,255,255,0.8)
backdrop-filter: blur(20px) saturate(180%)
border: 1px solid rgba(255,193,7,0.15)
box-shadow: 0 4px 16px rgba(3,105,161,0.1), ...
```

### Buttons

**Primary (solid blue):**
```
bg: linear-gradient(135deg, #0369a1, #0284c7)
text-white
shadow-lg shadow-[#0369a1]/20
hover: hover:shadow-xl hover:-translate-y-0.5
active: active:scale-95
disabled: disabled:opacity-40
```

**Secondary (ghost blue):**
```
bg-[#0369a1]/10 text-[#0369a1]
hover:bg-[#0369a1] hover:text-white
rounded-2xl
```

**Destructive:**
```
bg-slate-50 text-slate-400
hover:bg-red-50 hover:text-red-500
rounded-2xl
```

### Tab Pattern (Active / Inactive)
```
Active:   bg-[#0369a1] text-white shadow-lg
Inactive: bg-[#0369a1]/10 text-[#0369a1]
```

### Scrollbar
Use `custom-scrollbar` class for scrollable areas.

### Animations
- Entrance: `animate-fade-in`
- Spinner: `animate-spin` with `border-t-[#0369a1]` ring style
- Pulse: `animate-pulse` on loading text
- Bounce dots: for alternative loading state

### RTL & Typography
- Always `dir="rtl" lang="ug"` on the outer container
- Uyghur text content: `uyghur-text` class + `style={{ fontSize: \`\${fontSize}px\` }}`
- Headers: `fontSize + 4`
- Labels: fixed `text-xs` or `text-sm`, `font-bold`, `uppercase`

---

## Three Surfaces, Three Navigation Models

> **Critical distinction** — there are three distinct surfaces with different post-review behaviors. They must not be conflated.

---

### Surface A — Spell Check Page (Standalone)

**Context:** User navigates to `/spell-check` from the navbar. No reader is visible.

- Fetches a random book with open issues automatically
- Tracks `pagesWithIssues[]` — only pages with open issues
- **When current page is fully reviewed:** automatically navigates to the next page in `pagesWithIssues[]`. No message, no wait — silent advance.
- **When book is fully reviewed:** auto-fetches a new book
- No reader sync. Fully independent.
- `navigationMode='auto'`

---

### Surface B — Spell Check Tab + Reader Tab, Side by Side (Desktop)

**Context:** User is in the reader on desktop (xl+). Both the reader panel and the right sidebar are visible simultaneously. User switches the sidebar to the "Spell Check" tab.

- Tied to the reader's `currentPage`
- Reader drives page navigation — the user turns pages in the reader panel
- **When current page is fully reviewed:** show "All issues reviewed" message on the spell check tab. **Do not auto-navigate.** The user is reading and controls paging themselves.
- When the reader navigates to a new page → spell check tab reloads issues for that page
- Correcting a word updates the reader's live text immediately
- Shows book metadata (title, author) in the panel header
- `navigationMode='reader-driven'`

---

### Surface C — Spell Check Tab Only, No Reader Tab (Mobile)

**Context:** User is in the reader on mobile. The mobile tab switcher shows "Reader" | "Chat" | "Spell Check". User taps "Spell Check" — the reader is no longer visible.

- Tied to the reader's `currentPage`
- **When current page is fully reviewed:** show "All issues reviewed — swipe to go to next page" message. Enable swipe up/down gestures to navigate.
- **When current page was always clean:** show "No issues on this page — swipe to go to next page" message. Enable swipe gestures.
- **Swipe is only enabled when there are no remaining open issues on the page.** If issues exist, swipe does nothing (user must resolve them first).
- Swipe up → next page; swipe down → previous page
- Correcting a word updates the reader's live text immediately
- Shows book metadata in the panel header
- `navigationMode='swipe'`

---

### Comparison: What Happens When Page Is Fully Reviewed

| Surface | After all issues resolved | Page navigation |
|---|---|---|
| A — Standalone | Auto-advance to next issue page silently | Automatic |
| B — Sidebar + Reader (desktop) | Show "All reviewed" message, stay on page | User turns pages in reader |
| C — Sidebar only (mobile) | Show "All reviewed — swipe to next" message, enable swipe | User swipes in spell check tab |

---

## Component Architecture

### `SpellCheckView.tsx`
Container for Surface A. Owns: book fetch, `pagesWithIssues[]`, `currentPage`, `pageText`.
No longer syncs `currentPage` to the reader context.

### `SpellCheckPanel.tsx`
Core issue-resolution UI. Used in all three surfaces. **This is the component being rewritten.**

**Props:**
```ts
type NavigationMode =
  | 'auto'           // Surface A: auto-advance to next issue page when page is done
  | 'reader-driven'  // Surface B: show "reviewed" message, don't navigate (reader controls pages)
  | 'swipe'          // Surface C: show "swipe to next" message, enable swipe gestures

interface SpellCheckPanelProps {
  pageNumber: number
  totalPages: number
  pageText?: string          // locally-maintained page text (kept up to date after corrections)
  fontSize: number
  issues: SpellIssue[]
  isLoading: boolean         // fetching issues from API
  isScanning: boolean        // running manual rescan
  hasLoaded: boolean         // initial load has completed at least once
  navigationMode?: NavigationMode  // default: 'reader-driven'
  onRescan: () => void
  onApplyCorrection: (issueId: number, word: string, options?: { isPhrase?: boolean; range?: [number, number] }) => void
  onIgnoreIssue: (issueId: number) => void
  onNextPage: () => void   // called by panel only in 'auto' mode; in 'swipe' mode called on swipe gesture
  onPrevPage: () => void   // called by panel only in 'swipe' mode on swipe gesture
  // Surface A only: progress indicator
  currentIssuePageIndex?: number
  totalIssuePages?: number
  // Surfaces B & C: book metadata for panel header
  bookTitle?: string
  bookAuthor?: string | null
  bookVolume?: number | null
}
```

**How `ReaderView` determines the mode:**
```ts
// Desktop (xl+): reader and sidebar both visible → reader-driven
// Mobile: spell check tab active, reader not visible → swipe
const navigationMode = isMobile ? 'swipe' : 'reader-driven'
```

### `useSpellCheck.ts`
Manages API calls and local issue state. **One change required:** reset `hasLoaded` and `issues` at the start of `loadIssues()` so stale issues from the previous page never flash (Bug 4 fix).

**Post-correction flow (decision 3):** After applying a correction, the hook removes the issue from local state and the parent updates `pageText` locally. `loadIssues()` is **not** called again. The rescan (`triggerRecheck`) remains available only as a manual editor action.

---

## Data Model

### `SpellIssue`
```ts
{
  id: number
  word: string               // flagged word (already normalized by backend)
  char_offset: number | null // byte position in page.text where word starts
  char_end: number | null    // byte position where word ends
  ocr_corrections: string[]  // suggested corrections (always non-empty — backend only creates issues with viable corrections)
  status: 'open' | 'corrected' | 'ignored'
}
```

**Important:** The backend only creates a `PageSpellIssue` when a word has at least one viable dictionary correction. An issue with an empty `ocr_corrections[]` should not occur in practice.

### `spell_check_milestone` values
`idle` → `in_progress` → `done` / `error` / `skipped`

---

## All User Scenarios

---

### S1 — Initial Book Load

**Trigger:** User opens Spell Check View (or clicks "Next Book")
**State:** `isLoadingBook=true`, `bookMeta=null`
**UI:** Full-panel centered loading state
- Spinner (border ring + inner icon style, `text-[#0369a1]`)
- Pulsing label: `t('spellCheck.loadingBook')` — uppercase, `text-slate-400`
**Outcome:** → S2 (no books) or → S3 (book found)

---

### S2 — No Books With Issues ("All Clean")

**Trigger:** `/api/books/spell-check/random-book` returns 404
**State:** `bookError=true`
**UI:** Full-panel centered empty state
- Large `BookOpenCheck` icon in `bg-emerald-50 text-emerald-400 rounded-[40px] p-8`
- Title: `t('spellCheck.noBooks')` — `text-[#1a1a1a] text-lg font-normal`
- Detail: `t('spellCheck.noBooksDetail')` — `text-slate-400 text-sm`
- "Next Book" button (primary blue, retry)

**⚠ Accuracy note:** This state is also reached after a genuine API/network error. These two cases must be differentiated:

| Case | Icon | Color | Action |
|---|---|---|---|
| All books clean (404) | `BookOpenCheck` | emerald | "Check back later" (no retry) |
| Network / server error (5xx) | `AlertCircle` | amber | "Retry" button |

*New locale key needed:* `spellCheck.loadError` — "Could not connect. Please try again."

---

### S3 — Book Loaded, Loading Page Issues

**Trigger:** `bookMeta` set, `currentPage` = `first_issue_page`
**State:** `isLoading=true`, `hasLoaded=false`
**UI:** Full-panel centered loading spinner + `t('spellCheck.analyzing')` label
**Outcome:** → S4 (issues found) or → S6 (page is clean)

**⚠ Accuracy note:** `hasLoaded` is NOT reset between page navigations (it stays `true` from the previous page). On first load, this correctly shows the spinner. On subsequent page changes, `isLoading=true` is the signal — the panel must use `isLoading && !hasLoaded` to decide whether to show the full-panel spinner vs. inline loading.

---

### S4 — Issues Displayed

**Trigger:** `hasLoaded=true`, `issues.length > 0`, `!isBusy`

**UI structure — one active finding at a time:**
```
┌─ Panel header ──────────────────────────────────────────────┐
│  [Book title / Page N]    [Page M/N pages]  [↑] [↓]  [↺]  │
└─────────────────────────────────────────────────────────────┘
┌─ Finding stepper ───────────────────────────────────────────┐
│  [←]   Finding 2 of 4   [→]                                │
└─────────────────────────────────────────────────────────────┘
┌─ Active finding card ───────────────────────────────────────┐
│  [Context section — scrollable, word centered]  [Edit]      │
│  ─────────────────────────────────────────────────────────  │
│  [OCR suggestion buttons]                                   │
│  [Manual input field]                    [Apply]            │
│  [Later]  ─────────────────────────  [Not an Error]        │
└─────────────────────────────────────────────────────────────┘
```

**Panel header by surface:**
- **Surface A:** Left = page progress badge `N/M pages with issues`; Right = `↑` prev page, `↓` next page, `↺` rescan
- **Surface B:** Left = book title + author; Right = page number, `↺` rescan (no nav buttons — reader controls pages)
- **Surface C:** Left = book title + author; Right = page number, `↺` rescan (no nav buttons — swipe only)

**Finding stepper:**
- Shows `Finding X of Y` where Y = total issues on this page (including skipped)
- `←` / `→` to jump between findings without resolving (for review before acting)
- Hidden when there is only 1 finding on the page (arrows are meaningless)
- When a skipped finding is reached via `←`/`→`, the card shows a muted "Skipped" state with an "Undo" button — the action buttons (OCR suggestions, input, Skip/Ignore) are replaced
- Non-skipped count shown separately if any are skipped: e.g., "Finding 2 of 4 (1 skipped)"

---

### S4a — Active Finding & Context Display

**One finding at a time.** The panel shows a single "active" issue. The user resolves it (apply / ignore / skip), then the next issue automatically becomes active. A stepper shows position within the page (`1 / 4`).

**Active finding changes when:**
- User applies a correction → next issue in list becomes active
- User ignores → next issue becomes active
- User skips → issue is deferred; next non-skipped issue becomes active
- User taps stepper `←` / `→` arrows to manually navigate between issues

**On each activation, context is re-extracted from the current local `pageText`**, which reflects all corrections applied so far in this session. This guarantees the context is always accurate — no server round-trip needed.

**Context extraction (`extractContext()`):**
- Reads `char_offset` / `char_end` from the active issue (already shifted by `updateLocalOffsets` after each prior correction)
- Extracts ~20 tokens before and after from `pageText`
- Run on every active-issue change (cheap — pure string operation)

**Rendered context:**
- **Before text:** `text-[#1a1a1a] uyghur-text`
- **Flagged word:** `text-red-500 font-semibold bg-red-50 px-0.5 rounded`
- **After text:** `text-[#1a1a1a] uyghur-text`
- Container: `uyghur-text`, `style={{ fontSize }}`, `leading-loose`, `whitespace-pre-wrap`, `dir="rtl"`, `overflow-y-auto`

**Scroll-to (locate the word):** When the active issue changes, scroll the context container so the highlighted word is vertically centered. Attach a `ref` to the highlighted `<span>` and call `scrollIntoView({ block: 'center', behavior: 'smooth' })` inside a `useEffect([activeIssueId])`.

**Fallback states:**

| Condition | What to show |
|---|---|
| `pageText` undefined (still loading) | Skeleton shimmer — 2 lines at `fontSize` height, prevents layout shift |
| `pageText` loaded but offset is null | Word only in `text-red-500 font-semibold`, no surrounding context |
| `charEnd > pageText.length` | Same as null fallback + console warning (stale offset) |
| `charOffset === charEnd` | Render `issue.word` directly |

**Edit button:** top-right of context section, secondary ghost style, label: `t('common.edit')`. Opens → S4e.

---

### S4b — OCR Suggestion Buttons

**Condition:** `issue.ocr_corrections.length > 0` (always true per backend guarantee)
**Layout:**
- Label row: `t('spellCheck.suggestion')` — `text-xs font-bold text-slate-300 uppercase`
- Buttons: one per correction
  - Desktop (≥640px): stacked vertically, full-width
  - Mobile (<640px): horizontal scroll row (`flex flex-row overflow-x-auto gap-2 pb-1`)
- Button style: primary gradient, `uyghur-text`, correction word left + `Check` icon right
- On click → `onApplyCorrection(id, correction, { range: [char_offset, char_end] })`

**If multiple suggestions (>3):** Show first 3, rest collapsed under a "Show more" toggle.

---

### S4c — Manual Correction Input

**Always shown** when not in phrase edit mode.
- RTL `<input>` + "Apply" button (primary, disabled when empty)
- `placeholder={t('spellCheck.typeCorrection')}`
- `onKeyDown: Enter → handleCustomApply()`
- Uses `{ range: [char_offset, char_end] }` if offset exists, otherwise plain correction

---

### S4d — Skip / Ignore Actions

**Visual treatment (new proposal):**

| Action | Label (UG) | Label (EN) | Icon | Style | Persistence |
|---|---|---|---|---|---|
| Skip | كېيىن (Later) | Later | `Clock` | Destructive ghost | Local only |
| Ignore | خاتالىق ئەمەس | Not an Error | `X` | Destructive ghost | Saved to DB |

**Skip behavior (accuracy fix):**

> **⚠ Bug in current implementation:** `orderedIssues` is computed as:
> ```ts
> const orderedIssues = [
>   ...issues.filter(i => !skippedIds.includes(i.id)),
>   ...issues.filter(i =>  skippedIds.includes(i.id)),  // this half...
> ].filter(i => !skippedIds.includes(i.id));             // ...is immediately filtered out
> ```
> Skipped issues are **completely removed from view**, not moved to the bottom.
> The spec previously said "moves to end of list" — that is incorrect.

**Correct behavior for rewrite (single-finding model):**
- Skipping a finding advances to the next non-skipped finding in the stepper
- The skipped finding remains reachable via `←`/`→` stepper navigation
- When navigated to, the skipped finding shows a muted "Skipped" state card — OCR suggestions and action buttons are replaced by a single "Undo" button
- Auto-advance to S6/S7 triggers when all non-skipped findings are resolved (skipped findings do not block advancement)

**Ignore semantics:**
- Always confirm the distinction visually — ignore means "this word is correct, don't flag it again"
- Consider a subtle tooltip: `title={t('spellCheck.ignoreTooltip')}`

*New locale key:* `spellCheck.ignoreTooltip` — "Mark as correct — won't be flagged again"
*New locale key:* `spellCheck.skipLater` — "كېيىن" / "Later"
*New locale key:* `spellCheck.undoSkip` — "ئەمەس" / "Undo"

---

### S4e — Phrase Edit Mode

**Trigger:** Click "Edit" on context section
**UI:**
- Replaces context section with a `<textarea>`
- Pre-filled with `${ctx.before}${ctx.word}${ctx.after}` (exact string, no `.trim()`)
- `min-h` on mobile: `120px` not `300px` (current 300px is too tall)
- `min-h` on desktop: `160px`
- `class="uyghur-text border-2 border-[#0369a1]/30 focus:border-[#0369a1] rounded-2xl"`
- Apply + Cancel buttons below
- OCR suggestions and manual input are hidden while editing phrase

**When phrase edit is applied:**
- Calls `onApplyCorrection(id, newVal, { isPhrase: true, range: [contextStart, contextEnd] })`
- Parent updates `pageText` for the replaced range
- Parent calls `updateLocalOffsets(contextEnd, diff)`

**⚠ Accuracy note (Phrase edit + overlapping offsets):**

If two issues are close enough that their context windows overlap, applying a phrase edit for Issue A will corrupt Issue B's `char_offset` if Issue B falls within `[contextStart_A, contextEnd_A]`.

`updateLocalOffsets(contextEnd, diff)` only shifts issues **after** `contextEnd`. Issues **inside** the context window keep their original offsets, which are now wrong because the text in that range was replaced.

**Recommended mitigation for rewrite:**
After any phrase edit, re-fetch issues for the page (`loadIssues()`) instead of relying on predictive offset shifting. The rescan is fast (the data is already in DB). Only use predictive shifting for word-level (non-phrase) corrections.

---

### S5 — Rescanning (Triggered Recheck)

**Trigger:** User clicks rescan button in panel header
**State:** `isScanning=true`

| Issues visible? | UI behaviour |
|---|---|
| No issues yet | Full-panel spinner + `t('spellCheck.rescanning', { page })` |
| Issues visible | Issue cards remain; rescan button shows `animate-spin`; all action buttons disabled |

**Outcome:** `isScanning → false` → fresh page text fetched → `loadIssues()` → S3 or S4

---

### S6 — Page Has No Remaining Issues

**Trigger:** `hasLoaded=true`, `issues.length === 0`, `!isBusy`

**Message shown (by reason):**

| Reason | Message key |
|---|---|
| Applied a correction | `spellCheck.applied` |
| Ignored an issue | `spellCheck.ignored` |
| All skipped | `spellCheck.skipped` |
| Page was always clean | `spellCheck.noErrors` |

**Icon style:**
- Page was always clean / all fully resolved: `bg-emerald-50 text-emerald-500`
- Some skipped (work deferred): `bg-slate-50 text-slate-400`

**Then, behavior differs by `navigationMode`:**

#### `navigationMode='auto'` (Surface A — Standalone)
No message shown. Panel immediately calls `onNextPage()` → auto-advances to next issue page in `pagesWithIssues[]`. If no more pages, fetches a new book.

#### `navigationMode='reader-driven'` (Surface B — Desktop sidebar)
Shows message + checkmark icon. **No navigation hint, no auto-advance.** The message stays visible until the reader navigates to a different page, at which point the spell check tab reloads for the new page.

*Example: "تۈزىتىلدى" / "Corrected" — with a static checkmark, no "swipe" or "moving to next" text.*

#### `navigationMode='swipe'` (Surface C — Mobile tab only)
Shows message + checkmark icon + **swipe instruction**.

- If issues were just resolved: `t('spellCheck.reviewedSwipe')` — "All reviewed — swipe to go to next page"
- If page was always clean: `t('spellCheck.cleanSwipe')` — "No issues on this page — swipe to go to next page"

Swipe up → `onNextPage()`, swipe down → `onPrevPage()`. Swipe gestures are **only active in this state** (no remaining issues). If issues exist, swipe is disabled.

*New locale keys:*
- `spellCheck.skipped` — "يوچۇن قويۇلدى" / "Skipped for now"
- `spellCheck.reviewedSwipe` — "بارلىق تۈزىتىشلەر تامام — كېيىنكى بەتكە سىيرىلىڭ" / "All reviewed — swipe to next page"
- `spellCheck.cleanSwipe` — "بۇ بەتتە خاتالىق يوق — كېيىنكى بەتكە سىيرىلىڭ" / "No issues — swipe to next page"

---

### S7 — Auto-Advance to Next Issue Page (Standalone)

**Trigger:** Current page resolved, more entries remain in `pagesWithIssues[]`
**Action:** `setCurrentPage(pagesWithIssues[idx + 1])`

**⚠ Accuracy note (Stale closure after apply):**

In `SpellCheckView.onApplyCorrection`:
```tsx
if (spellCheck.issues.length === 0) {
  setPagesWithIssues(prev => prev.filter(p => p !== currentPage));
}
```

`spellCheck.issues.length` is read synchronously after the `await applyCorrection()` call. However, `applyCorrection()` calls `setIssues(prev => prev.filter(...))` — a React state update. The new state is NOT immediately available on `spellCheck.issues.length` in this closure.

**Result:** `pagesWithIssues` may not be cleaned up when the last issue on a page is applied, causing the user to revisit a now-clean page.

**Recommended fix for rewrite:** Track cleanup inside a `useEffect` watching `issues.length`, not in the apply handler.

---

### S8 — All Issues in Book Resolved (Standalone)

**Trigger:** `currentPage` was the last in `pagesWithIssues[]`
**Action:** `fetchRandomBook()` → back to S1

---

### S9 — Page Navigation by Surface

**Surface A — Standalone (`navigationMode='auto'`):**
- Panel header has explicit `↑` / `↓` icon buttons
- `↑` (prev): jump to `pagesWithIssues[idx - 1]`; if at start, sequential -1
- `↓` (next): jump to `pagesWithIssues[idx + 1]`; if at end, sequential +1
- Swipe gestures are **not the primary nav** here — buttons are. Swipe can be kept as a secondary gesture but is not required.

**Surface B — Desktop sidebar, reader visible (`navigationMode='reader-driven'`):**
- The spell check panel has **no page navigation controls** — it shows no prev/next buttons
- The user navigates pages using the reader (the large panel to the left)
- When reader changes page, spell check tab reloads automatically
- Rescan button `↺` is the only control in the header alongside book metadata

**Surface C — Mobile tab only (`navigationMode='swipe'`):**
- **No on-screen navigation buttons** — navigation is swipe-only
- Swipe up → `onNextPage()` (next page)
- Swipe down → `onPrevPage()` (previous page)
- **Swipe is gated: only active when `issues.length === 0`** — if any unresolved issues remain, swipe does nothing
- The "swipe to next page" instruction message (S6) is the visual cue that swipe is now enabled

---

### S10 — Predictive Offset Shifting (Word Corrections)

**Trigger:** Word-level correction applied (`!isPhrase`, `range` provided)
**Action:** `updateLocalOffsets(charEnd, correctedWord.length - (charEnd - charOffset))`
**Effect:** Remaining issues' offsets shift by the word-length delta — no re-fetch needed.

**Scope:** Only applies to word corrections. Phrase edits should trigger a fresh `loadIssues()` instead (see S4e accuracy note).

---

### S11 — Post-Correction Flow (No Auto-Rescan)

After a correction is applied, the following happens **locally only** — no re-fetch, no rescan:

1. **Remove issue from list:** `setIssues(prev => prev.filter(i => i.id !== issueId))`
2. **Update `pageText` in place:**
   - Word correction: `newText = pageText.slice(0,start) + correctedWord + pageText.slice(end)`
   - Phrase correction: `newText = pageText.slice(0,ctxStart) + newVal + pageText.slice(ctxEnd)`
3. **Shift remaining offsets:** `updateLocalOffsets(charEnd, lengthDiff)` for word corrections. Phrase corrections call `loadIssues()` instead (see Bug 3 fix).
4. **Activate next finding:** The next issue in the list becomes active; its context is re-extracted from the newly updated `pageText` and scrolled into view.
5. **Reader sync (Surface B only):** `setLoadedPages` updated so the reader view reflects the corrected text immediately.

**`loadIssues()` is never called automatically after a correction.** The rescan button (`↺`) is the only way to re-run spell check — it is a deliberate editor action.

**Rationale:** A correction doesn't create new issues. The remaining issues' words and positions (after offset shifting) are still valid. A full re-fetch would be wasteful and would flash a loading state unnecessarily.

---

### S12 — Page Text Refresh After Rescan

**Trigger:** `isScanning` transitions `true → false`
**Action:** Re-fetch `pageText` from API
**Why:** Inline rescan modifies DB text; local `pageText` (post-corrections) may be out of sync.

---

### S13 — Same Book Open in Reader (Standalone)

**Trigger:** `selectedBook.id === data.book_id` when fetching random book
**Behavior:** Start from nearest issue page at or after `readerPage` so the editor continues from where they were reading, rather than jumping to `first_issue_page`.
**No ongoing sync:** After this initial page selection, the standalone spell check view navigates independently. It does not update the reader's position as it moves through issues. The two views are decoupled.

---

### S14 — Access Denied

**Trigger:** Non-editor/admin accesses Spell Check View
**UI:** Centered `t('auth.signInMessage')` — `text-slate-400 font-normal` at `fontSize`
**Panel is not rendered**

---

### S15 — Book-Level Trigger (Admin, not in this panel)

Admin-only action on a separate admin UI. Resets all pages to `spell_check_milestone='idle'` for background reprocessing. Not part of the SpellCheckPanel scope.

---

### S-NEW-1 — Progress Indicator (New Feature)

**Where:** Panel header, left of nav buttons
**Content (Standalone):** `t('spellCheck.pageProgress', { current: idx+1, total: pagesWithIssues.length })`
- Displayed as a badge: `bg-[#0369a1]/10 text-[#0369a1] rounded-2xl px-3 py-1 text-xs font-bold`
- Example: "۳/۷ بەت" ("Page 3/7")

**Content (Reader tab):** Show page number only — `t('chat.pageNumber', { page: pageNumber })` (already exists)

*New locale key:* `spellCheck.pageProgress` — "Page {{current}} of {{total}}" / "{{current}}/{{total}} بەت"

---

### S-NEW-2 — Active Finding Skeleton While pageText Loads

**Trigger:** Issues are loaded (`hasLoaded=true`) but `pageText` is still undefined
**UI:** The active finding card renders with a shimmer skeleton in place of the context section only
- Skeleton: 2–3 lines at `fontSize` height, `animate-shimmer bg-slate-100 rounded-2xl`
- OCR suggestion buttons and manual input render immediately (they don't depend on `pageText`)
- Finding stepper renders normally (issue count is known)
- Once `pageText` arrives, the context section fades in (`animate-fade-in`) and scroll-to fires

**Note for Surfaces B/C:** `pageText` can be read directly from the reader's already-loaded `loadedPages[]` — no separate API fetch needed for those surfaces. The parent should pass it to `SpellCheckPanel` from the reader's existing in-memory page data.

---

### S-NEW-3 — Unsaved Phrase Edit Guard

**Trigger:** User is in phrase edit mode when any navigation action fires:
- Surface A: "Next Book" button, or `↑`/`↓` page nav buttons
- Surface B: Reader navigates to a new page (the tab reloads)
- Surface C: Swipe gesture fires `onNextPage` / `onPrevPage`

**Action:** Block the navigation. Show an inline warning banner inside the panel:
- "You have unsaved edits. Apply or cancel before moving on."
- Two options: "Discard" (discard phrase edit, proceed with navigation), "Stay" (dismiss banner, keep editing)

**Note for Surface B:** The reader's page change is hard to intercept from inside the panel. Recommended approach: when `pageNumber` prop changes while `isEditingPhrase` is true, auto-discard the phrase edit and log a warning (interception would require tight coupling to ReaderView). Document this as an acceptable trade-off.

*New locale key:* `spellCheck.unsavedEdit` — "تۈزىتىش ساقلانمىدى. داۋاملاشتىن بۇرۇن ئىلتىماس قىلىڭ."
*New locale key:* `spellCheck.stayAndEdit` — "داۋاملاش" / "Stay"
*New locale key:* `spellCheck.discardEdit` — "تۈزىتىشنى ئەمەلدىن قالدۇرۇش" / "Discard"

---

## State Machines

### Issue Card (Single Active Finding)

```
OPEN (active)
  │
  ├─ Click OCR suggestion ─────────────────────→ CORRECTED
  │     pageText updated locally, offsets shifted, next finding activated
  │
  ├─ Type + Apply ─────────────────────────────→ CORRECTED
  │     same as above
  │
  ├─ Phrase edit + Apply ──────────────────────→ CORRECTED
  │     pageText updated locally, loadIssues() called (offsets unreliable after phrase edit)
  │
  ├─ Click "Later" ────────────────────────────→ SKIPPED (local only)
  │     issue dimmed in stepper, next non-skipped finding activated
  │
  └─ Click "Not an Error" ─────────────────────→ IGNORED (server updated)
        removed from list, next finding activated

SKIPPED (reachable via stepper ← →)
  └─ Click "Undo" ─────────────────────────────→ OPEN (restored, becomes active)

CORRECTED / IGNORED → removed; no re-fetch, no rescan
```

### Page

```
LOADING          isLoading=true, !hasLoaded
  └─ Done ─────→ HAS_ISSUES  or  CLEAN

HAS_ISSUES       issues.length > 0
  └─ All resolved/skipped ──→ CLEAN

CLEAN            issues.length = 0, hasLoaded=true
  ├─ 'auto'          ──→ call onNextPage() immediately (no message)
  ├─ 'reader-driven' ──→ show "reviewed" message, stay — wait for reader to navigate
  └─ 'swipe'         ──→ show "swipe to next page" message, enable swipe gesture

SCANNING         isScanning=true
  └─ Done ─────→ re-fetch pageText → LOADING
```

### SpellCheckView (Book-Level)

```
INIT
  └─ fetchRandomBook() ──→ LOADING_BOOK

LOADING_BOOK
  ├─ 404 ─────────────→ ALL_CLEAN
  ├─ 5xx/network ─────→ LOAD_ERROR
  └─ Success ─────────→ REVIEWING_BOOK

REVIEWING_BOOK
  └─ All pages done ──→ LOADING_BOOK

ALL_CLEAN
  └─ "Next Book" ─────→ LOADING_BOOK

LOAD_ERROR
  └─ "Retry" ─────────→ LOADING_BOOK
```

---

## API Endpoints Summary

| Method | Endpoint | Used by |
|---|---|---|
| GET | `/api/books/spell-check/random-book` | SpellCheckView (book fetch) |
| GET | `/api/books/{id}/spell-check/summary` | Available but not currently used in UI |
| GET | `/api/books/{id}/pages/{n}/spell-check` | `useSpellCheck.loadIssues()` |
| POST | `/api/books/{id}/pages/{n}/spell-check/apply` | `useSpellCheck.applyCorrection()` |
| POST | `/api/books/{id}/pages/{n}/spell-check/ignore` | `useSpellCheck.ignoreIssue()` |
| POST | `/api/books/{id}/pages/{n}/spell-check/trigger` | `useSpellCheck.triggerRecheck()` |
| POST | `/api/books/{id}/spell-check/trigger` | Admin-only (not in SpellCheckPanel) |

**Unused endpoint opportunity:** `/api/books/{id}/spell-check/summary` returns per-page issue counts. This can power the progress indicator without extra backend work.

---

## Localization Keys

### Existing keys (preserve)

| Key | English | Uyghur | Used where |
|---|---|---|---|
| `spellCheck.title` | Spell Check | ئىملا | Navbar, page title |
| `spellCheck.checking` | Checking... | تەكشۈرۈۋاتىدۇ... | Page-level loading label |
| `spellCheck.analyzing` | Checking dictionary... | لۇغەت تەكشۈرۈۋاتىدۇ... | Book/initial loading label |
| `spellCheck.rescan` | Re-scan page | بەتنى قايتا تەكشۈرۈش | Rescan button tooltip |
| `spellCheck.rescanning` | Re-scanning page {{page}}... | {{page}}-بەتنىڭ ئىملاسى تەكشۈرۈلۈۋاتىدۇ... | Scanning spinner label |
| `spellCheck.noErrors` | Page {{page}}: No errors found! | {{page}}-بەتتە باشقا ئىملا خاتالىقى بايقالمىدى! | S6 clean page message |
| `spellCheck.suggestion` | Suggested Correction | تەۋسىيە قىلىنغان تۈزىتىش | OCR suggestion section label |
| `spellCheck.ignore` | Ignore | خاتالىق ئەمەس | Ignore button |
| `spellCheck.applied` | Corrected | تۈزىتىلدى | S6 post-correction message |
| `spellCheck.ignored` | Not Changed | ئۆزگەرمىدى | S6 post-ignore message |
| `spellCheck.apply` | Apply | توغۇرلاش | Apply button |
| `spellCheck.typeCorrection` | Type correct spelling... | توغرا يېزىلىشىنى كىرگۈزۈڭ... | Manual input placeholder |
| `spellCheck.nextBook` | Next Book | كېيىنكى كىتاب | Surface A "Next Book" button |
| `spellCheck.loadingBook` | Finding a book with issues... | ئىملا خاتالىقى بار كىتاب ئىزدەۋاتىدۇ... | S1 loading label |
| `spellCheck.noBooks` | No spell check issues found | ئىملا خاتالىقى بايقالمىدى | S2 empty state title |
| `spellCheck.noBooksDetail` | All books are clean, or spell check has not been run yet. | بارلىق كىتابلار تازا، ياكى ئىملا تەكشۈرۈش ئىشلىتىلمىگەن. | S2 empty state detail |
| `spellCheck.issueCount` | {{count}} pages with issues | {{count}} بەتتە خاتالىق بار | Surface A header badge |

### Retired keys (remove from locale files)

| Key | Reason |
|---|---|
| `spellCheck.skip` | Replaced by `spellCheck.skipLater` ("Later") — old label "بىلمىدىم" no longer used |
| `spellCheck.errorsCount` | "Total N errors found" header above card list — replaced by finding stepper "Finding X of Y" |
| `spellCheck.movingToNext` | "Moving to next..." — Surface A is silent, Surface B stays put, Surface C uses `reviewedSwipe` |

### New keys required for rewrite

| Key | English | Uyghur | Used where |
|---|---|---|---|
| `spellCheck.loadError` | Could not load. Please try again. | يوللىنالمىدى. قايتا سىناڭ. | S2 network error |
| `spellCheck.pageProgress` | Page {{current}} of {{total}} | {{current}}/{{total}} بەت | Surface A header progress badge |
| `spellCheck.findingProgress` | Finding {{current}} of {{total}} | {{current}}/{{total}}-تاپقۇلۇق | Finding stepper label |
| `spellCheck.findingSkippedNote` | ({{skipped}} skipped) | ({{skipped}} يوچۇن قويۇلدى) | Stepper skipped sub-label |
| `spellCheck.skipLater` | Later | كېيىن | Skip/Later button (replaces `skip`) |
| `spellCheck.undoSkip` | Undo | قايتۇرۇش | Undo button on skipped finding |
| `spellCheck.skipped` | Skipped for now | يوچۇن قويۇلدى | S6 all-skipped message |
| `spellCheck.ignoreTooltip` | Mark as correct — won't be flagged again | توغرا دەپ بەلگىلەش — قايتا بايقالمايدۇ | Ignore button tooltip |
| `spellCheck.unsavedEdit` | You have unsaved edits. | تۈزىتىش ساقلانمىدى. | S-NEW-3 guard banner |
| `spellCheck.stayAndEdit` | Stay | داۋاملاش | S-NEW-3 "stay" action |
| `spellCheck.discardEdit` | Discard | ئەمەلدىن قالدۇرۇش | S-NEW-3 "discard" action |
| `spellCheck.noContext` | (Context unavailable) | (مەزمۇن يوق) | Context fallback when offset is null |
| `spellCheck.reviewedSwipe` | All reviewed — swipe to next page | بارلىق تۈزىتىشلەر تامام — سىيرىلىڭ | Surface C post-review message |
| `spellCheck.cleanSwipe` | No issues — swipe to next page | خاتالىق يوق — سىيرىلىڭ | Surface C always-clean message |

---

## Accuracy Bugs Found in Current Implementation

These are **real bugs** that must be fixed in the rewrite:

### Bug 1 — Skipped issues are hidden, not reordered
**File:** `SpellCheckPanel.tsx` line 99–102
**Problem:** `orderedIssues` filters out skipped issues entirely. Spec incorrectly documented this as "moves to end of list."
**Fix:** Keep skipped issues visible as dimmed cards with undo capability.

### Bug 2 — `pagesWithIssues` cleanup uses stale closure
**File:** `SpellCheckView.tsx` lines 279–282
**Problem:** `spellCheck.issues.length` is read synchronously after `await applyCorrection()`, but React state is not updated synchronously. The check may always read the pre-correction count.
**Fix:** Move `pagesWithIssues` cleanup into a `useEffect` watching `spellCheck.issues`:
```tsx
useEffect(() => {
  if (spellCheck.hasLoaded && !spellCheck.isLoading && spellCheck.issues.length === 0) {
    setPagesWithIssues(prev => prev.filter(p => p !== currentPage));
  }
}, [spellCheck.issues.length, spellCheck.hasLoaded, spellCheck.isLoading]);
```

### Bug 3 — Phrase edit corrupts nearby issue offsets
**File:** `SpellCheckView.tsx` / `SpellCheckPanel.tsx`
**Problem:** When a phrase edit replaces `[contextStart, contextEnd]`, only issues after `contextEnd` get their offsets shifted. Issues inside the context window keep stale offsets.
**Fix:** After a phrase edit, call `loadIssues()` to refresh from DB instead of relying on predictive shifting.

### Bug 4 — `hasLoaded` not reset on page change
**File:** `useSpellCheck.ts` — `loadIssues()` doesn't reset `hasLoaded`
**Problem:** When navigating to a new page, `hasLoaded` remains `true` from the prior page. Old issues briefly render with new-page context.
**Fix:** Reset `hasLoaded` (and `issues`) at the start of `loadIssues()`:
```tsx
setHasLoaded(false);
setIssues([]);
setIsLoading(true);
```

### Bug 5 — pageText race causes context fallback flash
**File:** `SpellCheckView.tsx` lines 74–82
**Problem:** Issues and `pageText` are fetched in parallel. Issues often resolve first, causing context to briefly show the word-only fallback before the text loads.
**Fix:** Show a skeleton shimmer in the context area while `pageText` is undefined (S-NEW-2).

---

## UI Issues in Current Implementation

| # | Problem | Proposed Fix |
|---|---|---|
| 1 | Issue card too tall — all sections stack vertically | Compact card: suggestions horizontal scroll on mobile |
| 2 | Phrase edit textarea `min-h-[300px]` on mobile dominates screen | `min-h-[120px]` on mobile, `min-h-[160px]` on desktop |
| 3 | No progress indicator | Add "N/M pages" badge in panel header (S-NEW-1) |
| 4 | Page nav is swipe-only | Add explicit `←` `→` icon buttons in panel header |
| 5 | Skip hides issues silently, auto-advance is surprising | Show skipped as dimmed cards, allow undo (Bug 1 fix) |
| 6 | "Moving to next..." never shows in standalone view | Correct — `navigationMode='auto'` is silent. Surface B shows "reviewed" message. Surface C shows "swipe" message. `movingToNext` key retired. |
| 7 | Header duplicated for desktop/mobile | Single responsive header using Tailwind breakpoint classes |
| 8 | Rescan button is tiny and hard to find | Move to panel header nav group with consistent icon button style |
| 9 | "No books" and "API error" states look identical | Differentiate with icon + color + CTA (S2 accuracy note) |
| 10 | Reader tab shows no book context | Panel header in reader tab shows book title from `selectedBook` |
| 11 | Multiple OCR suggestions stack vertically on mobile | Horizontal pill row with horizontal scroll |

---

## Requirements for the Rewrite

### Must-Have
- [ ] All scenarios implemented (S1–S15, S-NEW-1 to S-NEW-3)
- [ ] All three surfaces supported via same `SpellCheckPanel` component
- [ ] All 5 accuracy bugs fixed (Bugs 1–5)
- [ ] Bug 3 fix: Phrase edit triggers `loadIssues()` (not predictive shifting) — data accuracy
- [ ] Bug 4 fix: `hasLoaded` + `issues` reset at start of `loadIssues()` — prevents stale flash
- [ ] **Decision 1:** Standalone view has NO reader position sync (`setReaderPage` removed)
- [ ] **Decision 2:** Reader tab panel header shows book title, author, and per-page issue count
- [ ] **Decision 3:** No auto `loadIssues()` or `triggerRecheck()` after a correction — local state only
- [ ] **Decision 4:** Single-active-finding model — one issue shown at a time with stepper
- [ ] **Decision 4:** Context re-extracted from local `pageText` on every finding activation
- [ ] **Decision 4:** Highlighted word scrolled into view on every finding activation
- [ ] RTL layout and `uyghur-text` class applied throughout
- [ ] Design tokens match app design system exactly (colors, radius, buttons, glass)
- [ ] Responsive: mobile ≥375px and desktop ≥1024px
- [ ] All API contracts preserved — no backend changes
- [ ] All locale strings used — new keys added to `en.json` and `ug.json`
- [ ] `silentMode` prop replaced with `navigationMode: 'auto' | 'reader-driven' | 'swipe'`
- [ ] Surface A passes `navigationMode='auto'`
- [ ] Surface B (desktop, reader visible) passes `navigationMode='reader-driven'`
- [ ] Surface C (mobile, spell check tab only) passes `navigationMode='swipe'`
- [ ] Swipe gestures only active in `'swipe'` mode when `issues.length === 0`

### Should-Have
- [ ] Progress indicator: "N/M pages with issues" in standalone header (S-NEW-1)
- [ ] Finding stepper: "Finding X of Y" with `←` `→` navigation, hidden when only 1 finding
- [ ] Skeleton shimmer for context while `pageText` loads (S-NEW-2)
- [ ] Surface B/C: read `pageText` from reader's loaded pages — no extra API fetch
- [ ] Skipped findings reachable via stepper, show muted state with "Undo" button
- [ ] Unsaved phrase edit guard on all navigation triggers across all surfaces (S-NEW-3)
- [ ] Error/clean state differentiation in S2 (emerald vs amber)
- [ ] All retired locale keys removed from `en.json` and `ug.json`
- [ ] OCR suggestions as horizontal scroll pill row on mobile

### Nice-to-Have
- [ ] `Enter` key applies first OCR suggestion when input is empty
- [ ] Animated slide-out when the active finding is resolved
- [ ] Ignore tooltip on first use explaining the permanent nature
- [ ] Keyboard shortcut legend (editor power users)
