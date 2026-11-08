# UI Component (`ui`)

## Overview
Provides primitive visual design containers and atomic layout wrappers, including glassmorphism backdrop panels used across the frontend interface.

## Interface
- `[GlassPanel.tsx:GlassPanel]` — Generic container component rendering modern glassmorphic panel styling with `glass-panel` className and custom styles.

## Invariants
- `[GlassPanel.tsx:GlassPanelProps]` — Forwards optional inline `style`, `className`, and `onClick` handlers while preserving nested `children`.

## Side Effects
- `[GlassPanel.tsx:onClick]` — Dispatches optional click event handler when provided.

## Verification
- Run: `npm test`
