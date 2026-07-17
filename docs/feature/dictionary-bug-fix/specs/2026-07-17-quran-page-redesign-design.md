# Quran Page Selection & Search Redesign

This document outlines the design specification for updating the selection controls and keyword search on the Quran page in Kitabim-AI.

## Background & Objective
Currently, the Quran page features a merged search/surah input dropdown. The user wants to split this into:
1. A dedicated, typeable Surah dropdown.
2. A dedicated, typeable Ayah dropdown (dependent on the selected Surah, with an option to view all ayahs).
3. A dedicated Global Search Box.

### Layout Requirements
- **Desktop**: All three controls (Surah dropdown, Ayah dropdown, and Global Search box) are displayed side-by-side in a horizontal row.
- **Mobile**: The Global Search box is at the top. The Surah and Ayah dropdowns are positioned side-by-side directly below it.

### Behavior & Interaction
- **Surah Dropdown**:
  - Displays the active surah name by default (default is Surah 1).
  - Typeable: typing in the input filters the list of surahs by surah number, English name, or Uyghur name.
  - Selecting a surah populates the Ayah dropdown with options corresponding to that surah.
- **Ayah Dropdown**:
  - Displays the active ayah number or "All Ayahs" (optional, default: not selected).
  - Typeable: typing a number filters the list of ayahs.
  - If no ayah is selected, all ayahs in the selected surah are displayed.
- **Global Search Box**:
  - Dedicated text input box.
  - When the user types a keyword and searches, a global search is triggered.
  - Triggering a global search resets the active Surah and Ayah dropdown values to clear/empty.
  - Clearing the global search restores the default surah view (Surah 1, all ayahs).
- **Aesthetic**:
  - Styled to match the premium "user role dropdown" in [UserManagementPanel.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/admin/users/UserManagementPanel.tsx).
  - Interactive states (focus, hover), dark mode support, and smooth transition animations.

## Proposed Changes

### [MODIFY] [QuranView.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/pages/QuranView.tsx)
- Reorganize layout container to implement responsive desktop/mobile placement.
- Replace the single search/dropdown input with three distinct components:
  1. **Surah Combobox**: Styled input + dropdown list wrapper.
  2. **Ayah Combobox**: Styled input + dropdown list wrapper.
  3. **Global Search Input**: Styled input + search/clear buttons.
- Update React states to track:
  - `activeSurah` (defaults to 1)
  - `activeAyah` (optional, defaults to null)
  - `surahSearchQuery` (state for typeable filtering)
  - `ayahSearchQuery` (state for typeable filtering)
  - `globalSearchQuery` (state for keywords)
  - Open/focused states for both dropdown menus.
- Implement reset behavior on global search execution and clearing.

## Verification Plan

### Automated Tests
- Run React/Vite build validation to ensure no type errors.
- Validate local Docker Compose dev services build successfully.

### Manual Verification
- Test selecting Surah 1 and verifying that the Ayah dropdown lists 1–7.
- Test filtering Surah dropdown by typing "Baqarah" or "2" and selecting it.
- Verify Ayah dropdown populates with 1–286.
- Test selecting Ayah 5 to show only Ayah 5.
- Test global search for a keyword (e.g. "مۇھەممەد") and verify that dropdowns reset and search results are loaded.
- Test clearing the search box to verify that it restores Surah 1.
- Verify mobile rendering: search box at top, dropdowns side-by-side.
