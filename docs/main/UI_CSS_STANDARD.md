# Kitabim AI — UI CSS Standard

> **Status:** Proposed standard, not yet adopted — `apps/frontend/tailwind.config.js` currently has an empty `theme.extend`, so none of the semantic tokens below exist as Tailwind utilities yet. Components use arbitrary values (`text-[30px]`, `bg-[#0369a1]/10`, `rounded-[28px]`) and hardcoded hex colors directly.
> **Stack:** Tailwind CSS 3.4, React 19, RTL (Uyghur), glass morphism design language, class-based dark mode

---

## Overview

This document defines the project-wide visual standard for font sizes, colors, spacing, border radii, shadows, and dark mode. The goal is to replace scattered arbitrary Tailwind values and repeated hex literals with named, semantic tokens defined in `tailwind.config.js` and CSS variables in `apps/frontend/index.css`.

Until this is implemented, treat the tables below as the target values to converge on when touching a component, not as classes that exist today.

---

## Color Tokens

To be added to `tailwind.config.js` under `theme.extend.colors`. Current hex values are taken from the CSS variables already defined in `apps/frontend/index.css` `:root` and from the values hardcoded throughout components.

### Brand Colors

| Token | Hex (light) | Hex (dark) | Usage |
|---|---|---|---|
| `primary` | `#0369a1` | `#38bdf8` | Main brand blue — borders, icons, active states |
| `primary-light` | `#0284c7` | `#0ea5e9` | Hover / lighter variant of primary |
| `primary-soft` | `rgba(3, 105, 161, 0.1)` | — | Tinted backgrounds, subtle highlights |
| `accent-gold` | `#FFD54F` | — | Gold accents, highlights, decorative borders |
| `accent-orange` | `#FF9800` | — | Warm accent, progress indicators, badges |
| `accent-purple` | `#9C27B0` | — | Secondary decorative accent |

