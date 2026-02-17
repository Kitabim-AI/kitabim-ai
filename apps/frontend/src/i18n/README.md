# Internationalization (i18n) Implementation

This project implements a custom i18n system for managing translations between Uyghur and English.

## Structure

```
src/
├── i18n/
│   ├── i18n.ts              # Core i18n configuration
│   ├── I18nContext.tsx      # React context provider
│   └── README.md            # This file
└── locales/
    ├── ug.json              # Uyghur translations (default)
    └── en.json              # English translations
```

## Usage

### 1. Using translations in components

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

### 2. Switching languages

The `LanguageSwitcher` component is available in the navbar. Users can click the globe icon to switch between languages.

```typescript
import { useI18n } from '../../i18n/I18nContext';

const { language, setLanguage } = useI18n();

// Switch to English
setLanguage('en');

// Switch to Uyghur
setLanguage('ug');
```

### 3. Adding new translations

#### Step 1: Add to translation files

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

#### Step 2: Use in your component

```typescript
const { t } = useI18n();

<h1>{t('myFeature.title')}</h1>
<p>{t('myFeature.description')}</p>
```

### 4. Translation with parameters

While not currently implemented, you can extend the `t()` function to support parameters:

```typescript
// In your component
t('welcome.message', { name: 'Ahmad' })

// In translation file
"welcome": {
  "message": "سالام {{name}}!"
}
```

## Translation Keys Organization

Translations are organized by feature/section:

- `common.*` - Common UI elements (buttons, labels)
- `app.*` - Application-wide text (name, tagline, footer)
- `nav.*` - Navigation menu items
- `home.*` - Home page content
- `library.*` - Library view content
- `bookCard.*` - Book card component
- `chat.*` - Chat interface
- `reader.*` - Reader view
- `admin.*` - Admin panel
- `spellCheck.*` - Spell check panel
- `pagination.*` - Pagination controls
- `notifications.*` - Success/error messages
- `modal.*` - Modal dialogs

## Example: Updating a Component

**Before:**
```typescript
<button>كىتاب قوشۇش</button>
```

**After:**
```typescript
import { useI18n } from '../../i18n/I18nContext';

const MyComponent = () => {
  const { t } = useI18n();

  return (
    <button>{t('nav.addBook')}</button>
  );
};
```

## Components Already Updated

- ✅ Navbar - Navigation menu items and search placeholder
- ✅ LanguageSwitcher - Language selection component

## Components to Update

The following components still have hardcoded text and should be updated:

- [ ] HomeView
- [ ] LibraryView
- [ ] BookCard
- [ ] ChatInterface
- [ ] ReaderView
- [ ] AdminView
- [ ] AdminTabs
- [ ] UserManagementPanel
- [ ] SpellCheckPanel
- [ ] Pagination
- [ ] Modal
- [ ] NotificationContainer

## Best Practices

1. **Always add to both language files** - Ensure feature parity between languages
2. **Use descriptive keys** - `nav.home` is better than `h1`
3. **Group related translations** - Keep features together
4. **Keep keys flat when possible** - Don't nest too deeply
5. **Use consistent naming** - Follow existing patterns

## Default Language

The default language is **Uyghur (ug)**. This is set in `i18n/i18n.ts`:

```typescript
export const defaultLanguage: Language = 'ug';
```

Users can change the language using the LanguageSwitcher component, and their preference will persist for the session.
