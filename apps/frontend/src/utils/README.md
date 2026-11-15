# Frontend Utilities

## Overview
Provides text formatting, bidirectional script handling, Arabic/Quranic normalization, social share link generation, and Uyghur alphabetical sorting.

## Interface
- `[costUtils.ts:formatAnswerCost]`: Formats dollar costs and token counts into bidirectional-safe Uyghur/English strings.
- `[quranUtils.ts:toEasternArabicDigits]`: Converts Western numbers to Eastern Arabic-Indic numerals (`٠, ١, ٢...`).
- `[quranUtils.ts:formatQuranAyahNumber]`: Formats ayah numbers wrapped in traditional Quranic ornate brackets (`\uFD3F...\uFD3E`).
- `[quranUtils.ts:normalizeArabic]`: Normalizes Uthmanic Quran script into standard Arabic glyphs.
- `[quranUtils.ts:normalizeArabicWithAyah]`: Normalizes Arabic text and appends formatted ayah bracket suffix.
- `[quranUtils.ts:formatQuranAyahUg]`: Cleans Uyghur Quran translations, removing trailing number artifacts and ensuring valid punctuation.
- `[shareText.ts:DEFAULT_SHARE_HASHTAGS]`: Default hashtags string appended to social share posts (`#KitabimAI #Uyghur`).
- `[shareText.ts:cleanShareText]`: Strips markdown ref links and BookID metadata from shareable excerpts.
- `[shareText.ts:formatShareSource]`: Formats clean Uyghur citation lines (`— «Title» (Author), Page`).
- `[shareText.ts:ShareSourceInfo]`: Interface describing source citation metadata (`bookTitle`, `bookAuthor`, `pageNumber`).
- `[shareText.ts:buildSafeTweetText]`: Binary-searches text truncation to safely fit within encoded X (Twitter) intent URL lengths.
- `[shareText.ts:SafeTweetInput]`: Interface defining text structure and URL length budget parameters.
- `[uyghurAlphabet.ts:UYGHUR_ALPHABET]`: Array of 32 Uyghur Arabic alphabet letters in canonical collation order.
- `[uyghurAlphabet.ts:sortByUyghurAlphabet]`: Sorts strings according to canonical Uyghur alphabetical precedence.
- `[uyghurAlphabet.ts:parseDefinition]`: Splits dictionary definition text into chunks of text, metadata tags (`[...]`), and line breaks (`[CRLF]`).
- `[uyghurAlphabet.ts:ParsedChunk]`: Interface representing a parsed definition chunk (`type: 'text' | 'metadata' | 'br'`, `content`).

## Invariants
- `[costUtils.ts:formatAnswerCost]`: Enforces Left-to-Right Mark (`\u200E`) wrapping around numerals and dollar values to prevent bidirectional layout distortion.
- `[shareText.ts:buildSafeTweetText]`: Output text is guaranteed to produce an encoded tweet intent URL within the specified `maxUrlLength`.
- `[uyghurAlphabet.ts:sortByUyghurAlphabet]`: Characters not present in `UYGHUR_ALPHABET` sort after all known alphabet characters.

## Side Effects
- `None`: Pure computational and transformation functions with zero side effects.

## Verification
- Run: `npm test`
