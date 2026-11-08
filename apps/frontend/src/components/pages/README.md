# Pages Component (`pages`)

## Overview
Provides standalone top-level route views for trilingual Quran reading with Surah/Ayah pickers and search, comprehensive Uyghur dictionary browsing across multiple sub-dictionaries, and a community volunteer/contributor landing page.

## Interface
- `[DictionaryView.tsx:default]` — Tabbed container page hosting multi-dictionary views (definition, proverbs, historical vocabulary, history staging, names, English-Uyghur, synonyms, and words).
- `[JoinUsView.tsx:default]` — Volunteer recruitment landing page detailing editor and developer roles, and embedding an interactive contact submission modal.
- `[QuranView.tsx:QuranView]` / `[QuranView.tsx:default]` — Quran reader component offering Arabic script with Uyghur and English translations, Surah/Ayah comboboxes, and text search.

## Invariants
- `[DictionaryView.tsx:isAdmin]` — Conditionally shows the `history-staging` tab only when `useIsAdmin()` evaluates to true.
- `[QuranView.tsx:activeSurah]` — Initializes active surah to Surah 1 (Al-Fatihah) on mount.
- `[JoinUsView.tsx:contactForm]` — Validates non-empty trimmed name, email, and message before dispatching form submission.

## Side Effects
- `[JoinUsView.tsx:submitContactForm]` — Submits volunteer application payload to backend contact service.
- `[QuranView.tsx:authFetch]` — Fetches surah lists and verses via `/api/quran/surahs`, `/api/quran/surahs/${surah}`, and `/api/quran/search`.

## Verification
- Run: `npm test`
