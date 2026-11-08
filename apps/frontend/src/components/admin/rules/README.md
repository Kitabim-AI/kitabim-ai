# Auto-Correct Rules Admin Component (`admin/rules`)

## Overview
Provides the administrative user interface for viewing, searching, creating, editing, toggling, and deleting global Uyghur spell-check auto-correction rules with infinite-scroll pagination and summary statistics.

## Interface
- `[AutoCorrectRulesPanel.tsx:AutoCorrectRulesPanel]` — Named and default exported React functional component rendering the CRUD table, search bar, statistics cards, and modal forms for global auto-correction spell rules.

## Invariants
- `[AutoCorrectRulesPanel.tsx:loadRules]` — Non-initial pagination loads bail early if `isLoading`, `isLoadingMore`, or `!hasMore` is true; `pageSize` is fixed at `20` and `hasMore` requires `data.items.length === pageSize` and loaded item count `< data.total`.
- `[AutoCorrectRulesPanel.tsx:loadRules]` — Appending rules on subsequent pages deduplicates incoming `data.items` by checking against existing `rule.id` values.
- `[AutoCorrectRulesPanel.tsx:handleSubmit]` — Submitting a rule requires non-empty trimmed `misspelled` and `corrected` values (`!misspelled.trim() || !corrected.trim()`); when editing (`!!editingRule`), the `misspelled` input is disabled and `misspelled_word` is omitted from the PATCH body while used as the URL path parameter.

## Side Effects
- `[AutoCorrectRulesPanel.tsx:loadStats]` — Calls `authFetch('/api/auto-correct-rules/stats')` (`GET`) on mount, refresh, rule create/edit, delete, and active toggle.
- `[AutoCorrectRulesPanel.tsx:loadRules]` — Calls `authFetch('/api/auto-correct-rules?skip=...&limit=...&search=...')` (`GET`) on initial load, debounced search change (500ms timeout), refresh, and `IntersectionObserver` trigger.
- `[AutoCorrectRulesPanel.tsx:handleSubmit]` — Calls `authFetch('/api/auto-correct-rules', { method: 'POST', ... })` when creating a rule or `authFetch('/api/auto-correct-rules/${editingRule.misspelled_word}', { method: 'PATCH', ... })` when editing a rule; invokes `window.alert` on error.
- `[AutoCorrectRulesPanel.tsx:handleDelete]` — Calls `authFetch('/api/auto-correct-rules/${isDeleting.misspelled_word}', { method: 'DELETE' })`; invokes `window.alert` on error.
- `[AutoCorrectRulesPanel.tsx:toggleRuleActive]` — Calls `authFetch('/api/auto-correct-rules/${rule.misspelled_word}', { method: 'PATCH', ... })` to invert `is_active`; invokes `window.alert` on error.
- `[AutoCorrectRulesPanel.tsx:AutoCorrectRulesPanel]` — Renders Add/Edit and Delete confirmation modals directly into `document.body` via `createPortal`, sets up an `IntersectionObserver` on `loaderRef`, and auto-focuses `inputRef` after 50ms on mount.

## Verification
- Run: `npm test`
