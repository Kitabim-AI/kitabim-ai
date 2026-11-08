# Common Component (`common`)

## Overview
Provides shared application UI primitives including localized markdown rendering with table of contents detection and Quranic diacritics styling, confirmation and alert modals, toast notifications, user avatars, language switching, rotating research questions, and proverb displays.

## Interface
- `[LanguageSwitcher.tsx:LanguageSwitcher]` — Language selector dropdown toggling application locale between Uyghur (`ug`) and English (`en`).
- `[MarkdownContent.tsx:MarkdownContent]` — Localized markdown renderer with citation badges, table formatting, and Quranic Arabic diacritics font adaptation.
- `[MarkdownContent.tsx:isTocPageContent]` — Regex and keyword heuristic utility detecting whether page text represents a Table of Contents.
- `[Modal.tsx:Modal]` — Reusable dialog supporting `'alert' | 'confirm' | 'success'` variants with body scroll locking and backdrop dismiss.
- `[NotificationContainer.tsx:NotificationContainer]` — Toast notifications display container subscribing to `NotificationContext`.
- `[ProverbDisplay.tsx:ProverbDisplay]` — Component querying and presenting random or keyword-matched Uyghur proverbs.
- `[QuestionRotator.tsx:QuestionRotator]` — Fading carousel cycling through community and featured research questions.
- `[UserAvatar.tsx:UserAvatar]` — Profile avatar rendering remote user image with automatic fallback to name initials.

## Invariants
- `[MarkdownContent.tsx:shouldUseArabicFont]` — Automatically switches font styling to `arabic-text` only when Arabic script containing diacritics is detected.
- `[Modal.tsx:useEffect]` — Locks `document.body.style.overflow = 'hidden'` while modal is mounted and visible.
- `[UserAvatar.tsx:hasError]` — If user image fails to load (`onError`), switches state to display first letter initials over a gradient background.

## Side Effects
- `[LanguageSwitcher.tsx:setLanguage]` — Updates active language in `I18nContext`.
- `[ProverbDisplay.tsx:PersistenceService.getRandomProverb]` — Calls persistence service to fetch random proverb data.
- `[QuestionRotator.tsx:PersistenceService.getFeaturedQuestions]` — Calls persistence service to fetch top featured questions.
- `[NotificationContainer.tsx:removeNotification]` — Removes notifications from global context on dismiss.

## Verification
- Run: `npm test`