The light/dark pairs above already exist as CSS variables (`--primary-blue`, `--secondary-blue`) that swap value under the `.dark` class selector in `index.css`. Components currently reproduce this manually with `dark:` variants (e.g. `text-[#0369a1] dark:text-[#38bdf8]`) rather than referencing the variables — see [Dark Mode](#dark-mode) below.

### Neutral / Text Colors

| Token | Hex | Usage |
|---|---|---|
| `text-base-color` | `#1a1a1a` | Primary body text |
| `text-secondary` | `#64748b` | Secondary / supporting text |
| `text-muted` | `#94a3b8` | Placeholders, disabled, helper text |
| `bg-page` | `#f8fafc` | Static page background fallback |

### Status Colors (Admin / Processing Pipeline)

Confirmed in active use today via Tailwind's built-in palette (not yet as named tokens):

| Token | Tailwind Equivalent | Usage |
|---|---|---|
| `status-ready` | `emerald-500` | Step or Book is 100% complete |
| `status-active` | `[#FF9800]` | Step is in progress / started (blinking) |
| `status-pending` | `slate-300` | Step is waiting/idle |
| `status-error` | `red-500` | Step encountered an error |

---

## Typography Scale

To be added to `tailwind.config.js` under `theme.extend.fontSize`.

| Token | Size | Usage |
|---|---|---|
| `text-ui-2xs` | 10px | Tiny labels on mobile (e.g. BookCard status badge) |
| `text-ui-xs` | 12px | Captions, metadata, helper text |
| `text-ui-sm` | 14px | Secondary body, table cells, nav items |
| `text-ui-base` | 16px | Default body text, inputs, chat messages |
| `text-ui-md` | 18px | Emphasized body text |
| `text-ui-lg` | 20px | Subheadings, modal titles |
| `text-ui-xl` | 24px | Section headings |
| `text-ui-2xl` | 30px | Page headings, library title |
| `text-ui-3xl` | 40px | Logo / hero / display text |

**Fonts** (declared via `@font-face` in `index.css`, applied through CSS variables):
- `--font-uyghur` (`ALKATIP Basma`) — default body/UI font, applied globally to `*, body, button, input, textarea, select`
- `--font-headers` (`ALKATIP Basma`) — `h1`–`h6`; book content headings switch to `ALKATIP Basma Tom` via `.uyghur-text h1`–`h6`
- `--font-nav` (`ALKATIP Basma`) — nav/`.navbar`/`[role="navigation"]`
- `Adobe Arabic` (`.reader-font-adobe`, `.arabic-text`) and `KFGQPC Uthmanic Script HAFS` (`.quran-page .arabic-text`) — alternate reader fonts and Quran text

**Line height conventions:**
- Uyghur content text: `1.8` (`.uyghur-text` class)
- UI / chrome text: `1.5` (Tailwind default `leading-normal`)

**Mobile input font-size:** `index.css` forces `font-size: 16px !important` on `input`, `select`, and `textarea` below 768px viewport width (`@media screen and (max-width: 767px)`), to prevent iOS Safari from auto-zooming on focus. This already matches the `text-ui-base` (16px) target above, independent of token adoption.

---

## Border Radius

To be added to `tailwind.config.js` under `theme.extend.borderRadius`.

| Token | Value | Usage |
|---|---|---|
| `rounded-ui-sm` | 8px | Buttons, input fields, chips, small badges |
| `rounded-ui-md` | 12px | Cards, dropdowns, tooltips |
| `rounded-ui-lg` | 16px | Side panels, larger containers |
| `rounded-ui-xl` | 20px | Modals, major panels |
| `rounded-ui-2xl` | 28px | Book cards, hero cards |
| `rounded-ui-full` | 9999px (`rounded-full`) | Avatars, pill badges — already used consistently today |

---

## Spacing Conventions

Use Tailwind's default numeric scale. These are the semantic conventions for common contexts:

| Context | Classes | Description |
|---|---|---|
| Button — small | `px-4 py-2` | Compact action buttons |
| Button — default | `px-6 py-3` | Standard buttons |
| Button — large | `px-8 py-4` | Hero / prominent CTAs |
| Card padding — compact | `p-4` | Dense information cards |
| Card padding — default | `p-6` | Standard cards |
| Card padding — spacious | `p-8` | Feature / hero cards |
| Page edge margins | `px-4 sm:px-6 md:px-10 lg:px-12` | Global horizontal padding |
| Section gaps (grid/flex) | `gap-4 md:gap-6 lg:gap-8` | Space between major sections |
| Element gaps | `gap-2 md:gap-4` | Space between close siblings |

---

## Shadows

To be added to `tailwind.config.js` under `theme.extend.boxShadow`.

| Token | Value | Usage |
|---|---|---|
| `shadow-ui-sm` | `0 2px 8px rgba(3,105,161,0.08)` | Subtle card lift, resting state |
| `shadow-ui-md` | `0 4px 16px rgba(3,105,161,0.12)` | Hover state, active cards |
| `shadow-ui-lg` | `0 8px 32px rgba(3,105,161,0.16), 0 4px 12px rgba(156,39,176,0.06)` | Modals, floating panels |

---

## Glass Morphism

`.glass-panel` (defined in `apps/frontend/index.css`) is the standard frosted-surface utility class and is already used across the app (navbar, admin menus, modals, ~28 components), including via the reusable `<GlassPanel>` wrapper component (`apps/frontend/src/components/ui/GlassPanel.tsx`).

| Class | Status | Opacity | Usage |
|---|---|---|---|
| `.glass-panel` | Implemented | `rgba(255,255,255,0.8)` light / `rgba(15,23,42,0.65)` dark | Navbar, sidebars, main chat container, dropdown menus |
| `.glass-panel-light` | Proposed, not yet in `index.css` | `rgba(255,255,255,0.5)` | Inner nested panels, secondary surfaces |
| `.glass-panel-strong` | Proposed, not yet in `index.css` | `rgba(255,255,255,0.95)` | Modals, critical dialogs requiring readability |

CSS variables backing `.glass-panel` (in `index.css` `:root`, overridden under `.dark`):
```css
--glass-bg: rgba(255, 255, 255, 0.8);
--glass-blur: blur(20px) saturate(180%);
--glass-border: 1px solid rgba(255, 193, 7, 0.15);
```

---

## Dark Mode

`tailwind.config.js` sets `darkMode: 'class'`. Dark mode is toggled by adding a `.dark` class to the root element (not a media-query strategy), and is already extensively adopted — components use `dark:` variants directly (over 2,000 occurrences across `apps/frontend/src`), most often paired with the arbitrary-hex pattern rather than a semantic token, e.g.:

```
text-[#0369a1] dark:text-[#38bdf8]
bg-[#0369a1]/5 dark:bg-[#38bdf8]/10
border-slate-200 dark:border-slate-800
```

`index.css` also defines a `.dark` override block that repoints the brand CSS variables (`--primary-blue`, `--secondary-blue`, `--bg-light`, `--glass-bg`, `--glass-border`) and the page background gradient/decorative overlays for dark mode. When the color tokens above are implemented in `tailwind.config.js`, each brand color token should resolve through these variables so `dark:` variants are unnecessary for brand colors — only status/neutral colors would still need explicit `dark:` classes.

---

## RTL

The document root is RTL by default (`html { direction: rtl }` in `index.css`), matching the Uyghur-first UI. Individual components additionally set `dir="rtl"` where content needs to be explicit (e.g. reader panes, modals). Uyghur body/content text uses the `.uyghur-text` utility class (line-height `1.8`, ligature/kerning feature settings tuned for Perso-Arabic script, italics disabled since most Uyghur webfonts break letter connections under `font-style: italic`).

---

## Implementation Plan

When ready to implement, make changes in this order — no component files need to change first:

1. **`apps/frontend/tailwind.config.js`** — extend theme with all color, font-size, border-radius, and shadow tokens above
2. **`apps/frontend/index.css`** — add CSS variables for missing tokens (glass variants, shadow values); keep existing variables
3. **Component migration (later)** — replace arbitrary values like `text-[30px]` → `text-ui-3xl`, `bg-[#0369a1]/10` → `bg-primary-soft`, `rounded-[28px]` → `rounded-ui-2xl` across component files

---

## Current Inconsistencies to Fix During Migration

Verified against `apps/frontend/src` — arbitrary values remain widespread (over 250 arbitrary font-size classes alone):

| Issue | Example (current) | Target |
|---|---|---|
| Arbitrary font sizes | `text-[30px]`, `text-[10px]` | `text-ui-2xl`, `text-ui-2xs` |
| Hardcoded color values | `bg-[#0369a1]/10`, `text-[#0369a1]/50` | `bg-primary-soft`, `text-primary/50` |
| Mixed border radii | `rounded-[20px]`, `rounded-[28px]`, `rounded-[40px]` | `rounded-ui-xl`, `rounded-ui-2xl` |
| Inline shadow overrides | `shadow-xl shadow-[#0369a1]/20` | `shadow-ui-lg` |
| Manual dark-mode color pairs | `text-[#0369a1] dark:text-[#38bdf8]` | `text-primary` (resolves via CSS variable) |
