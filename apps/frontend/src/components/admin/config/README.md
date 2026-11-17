# System Configuration Admin Component (`admin/config`)

## Overview
Provides administrative key-value system configuration management, category filtering by feature prefixes, JSON syntax validation and pretty-printing, and AI circuit breaker status monitoring and manual reset controls.

## Interface
- `[index.ts:SystemConfigPanel]` — Re-exports `SystemConfigPanel` from `./SystemConfigPanel`.
- `[SystemConfigPanel.tsx:SystemConfigPanel]` — Exported React functional component (`SystemConfigPanel`) providing CRUD management for system configurations, prefix-based feature grouping, JSON validation/formatting, and circuit breaker status monitoring/resetting.

## Invariants
- `[SystemConfigPanel.tsx:isAdmin]` — Editing, creating, and circuit breaker reset/trip actions are guarded for administrators via `useIsAdmin()`.
- `[SystemConfigPanel.tsx:isJsonConfig]` — Configurations with key `'sys_llm_model_pricing'` or values delimited with `{...}` / `[...]` are validated via `JSON.parse` before save; invalid JSON alerts the user and aborts save.
- `[SystemConfigPanel.tsx:FEATURE_GROUPS]` — Configs are mapped to feature categories (`ocr_`, `rag_`, `embed_`, `kg_`, `summary_`, `spell_`, `sys_`) based on key prefix, falling back to `'sys'`.

## Side Effects
- `[SystemConfigPanel.tsx:loadConfigs]` — Authenticated HTTP `GET` to `/api/system-configs/`.
- `[SystemConfigPanel.tsx:loadCircuitBreakerStatus]` — Authenticated HTTP `GET` to `/api/system-configs/circuit-breaker/status`.
- `[SystemConfigPanel.tsx:resetCircuitBreaker]` — Authenticated HTTP `POST` to `/api/system-configs/circuit-breaker/reset` (with optional `?name=...`).
- `[SystemConfigPanel.tsx:forceOpenCircuitBreaker]` — Authenticated HTTP `POST` to `/api/system-configs/circuit-breaker/open` (with optional `?name=...`).
- `[SystemConfigPanel.tsx:handleCreate]` — Authenticated HTTP `POST` to `/api/system-configs/` with `{ key, value, description }`.
- `[SystemConfigPanel.tsx:handleUpdate]` — Authenticated HTTP `PUT` to `/api/system-configs/${key}` with `{ value, description }`.
- `[SystemConfigPanel.tsx:useEffect]` — Auto-focuses `inputRef` after a 50ms delay on mount.

## Verification
- Run: `npm test`
