# Design Spec: Dark Mode and Auto Theme Selection

Implementing a dark mode theme toggle (Light / Dark / System Auto) in the Kitabim.AI frontend, using Tailwind CSS's class-based dark mode strategy and custom CSS variables for premium styling.

## Proposed Architecture

1. **Tailwind Config**:
   Configure Tailwind to look for the `dark` class on the `<html>` or `<body>` element.
   ```javascript
   darkMode: 'class'
   ```

2. **ThemeContext**:
   A context provider `ThemeContext` (and hook `useTheme`) will manage:
   - Current active theme state: `'light' | 'dark' | 'system'`.
   - LocalStorage persistence.
   - Media query listener for `(prefers-color-scheme: dark)` to automatically toggle classes if theme is `'system'`.

3. **Styling (CSS variables)**:
   Add overrides for CSS variables inside `index.css` under the `.dark` class selector, including backgrounds, shadows, text, selection color, scrollbars, etc.

4. **UI Toggle Component**:
   A dropdown theme selector menu in the `Navbar` (beside search/auth controls).

---

## Proposed Changes

### 1. `apps/frontend/tailwind.config.js`
Enable class-based dark mode:
```diff
  export default {
+   darkMode: 'class',
    content: [
      "./index.html",
```

### 2. `apps/frontend/src/context/ThemeContext.tsx`
[NEW] Implement the provider containing the theme selection logic.

```typescript
import React, { createContext, useContext, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark' | 'system';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const saved = localStorage.getItem('theme') as Theme;
    return saved || 'system';
  });

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem('theme', newTheme);
  };

  useEffect(() => {
    const root = window.document.documentElement;
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const updateTheme = () => {
      const isDark =
        theme === 'dark' ||
        (theme === 'system' && mediaQuery.matches);

      if (isDark) {
        root.classList.add('dark');
      } else {
        root.classList.remove('dark');
      }
    };

    updateTheme();

    if (theme === 'system') {
      mediaQuery.addEventListener('change', updateTheme);
      return () => mediaQuery.removeEventListener('change', updateTheme);
    }
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};
```

### 3. `apps/frontend/src/App.tsx`
Wrap the root element with `ThemeProvider`.

### 4. `apps/frontend/index.css`
Define premium dark mode colors:
```css
/* Dark Mode Override Variables */
.dark {
  --primary-blue: #38bdf8;
  --secondary-blue: #0ea5e9;
  --bg-light: #020617;
  
  --glass-bg: rgba(15, 23, 42, 0.65);
  --glass-border: 1px solid rgba(3, 105, 161, 0.25);
  
  color-scheme: dark;
}

/* Elegant dark gradient backgrounds */
body.dark {
  background: linear-gradient(135deg, #0b0f19 0%, #020617 50%, #0d1226 100%);
  background-size: 200% 200%;
  color: #f1f5f9;
}

body.dark::before {
  background-image:
    radial-gradient(circle at 20% 30%, rgba(3, 105, 161, 0.15) 0%, transparent 40%),
    radial-gradient(circle at 80% 70%, rgba(156, 39, 176, 0.12) 0%, transparent 40%),
    radial-gradient(circle at 50% 50%, rgba(3, 105, 161, 0.1) 0%, transparent 50%);
}

body.dark::after {
  background-image:
    repeating-linear-gradient(90deg, transparent, transparent 50px, rgba(3, 105, 161, 0.04) 50px, rgba(3, 105, 161, 0.04) 51px),
    repeating-linear-gradient(0deg, transparent, transparent 50px, rgba(156, 39, 176, 0.03) 50px, rgba(156, 39, 176, 0.03) 51px);
}

.dark ::selection {
  background: rgba(3, 105, 161, 0.4);
  color: #ffffff;
}

.dark .custom-scrollbar:hover::-webkit-scrollbar-thumb {
  background: rgba(56, 189, 248, 0.2);
}

.dark .custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: var(--primary-blue);
}
```

Ensure tailwind utilities are adjusted for text colors and panel themes where hardcoded light styles might exist (e.g. `bg-white` classes will need to be matched with `dark:bg-slate-900` or `.glass-panel`).

### 5. `apps/frontend/src/components/layout/Navbar.tsx`
Add a beautiful dropdown-based toggle selector in the Navbar.
Use `Sun`, `Moon`, and `Monitor` icons to represent the three options.

---

## Verification Plan

### Manual Verification
- Load page on a device configured for light theme -> background should be light.
- Toggle device theme to dark theme -> page should automatically switch to dark.
- Force Dark Mode via the selector -> page must switch to dark mode.
- Force Light Mode via the selector -> page must switch to light mode.
- Refresh page -> selection must persist.
- Switch to system settings on selector, toggle device settings -> should toggle automatically.
