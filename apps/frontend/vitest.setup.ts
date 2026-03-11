import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock Gladly or other browser globals if needed
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // deprecated
    removeListener: vi.fn(), // deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Global mock for translations so tests can assert against translation keys directly
vi.mock('@/src/i18n/I18nContext', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/src/i18n/I18nContext')>();
  return {
    ...actual,
    useI18n: () => ({
      t: (key: string, params?: Record<string, string | number>) => {
        if (params) {
          return Object.entries(params).reduce(
            (s, [k, v]) => s.replace(`{{${k}}}`, String(v)),
            key
          );
        }
        return key;
      },
      language: 'en',
      setLanguage: vi.fn(),
    }),
  };
});

// Mock ResizeObserver
global.ResizeObserver = class {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
} as any;

// Mock IntersectionObserver
global.IntersectionObserver = class {
  constructor(callback: any) {
    this.callback = callback;
  }
  callback: any;
  root = null;
  rootMargin = '';
  thresholds = [];
  takeRecords = vi.fn();
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
} as any;

// Mock scrollIntoView
window.HTMLElement.prototype.scrollIntoView = vi.fn();

// Mock localStorage
const localStorageMock = (function() {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn(key => store[key] || null),
    setItem: vi.fn((key, value) => {
      store[key] = value.toString();
    }),
    removeItem: vi.fn(key => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    })
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true
});
