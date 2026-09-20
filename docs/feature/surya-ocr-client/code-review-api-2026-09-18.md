# API Code Review — 2026-09-18

**Branch:** feature/surya-ocr-client
**Scope:** Uncommitted changes made by a separate concurrent Claude Code session (now stopped) implementing (a) TODO 6 from `docs/feature/llm-token-cost-optimization/llm-token-cost-optimization-todos.md` — switching `history_gemini_model` default from `gemini-2.5-flash` to `gemini-3.5-flash-lite` — and (b) a follow-on "configurable model pricing via system_configs" feature (migration 094, `pricing.py`, `cost_tracker.py`, `rag_eval_job.py`).
**Verdict:** Approve with suggestions (findings fixed 2026-09-18)

## Issues

### `packages/backend-core/app/llm/pricing.py`

- **Fixed** — removed the unused `MODEL_PRICING = DEFAULT_MODEL_PRICING` alias (line 47). Confirmed no remaining references via grep; `pricing_test.py` already imported `DEFAULT_MODEL_PRICING` directly.

### `packages/backend-core/agent.py`, `app/services/rag/llm_resources.py`, `app/services/history_extraction_service.py`, `app/services/batch_history_extraction_service.py`, `app/db/models.py`

- **Confirmed intentional** — new default model id `gemini-3.5-flash-lite` is used consistently across all five files, migration 093, and the OCR/catalog test mocks, and is correctly registered in `pricing.py`'s `DEFAULT_MODEL_PRICING` and the migration-094 JSON. Author confirmed this is a deliberate default-model swap, not a typo for the codebase's existing `gemini-3.1-flash-lite`.

### `packages/backend-core/app/llm/cost_tracker.py`, `services/worker/jobs/rag_eval_job.py`, `packages/backend-core/app/services/chat/orchestrator.py`

- No issues found. Traced the full flow: `get_model_pricing_from_repo()` is fetched once per chat turn (`orchestrator.py`, before `set_current_query_context`) and once per async judge job (`rag_eval_job.py`), both before any `cost_tracker.add()` / `estimate_cost_usd()` calls happen, so dynamic pricing is applied consistently across every cost-recording call site (`query_signals.py`, `reranker.py`, `judge.py` live path, `orchestrator.py` retrieval/answer stages, and the async judge). `SystemConfigsRepository.get_value` already invalidates its Redis cache key on every config write (pre-existing generic behavior, confirmed at `system_configs_repository.py:48,53`), so an admin editing `sys_llm_model_pricing` via the UI takes effect on the next call without a restart.

### `packages/backend-core/migrations/093_*.sql`, `094_*.sql`

- No issues found. Both are single-purpose, have matching rollbacks, use `ON CONFLICT DO NOTHING` / value-guarded `UPDATE` (won't clobber a value an admin already customized away from the old default), and migration 094's JSON uses the `"input"`/`"output"` key names that `parse_model_pricing()` checks first — confirmed no format mismatch between what's seeded and what's parsed.

### Test files (`batch_ocr_service_test.py`, `catalog_phrase_intent_test.py`)

- **Withdrawn** — originally flagged as unrelated scope creep (mock model-name placeholders changed from `"gemini-2.5-flash"` to `"gemini-3.5-flash-lite"` in tests that don't exercise `history_gemini_model`). Author confirmed this was an intentional broader default-model swap, not incidental churn. No fix needed.

### Everything else touched (`app/db/models.py`, `history_extraction_service_test.py`, `batch_history_extraction_service_test.py`, `models_test.py`)

- No issues found — all changes are correctly scoped, consistent one-liners tracking the model-default switch. The 3 pre-existing failures in `models_test.py::test_protected_llm_timeout_*` are unrelated: confirmed via `git stash` that they fail identically against the clean committed baseline (before either this session's or the other session's changes), so they are not a regression introduced by this diff.

## Summary

The change is a clean, well-scoped extension of the existing cost-tracking work: it makes Gemini model pricing configurable at runtime via `system_configs` (with correct Redis cache invalidation and consistent threading of the dynamic pricing map through every cost-computation call site, live and async), and separately lowers the history-extraction model's default cost. No correctness, security, or architecture issues found. The two flagged items are cosmetic (an unused backward-compat alias, and incidental unrelated test-string churn) and one is a "please double-check this is the intended model id" flag rather than a defect.
