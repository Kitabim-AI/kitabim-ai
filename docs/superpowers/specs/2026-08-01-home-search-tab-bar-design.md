# Home Search Tab Bar UX & Design Spec

## Overview
This document specifies the UI/UX redesign for the Home Search Box Tab Bar (`SearchTabBar.tsx`) in Kitabim-AI.

## Problems Addressed
1. **Horizontal Scrollbar**: Native/custom scrollbar tracks appeared underneath search tabs on browsers due to `overflow-x-auto custom-scrollbar`.
2. **Typography Mismatch**: Non-Uyghur/Latin strings (e.g. "History Terms", "Names") defaulted to browser `serif` (Times New Roman) because the primary Uyghur font (`ALKATIP Basma`) lacks Latin glyphs.
3. **UX Style Disconnect**: Tabs appeared as disconnected, floating dark buttons rather than a cohesive, glassmorphic segmented controller consistent with Kitabim.AI's design language.

## Design Specifications

### 1. Unified Glass Segmented Container
- Tabs are wrapped in a single, continuous pill-shaped glass container (`rounded-full backdrop-blur-2xl`).
- Container styling:
  - Light mode: `bg-slate-200/50 border border-slate-300/40 shadow-inner`
  - Dark mode: `bg-slate-900/60 border border-slate-800/80 shadow-inner`
- Padding & Layout: `p-1.5 min-w-max flex items-center gap-1.5`.

### 2. Scrollbar Removal & Smooth Scroll
- Scrollbar is completely hidden across all rendering engines: `[scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden`.
- Tab buttons marked with `flex-shrink-0` to preserve whitespace and pill structure without wrapping or shrinking.

### 3. Tab Button Aesthetics & States
- **Base Tab Styling**: `px-3.5 py-1.5 rounded-full text-xs sm:text-sm font-medium whitespace-nowrap transition-all duration-200 active:scale-95 flex-shrink-0 flex items-center gap-2`.
- **Typography**: Combined `font-sans uyghur-text` to ensure clean sans-serif rendering for Latin labels alongside proper Uyghur typography.
- **Inactive State**:
  - `text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-white/40 dark:hover:bg-slate-800/50`
- **Active State (Standard Tabs)**:
  - `bg-white dark:bg-slate-800 text-[#0369a1] dark:text-[#38bdf8] shadow-md border border-slate-200/60 dark:border-slate-700/60 font-semibold`
- **Active State ("Ask AI" Tab)**:
  - `bg-gradient-to-r from-[#0369a1] to-[#0284c7] dark:from-[#38bdf8] dark:to-[#0ea5e9] text-white dark:text-slate-950 shadow-md shadow-[#0369a1]/30 font-semibold`

## Verification
1. Verify horizontal scrollbar is completely hidden on desktop and mobile browsers.
2. Confirm English and Uyghur tab titles render with modern typography (no Times New Roman fallback).
3. Validate responsive behavior and active tab toggling.
