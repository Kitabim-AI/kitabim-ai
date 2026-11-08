# Frontend Context

## Overview
Coordinates global React application state including navigation routing, library management, active reader progress, floating notifications, and theme settings.

## Interface
- `[AppContext.tsx:ADMIN_TABS]`: Tuple of allowed subview tab keys for the admin dashboard (`'books'`, `'users'`, `'questions'`, `'rules'`, `'stats'`, `'contacts'`, `'config'`).
- `[AppContext.tsx:LIBRARY_TABS]`: Tuple of allowed subview tab keys for the library dashboard (`'all-books'`, `'reading'`, `'bookmarks'`).
- `[AppContext.tsx:AppProvider]`: React provider supplying routing, shelf pagination, search queries, book reader modal, and chat state to descendants.
- `[AppContext.tsx:useAppContext]`: Hook returning global application state and dispatchers (`AppContextType`).
- `[NotificationContext.tsx:NotificationType]`: Union type representing toast notification severity levels (`'success' | 'error' | 'info'`).
- `[NotificationContext.tsx:Notification]`: Interface describing notification records (`id`, `type`, `message`).
- `[NotificationContext.tsx:NotificationProvider]`: React provider managing toast notification queues.
- `[NotificationContext.tsx:useNotification]`: Hook returning notification operations (`addNotification`, `removeNotification`).
- `[ThemeContext.tsx:Theme]`: Union type representing theme modes (`'light' | 'dark'`).
- `[ThemeContext.tsx:ThemeProvider]`: React provider managing UI theme switching and persistence.
- `[ThemeContext.tsx:useTheme]`: Hook returning active theme mode and `setTheme` updater.

## Invariants
- `[AppContext.tsx:useAppContext]`: Must be invoked inside `<AppProvider>`, throwing `Error('useAppContext must be used within an AppProvider')` if context is undefined.
- `[NotificationContext.tsx:useNotification]`: Must be invoked inside `<NotificationProvider>`, throwing `Error('useNotification must be used within a NotificationProvider')` if context is undefined.
- `[ThemeContext.tsx:useTheme]`: Must be invoked inside `<ThemeProvider>`, throwing `Error('useTheme must be used within a ThemeProvider')` if context is undefined.
- `[AppContext.tsx:AppProvider]`: Subtab transitions in admin or library views validate against `ADMIN_TABS` and `LIBRARY_TABS`, falling back to `'books'` and `'all-books'` respectively.

## Side Effects
- `[AppContext.tsx:AppProvider]`: Writes browser location and history via `window.history.pushState` and `window.history.replaceState`; registers global listeners for `popstate`, `visibilitychange`, and `pagehide`; persists book reading progress via `PersistenceService.saveReadingProgress` debounced at 2000ms.
- `[NotificationContext.tsx:NotificationProvider]`: Schedules 5000ms `setTimeout` timers to automatically dismiss `'success'` notifications.
- `[ThemeContext.tsx:ThemeProvider]`: Reads from and writes to `localStorage` key `'theme'`; modifies CSS classes on `document.documentElement` (`root.classList.add('dark')` / `root.classList.remove('dark')`).

## Verification
- Run: `npm test`
