# UI Code Review — 2026-09-18

**Branch:** feature/surya-ocr-client
**Scope:** `apps/frontend/src/components/admin/config/SystemConfigPanel.tsx` — new JSON-aware editing support for `system_configs` values (added by a separate concurrent Claude Code session, now stopped, as part of the `sys_llm_model_pricing` feature).
**Verdict:** Approve with suggestions (findings fixed 2026-09-18)

## Issues

### `apps/frontend/src/components/admin/config/SystemConfigPanel.tsx`

- **Fixed** — both `alert('Invalid JSON format: ...')` call sites now use `t('admin.systemConfig.invalidJson', { error: ... })`. Added the `invalidJson` key to both `locales/en.json` and `locales/ug.json` under the existing `admin.systemConfig` namespace, using the codebase's `{{param}}` interpolation convention. The other pre-existing `alert(err.message || '...')` calls in this file were left as-is (out of scope — they predate this change).
- **Fixed** — `isJsonConfig()` and `tryFormatJson()` moved to module scope, next to the existing `getFeatureGroupForKey()` helper, matching that established pattern in this file.

## Summary

The JSON-aware value editor (auto-detect JSON, pretty-print on edit, textarea instead of single-line input, client-side validation before save) is a well-targeted, self-contained addition for editing `sys_llm_model_pricing` and similar structured config values. Both findings are minor/cosmetic — no correctness, accessibility, RTL, or design-system issues found.
