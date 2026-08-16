---
name: ui-designer
description: "Use when designing new React UI components for the kitabim-ai frontend, before implementation."
---

# UI Designer Skill — Kitabim AI Frontend

You are acting as a UI designer and implementer for the kitabim-ai frontend. Your job is to design and implement polished, accessible, responsive React/TypeScript UI components that feel native to this codebase.

## Project Context

- **Framework:** React + TypeScript, Vite
- **Styling:** Tailwind CSS (utility-first, no separate CSS files)
- **Icons:** `lucide-react`
- **i18n:** `useI18n()` hook from `../../i18n/I18nContext` — always use `t('key')` for user-visible strings
- **RTL:** The app supports RTL (Uyghur language). Use `dir="rtl"` on containers with text content. Add `uyghur-text` class for Uyghur body text.
- **Theming:** The app supports light/dark mode via `useTheme()` hook from `../../context/ThemeContext`, which toggles a `dark` class on `<html>`. Every color, border, and background utility should have a matching Tailwind `dark:` variant — this is used consistently across nearly all components, including the newest ones (e.g. `components/graph/GraphView.tsx`).
- **Frontend root:** `apps/frontend/src/`

## Design System

### Color Palette
- **Primary blue:** `#0369a1` (use for actions, links, icons, accents)
- **Primary blue tints:** `#0369a1/10`, `#0369a1/20`, `#0369a1/30` for backgrounds/borders
- **Dark text:** `#1a1a1a`
- **Body text:** `text-slate-700`
- **Muted text:** `#64748b` / `text-slate-500`
- **Borders:** `border-[#0369a1]/10` (default), `border-[#0369a1]/30` (hover)
- **White surfaces:** `bg-white/80` or `bg-white/90` with `backdrop-blur-xl`

### Dark Mode
Every color/border/surface token above needs a `dark:` counterpart — this is applied consistently, not optional:
- **Accent (dark equivalent of `#0369a1`):** `#38bdf8` — e.g. `text-[#0369a1] dark:text-[#38bdf8]`, `border-[#0369a1]/10 dark:border-[#38bdf8]/10`, `bg-[#0369a1]/10 dark:bg-[#38bdf8]/10`
- **Surfaces:** `bg-white/80 dark:bg-slate-900/60` (panels), `dark:bg-slate-900/95` (opaque menus/dropdowns)
- **Text:** `dark:text-slate-100` (headings), `dark:text-slate-400` or `dark:text-slate-500` (muted/body)
- **Borders:** `dark:border-slate-800` (neutral), `dark:border-[#38bdf8]/10` (accent)

### Glass Morphism Pattern
The signature style of this app. Most components apply the global `glass-panel` CSS class (defined in `apps/frontend/index.css`, backed by `--glass-bg`/`--glass-blur`/`--glass-border` CSS variables that flip automatically for dark mode) directly as a className, layered with Tailwind utilities for rounding/border/shadow overrides:
```tsx
className="glass-panel rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 shadow-md"
```
Equivalent inline (no `glass-panel` class) if you need a one-off surface:
```tsx
className="bg-white/80 dark:bg-slate-900/60 backdrop-blur-xl rounded-2xl border border-[#0369a1]/10 dark:border-slate-800 shadow-md"
```
Or use the existing `<GlassPanel>` component from `components/ui/GlassPanel.tsx`, which wraps the `glass-panel` class.

### Rounded Corners
- Cards: `rounded-2xl` (mobile) → `sm:rounded-3xl` (desktop)
- Modals: `rounded-[24px]` → `sm:rounded-[32px]` → `md:rounded-[40px]`
- Buttons: `rounded-2xl`
- Badges/pills: `rounded-full`
- Icons in containers: `rounded-2xl`

### Buttons
- **Primary:** `bg-slate-900 dark:bg-slate-800 hover:bg-slate-800 dark:hover:bg-slate-700 text-white dark:text-slate-100 rounded-2xl px-6 py-2.5 text-sm font-normal uppercase tracking-widest transition-all active:scale-95 shadow-lg shadow-black/10`
- **Icon button:** `p-2 hover:bg-red-50 dark:hover:bg-red-950/20 text-slate-300 hover:text-red-500 rounded-2xl transition-all active:scale-95`
- **Pill badge:** `px-3 py-1 bg-[#0369a1]/10 dark:bg-[#38bdf8]/10 text-[#0369a1] dark:text-[#38bdf8] rounded-full text-xs`

### Shadows
- Cards: `shadow-md`
- Hover: `shadow-[0_12px_24px_rgba(3,105,161,0.1)]`
- Modals: `shadow-[0_32px_128px_rgba(0,0,0,0.3)]`
- Icon containers: `shadow-xl shadow-[#0369a1]/20`

### Animations & Transitions
- Default transition: `transition-all duration-300`
- Card hover lift: `hover:-translate-y-1`
- Button press: `active:scale-95`
- Fade in overlay: `animate-fade-in`
- Scale up modal: `animate-scale-up`

### Status Colors
Map status strings to Tailwind pairs (`bg-*-50 text-*-600`):
- `ready` → emerald | `error` → red | `pending` → amber
- `ocr*` → blue | `indexing`/`embedding` → orange | `spell_check` → purple | `chunking` → indigo

## Component Patterns

### Component Structure
```tsx
import React from 'react';
import { IconName } from 'lucide-react';
import { useI18n } from '../../i18n/I18nContext';

interface MyComponentProps {
  // typed props
}

export const MyComponent: React.FC<MyComponentProps> = ({ ... }) => {
  const { t } = useI18n();
  return ( ... );
};
```

### Responsive Breakpoints
Always mobile-first. Common pattern:
```tsx
className="text-sm sm:text-lg p-3 sm:p-5 rounded-2xl sm:rounded-3xl gap-2 sm:gap-4"
```

### Modals
Use `createPortal(jsx, document.body)` with a backdrop + centered panel:
```tsx
<div className="fixed inset-0 z-[200] flex items-center justify-center p-2 sm:p-4 md:p-8" dir="rtl">
  <div className="absolute inset-0 bg-slate-900/60 backdrop-blur-xl" onClick={onClose} />
  <div className="bg-white/90 dark:bg-slate-900/95 backdrop-blur-2xl rounded-[24px] sm:rounded-[32px] w-full max-w-2xl max-h-[90vh] relative z-10 overflow-hidden flex flex-col border border-white/40 dark:border-slate-800/40">
    {/* Header, Content, Footer */}
  </div>
</div>
```

### Icon Usage
- Import only what you use from `lucide-react`
- Standard sizes: `size={14}` (small), `size={20}` (medium), `size={28}` (large)
- Consistent stroke: `strokeWidth={2.5}`
- Responsive icons: render two with `className="sm:hidden"` / `className="hidden sm:block"`

## Workflow

1. **Read before writing** — read existing components in the same directory for style context before creating or editing any component.
2. **Check for reuse** — check `components/ui/` and `components/common/` for existing building blocks (`GlassPanel`, `Modal`, `UserAvatar`, etc.) before building from scratch.
3. **i18n all strings** — never hardcode user-visible text; add translation keys via `t('namespace.key')`.
4. **RTL awareness** — use `text-right`, `dir="rtl"`, and avoid directional layout assumptions.
5. **Accessibility** — add `title`, `aria-label`, or `aria-hidden` where needed. Ensure interactive elements have visible focus styles.
6. **No magic numbers** — use Tailwind spacing/sizing tokens; only use arbitrary values (`w-[300px]`) when needed for design precision.
7. **Dark mode** — pair every color/border/background utility with a `dark:` variant (see Dark Mode section above); do not ship light-mode-only styling.
