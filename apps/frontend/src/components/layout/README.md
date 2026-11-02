# Layout Component (`layout`)

## Overview
Provides the overarching structural application layout, responsive navigation bar, view mode switching, dark/light theme toggling, sponsor attribution footer, and global modal/notification mounting frames.

## Interface
- `[Navbar.tsx:Navbar]` — Top application navigation bar providing logo navigation, global search trigger, route view switching (`home`, `library`, `global-chat`, `spell-check`, `graph`, `dictionary`, `quran`, `admin`), light/dark theme toggler, and auth widget.
- `[Shell.tsx:Shell]` — Top-level application frame rendering the `Navbar`, main view container, responsive footer with sponsor links, `Modal` dialog portal, and `NotificationContainer`.

## Invariants
- `[Navbar.tsx:isEditor]` — Restricts access to admin link in navbar to users possessing editor/admin roles (`useIsEditor()`).
- `[Shell.tsx:isReaderFullscreen]` — Hides the navigation bar on mobile/tablet viewports when reading a book in fullscreen mode (`isReaderFullscreen`).

## Side Effects
- `[Navbar.tsx:setTheme]` — Modifies active theme (`light` | `dark`) in `ThemeContext` and updates root DOM classes/attributes.
- `[Navbar.tsx:setView]` — Changes global active view state in `AppContext`.

## Verification
- Run: `npm test`
