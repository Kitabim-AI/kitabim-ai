# System Config Model Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Configure Gemini model prices via `system_configs` (`sys_llm_model_pricing`) so rates can be managed dynamically at runtime with Redis caching and UI JSON validation.

**Architecture:** A JSON configuration key `sys_llm_model_pricing` stored in `system_configs` is parsed by `app.llm.pricing`, cached in Redis via `SystemConfigsRepository`, and provided to `CostTracker` and `rag_eval_job`. The existing static pricing table serves as a safe fallback. The admin frontend (`SystemConfigPanel.tsx`) provides a formatted JSON editor with client-side syntax validation.

**Tech Stack:** Python, FastAPI, SQLAlchemy, PostgreSQL, Redis, React, TypeScript

---

### Task 1: Database Migration & Seeding

**Files:**
- Create: `packages/backend-core/migrations/094_seed_model_pricing_system_config.sql`
- Create: `packages/backend-core/migrations/094_rollback_seed_model_pricing_system_config.sql`
- Modify: `packages/backend-core/app/db/seeds.py`
- Test: `packages/backend-core/tests/app/db/seeds_test.py`

- [ ] **Step 1: Create migration 094 and rollback SQL files**
- [ ] **Step 2: Add `sys_llm_model_pricing` to `defaults` in `app/db/seeds.py`**
- [ ] **Step 3: Run `pytest packages/backend-core/tests/app/db/seeds_test.py` and verify passing**

---

### Task 2: Pricing Module & CostTracker Updates

**Files:**
- Modify: `packages/backend-core/app/llm/pricing.py`
- Modify: `packages/backend-core/app/llm/cost_tracker.py`
- Create: `packages/backend-core/tests/app/llm/pricing_test.py`

- [ ] **Step 1: Write comprehensive unit tests in `pricing_test.py`**
- [ ] **Step 2: Implement JSON parsing, fallback merging, and `get_model_pricing_from_repo` in `pricing.py`**
- [ ] **Step 3: Update `CostTracker` in `cost_tracker.py` to support dynamic pricing map and fallback price**
- [ ] **Step 4: Run `pytest packages/backend-core/tests/app/llm/pricing_test.py` and verify passing**

---

### Task 3: Pipeline Integration (Orchestrator & Worker)

**Files:**
- Modify: `packages/backend-core/app/services/chat/orchestrator.py`
- Modify: `services/worker/jobs/rag_eval_job.py`

- [ ] **Step 1: Wire `get_model_pricing_from_repo` into `orchestrator.py` to configure `ctx.cost_tracker`**
- [ ] **Step 2: Wire `get_model_pricing_from_repo` into `rag_eval_job.py` for dynamic `judge_cost_usd` estimation**

---

### Task 4: Admin Panel JSON Editor & Validation

**Files:**
- Modify: `apps/frontend/src/components/admin/config/SystemConfigPanel.tsx`

- [ ] **Step 1: Add JSON detection, textarea rendering, and pretty-printing to `SystemConfigPanel.tsx`**
- [ ] **Step 2: Add client-side JSON syntax validation on save with user-friendly error display**

---

### Task 5: Verification & Testing

- [ ] **Step 1: Run all test suites: `pytest packages/backend-core/tests/app/llm/pricing_test.py` and `pytest packages/backend-core/tests/app/db/seeds_test.py`**
- [ ] **Step 2: Build frontend to verify TypeScript types and bundle: `npm run build` in `apps/frontend`**
