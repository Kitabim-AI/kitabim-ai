# Frontend Application (`apps/frontend`)

## Overview
Web application frontend for Kitabim.AI built with React 19, TypeScript, Vite, and Tailwind CSS. Provides the client-facing user interface for catalog browsing, book reading with inline corrections, streaming RAG chat with historical figures, Uyghur orthographic spell checking, and administrator controls.

## Local Interface & Invariants
- `[index.tsx:initAppConfig]` - Initializes application security configuration (`X-Kitabim-App-Id`) prior to mounting the React component tree into DOM `#root`.
- `[index.tsx:root.render]` - Mounts `<I18nProvider>`, `<AuthProvider>`, `<NotificationProvider>`, and `<App>` within `<React.StrictMode>`.

## Subdirectories & Boundaries
- [src](./src/README.md) - Application source code containing components, hooks, services, contexts, utilities, and localization files.

## Invariants
- `[index.tsx]` - Requires DOM element `#root` to exist; throws an error if missing.
- `[index.tsx]` - API requests require `initAppConfig()` to resolve before initial render to ensure proper request attribution.

## Side Effects
- `[index.tsx]` - Mounts React application into `#root` DOM container.
- `[index.tsx]` - Issues initial HTTP request to fetch application configuration.

## Verification
- Run: `npm test`

