# Frontend Source (`apps/frontend/src`)

## Overview
Source code root for the Kitabim.AI React 19 single-page application. Groups UI component packages, global React context providers, reusable hooks, API clients, computational utilities, internationalization dictionaries, and static constants.

## Subdirectories & Boundaries
- [components](./components/README.md) - Reusable UI views, administrative console, conversational chat interface, virtualized reader, search views, and orthographic spell checking.
- [constants](./constants/README.md) - Static configuration constants including conversational assistant character personas and OCR/pipeline milestone definitions.
- [context](./context/README.md) - Global React context state management for routing, library navigation, reading progress, notifications, and theme modes.
- [hooks](./hooks/README.md) - Custom React hooks for authentication, book actions, streaming chat, reader DOM management, search, and Uyghur keyboard input.
- [i18n](./i18n/README.md) - Uyghur and English internationalization subsystem with dot-path key translation and parameter interpolation.
- [services](./services/README.md) - HTTP API clients for authentication, Gemini AI chat streaming, PDF rendering, full-text search, and admin user management.
- [utils](./utils/README.md) - Pure utility functions for Arabic/Quranic normalization, Uyghur alphabet collation, token cost calculation, and text diffing.

## Verification
- Run: `npm test`

