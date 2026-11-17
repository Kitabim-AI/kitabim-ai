# Admin Blueprint (`admin`)

## Overview
Administrative management console providing book pipeline milestone monitoring, manual processing action dispatch, user role administration, dictionary editorial suites, system configuration, auto-correction spell rules, question curation, volunteer submissions, and platform statistics.

## Interface
- `[index.ts:AdminTabs]` — Tabbed navigation wrapper managing access across administrative tools.
- `[index.ts:AdminView]` — Primary dashboard displaying books, pipeline progress milestones, status filters, and pipeline trigger menus.
- `[index.ts:UserManagementPanel]` — Re-exported user management panel from `./users`.
- `[ActionMenu.tsx:ActionMenu]` — Dropdown action menu triggering manual pipeline stages (OCR, Structure, Chunking, Embedding, Spell-check, Graph, Summary).
- `[AdminQuestions.tsx:AdminQuestions]` — Table and filter manager for user questions and search queries.
- `[AdminTabs.tsx:AdminTabs]` — Guarded tabs container allowing role-based access for editors and administrators.
- `[ContactSubmissionsPanel.tsx:ContactSubmissionsPanel]` — Panel viewing volunteer submissions and contact inquiries.
- `[ProgressBar.tsx:ProgressBar]` — Visual completion bar illustrating page milestone counts across pipeline stages.
- `[QuestionDetailModal.tsx:QuestionDetailModal]` — Modal displaying question context, answered chunks, and curation status.
- `[StatsPanel.tsx:StatsPanel]` — System-wide analytics and usage statistics dashboard.
- `[TagEditor.tsx:TagEditor]` — Book genre, era, category, and subject tag editor component.
- Subdirectories:
  - `config`: [./config/README.md](./config/README.md) - System configuration key-value CRUD panel and AI circuit breaker controls.
  - `dictionary`: [./dictionary/README.md](./dictionary/README.md) - Uyghur definition, proverbs, historical vocabulary, names, and English-Uyghur dictionaries.
  - `rules`: [./rules/README.md](./rules/README.md) - Global auto-correction spell-check rules CRUD management and activation toggle.
  - `synonyms`: [./synonyms/README.md](./synonyms/README.md) - Uyghur synonym dictionary browsing, search, and administrator deletion.
  - `users`: [./users/README.md](./users/README.md) - User role assignments, account activation toggle, and user search.
  - `words`: [./words/README.md](./words/README.md) - Spell-check dictionary words browser with Uyghur letter-group filtering and deletion.

## Invariants
- `[AdminTabs.tsx:AdminTabs]` — Requires editor or admin privileges (`useIsEditor()`); unprivileged access renders an unauthorized access notice.
- `[AdminTabs.tsx:visibleTabs]` — Filters tabs based on admin status (`isAdmin`), hiding users, questions, stats, contacts, and config tabs from non-admin editors.
- `[AdminView.tsx:getStatusTextColor]` — Maps pipeline status constants (`ready`, `embedding`, `spell_check`, `chunking`, `ocr`, `error`) to color-coded styles.

## Side Effects
- `[AdminView.tsx:authFetch]` — Fetches book listings and pipeline status details from backend API endpoints.
- `[ActionMenu.tsx:authFetch]` — Triggers pipeline worker tasks (e.g. re-running OCR, embedding, or graph generation).
- `[ContactSubmissionsPanel.tsx:authFetch]` — Fetches contact form submissions and updates submission statuses.
- `[StatsPanel.tsx:authFetch]` — Fetches system analytics and database statistics.

## Verification
- Run: `npm test`
