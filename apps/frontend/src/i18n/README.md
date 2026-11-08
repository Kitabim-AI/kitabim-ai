# Internationalization (i18n)

## Overview
Custom internationalization (i18n) subsystem providing multilingual support between Uyghur (`ug`, default) and English (`en`), complete with dot-path key resolution, parameter interpolation, and persistent user locale preference.

## Interface
- `[i18n.ts:Language]`: Union type of supported language codes (`'ug' | 'en'`).
- `[i18n.ts:translations]`: Bundled translation dictionary mappings for supported locales (`ug`, `en`).
- `[i18n.ts:defaultLanguage]`: Default language fallback constant (`'ug'`).
- `[i18n.ts:getNestedTranslation]`: Resolves dot-delimited key paths against a locale dictionary object, returning the key if unresolved.
- `[I18nContext.tsx:I18nContext]`: React context object holding active language state and translation helper.
- `[I18nContext.tsx:I18nProvider]`: Provider component managing active language state, persistence, and `t()` parameter interpolation.
- `[I18nContext.tsx:useI18n]`: React hook exposing `{ language, setLanguage, t }`.

## Invariants
- `[i18n.ts:defaultLanguage]`: Default language is strictly Uyghur (`'ug'`).
- `[i18n.ts:getNestedTranslation]`: If a translation path fails to resolve, the function returns the literal path string rather than throwing or returning null.
- `[I18nContext.tsx:useI18n]`: Must be invoked within an `<I18nProvider>`, throwing `Error('useI18n must be used within I18nProvider')` if context is absent.
- `[I18nContext.tsx:I18nProvider]`: Parameter interpolation replaces exact pattern `{{paramKey}}` with stringified values.

## Side Effects
- `[I18nContext.tsx:I18nProvider]`: Reads from and persists active language selection to `localStorage` under key `'kitabim_language'`.

## Verification
- Run: `npm test`

---

## Developer Guide

### Structure
```
src/
├── i18n/
│   ├── i18n.ts              # Core i18n configuration
│   ├── I18nContext.tsx      # React context provider
│   └── README.md            # Component contract and developer guide
└── locales/
    ├── ug.json              # Uyghur translations (default)
    └── en.json              # English translations
```

### Usage

#### 1. Using translations in components
```typescript
import { useI18n } from '../../i18n/I18nContext';

const MyComponent = () => {
  const { t } = useI18n();

  return (
    <div>
      <h1>{t('nav.home')}</h1>
      <p>{t('library.title')}</p>
    </div>
  );
};
```

#### 2. Switching languages
The `LanguageSwitcher` component is available in the navbar. Users can click the globe icon to switch between languages.

```typescript
import { useI18n } from '../../i18n/I18nContext';

const { language, setLanguage } = useI18n();

// Switch to English
setLanguage('en');

// Switch to Uyghur
setLanguage('ug');
```

#### 3. Adding new translations
Add your translation key to both `locales/ug.json` and `locales/en.json`:

**ug.json**
```json
{
  "myFeature": {
    "title": "نامى",
    "description": "چۈشەندۈرۈش"
  }
}
```

**en.json**
```json
{
  "myFeature": {
    "title": "Title",
    "description": "Description"
  }
}
```

#### 4. Translation with parameters
The `t()` function supports simple `{{param}}` interpolation:
```typescript
t('welcome.message', { name: 'Ahmad' })
```

### Translation Keys Organization
- `common.*` - Common UI elements (buttons, labels)
- `app.*` - Application-wide text (name, tagline, footer)
- `auth.*` - Authentication (login/OAuth) UI
- `nav.*` - Navigation menu items
- `home.*` - Home page content
- `library.*` - Library view content
- `book.*` - Book detail content
- `bookCard.*` - Book card component
- `chat.*` - Chat interface
- `reader.*` - Reader view
- `admin.*` - Admin panel
- `spellCheck.*` - Spell check panel
- `notifications.*` - Success/error messages
- `modal.*` - Modal dialogs
- `graph.*` - Knowledge graph view
- `joinUs.*` - Join us / contact page
- `proverbs.*` - Proverbs dictionary
- `quran.*` - Quran view
- `share.*` - Share chat/link modals
- `suggestions.*` - Suggestion/question rotator
- `theme.*` - Theme switcher

### Best Practices
1. **Always add to both language files** - Ensure feature parity between languages
2. **Use descriptive keys** - `nav.home` is better than `h1`
3. **Group related translations** - Keep features together
4. **Keep keys flat when possible** - Don't nest too deeply
5. **Use consistent naming** - Follow existing patterns
