# Kitabim AI — UI CSS Standard

> **Status:** Draft — Not yet implemented
> **Stack:** Tailwind CSS 3.4, custom components, RTL (Uyghur), glass morphism design language

---

## Overview

This document defines the project-wide visual standard for font sizes, colors, spacing, border radii, shadows, and other look-and-feel attributes. The goal is to replace scattered arbitrary Tailwind values (e.g. `text-[30px]`, `bg-[#0369a1]/10`) with named, semantic tokens defined in `tailwind.config.js` and `index.css`.

---

## Color Tokens

To be added to `tailwind.config.js` under `theme.extend.colors`.

### Brand Colors

| Token | Hex | Usage |
|---|---|---|
| `primary` | `#0369a1` | Main brand blue — borders, icons, active states |
| `primary-light` | `#0284c7` | Hover / lighter variant of primary |
| `primary-soft` | `rgba(3, 105, 161, 0.1)` | Tinted backgrounds, subtle highlights |
| `accent-gold` | `#FFD54F` | Gold accents, highlights, decorative borders |
| `accent-orange` | `#FF9800` | Warm accent, progress indicators, badges |
| `accent-purple` | `#9C27B0` | Secondary decorative accent |

### Neutral / Text Colors

| Token | Hex | Usage |
|---|---|---|
| `text-base-color` | `#1a1a1a` | Primary body text |
| `text-secondary` | `#64748b` | Secondary / supporting text |
| `text-muted` | `#94a3b8` | Placeholders, disabled, helper text |
| `bg-page` | `#f8fafc` | Static page background fallback |

### Status Colors (Admin / Processing Pipeline)

| Token | Tailwind Equivalent | Usage |
|---|---|---|
| `status-ready` | `emerald-500` | Step or Book is 100% complete |
| `status-active` | `[#FF9800]` | Step is in progress / started (Blinking) |
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

**Line height conventions:**
- Uyghur content text: `1.8` (handled by `.uyghur-text` class)
- UI / chrome text: `1.5` (Tailwind default `leading-normal`)

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
| `rounded-ui-full` | 9999px | Avatars, pill badges |

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

The `.glass-panel` utility class (already in `index.css`) is the standard for all frosted surface elements.

| Class | Opacity | Usage |
|---|---|---|
| `.glass-panel` | `rgba(255,255,255,0.8)` | Navbar, sidebars, main chat container |
| `.glass-panel-light` | `rgba(255,255,255,0.5)` | Inner nested panels, secondary surfaces |
| `.glass-panel-strong` | `rgba(255,255,255,0.95)` | Modals, critical dialogs requiring readability |

CSS variables (in `index.css :root`):
```css
--glass-bg: rgba(255, 255, 255, 0.8);
--glass-blur: blur(20px) saturate(180%);
--glass-border: 1px solid rgba(255, 193, 7, 0.15);
```

---

## Implementation Plan

When ready to implement, make changes in this order — no component files need to change first:

1. **`apps/frontend/tailwind.config.js`** — extend theme with all color, font-size, border-radius, and shadow tokens above
2. **`apps/frontend/index.css`** — add CSS variables for missing tokens (glass variants, shadow values); keep existing variables
3. **Component migration (later)** — replace arbitrary values like `text-[30px]` → `text-ui-3xl`, `bg-[#0369a1]/10` → `bg-primary-soft`, `rounded-[28px]` → `rounded-ui-2xl` across component files

---

## Current Inconsistencies to Fix During Migration

| Issue | Example (current) | Target |
|---|---|---|
| Arbitrary font sizes | `text-[30px]`, `text-[10px]` | `text-ui-2xl`, `text-ui-2xs` |
| Hardcoded color values | `bg-[#0369a1]/10`, `text-[#0369a1]/50` | `bg-primary-soft`, `text-primary/50` |
| Mixed border radii | `rounded-[20px]`, `rounded-[28px]`, `rounded-[40px]` | `rounded-ui-xl`, `rounded-ui-2xl` |
| Inline shadow overrides | `shadow-xl shadow-[#0369a1]/20` | `shadow-ui-lg` |
