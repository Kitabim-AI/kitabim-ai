# Dictionary Similarity Search and Fallback Fixes Implementation Plan

**Goal:** Clean up irrelevant dictionary results by raising trigram similarity threshold to 0.4, and implement a fallback to search library book chunks when dictionary lookups return no matches.

**Architecture:**
- Update similarity threshold filter queries in `DictionaryRepository` from `> 0.2` to `> 0.4` to filter out noise like unrelated suffix matches (e.g. matching "kameda event" for "karbala event").
- Update the deterministic RAG handler (`DeterministicRAGHandler.execute_path`) so that if the query is a dictionary query but no dictionary matches are found, it falls back to a global `search_chunks` call to search library books for the term.
- Add and run pytest cases verifying both the raised similarity threshold and the fallback behavior.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL, pytest

## Global Constraints
- Keep the monorepo structure intact.
- Follow existing Python/SQLAlchemy conventions in the codebase.
- No print statements; use `log_json` for logging.

---

### Task 1: Update Dictionary Similarity Thresholds

**Files:**
- Modify: [dictionary_repository.py](../../../packages/backend-core/app/db/repositories/dictionary_repository.py)

- [ ] **Step 1: Write a failing test for noisy similarity matches**
- [ ] **Step 2: Update the thresholds in `DictionaryRepository`**
- [ ] **Step 3: Run existing and new repository tests**

---

### Task 2: Implement Book Chunk Fallback in Deterministic RAG Handler

**Files:**
- Modify: [deterministic_handler.py](../../../packages/backend-core/app/services/rag/agent/deterministic_handler.py)

- [ ] **Step 1: Modify the execution logic in `execute_path`**
- [ ] **Step 2: Add test cases to verify the fallback logic**

---

### Task 3: Cleanup and Local Verification

- [ ] **Step 1: Run all backend-core tests**
- [ ] **Step 2: Clean up temporary debug script**
- [ ] **Step 3: Build & Restart Docker Compose services**

## Verification Plan

### Automated Tests
- `.venv/bin/pytest packages/backend-core/tests/app/services/deterministic_router_test.py`
- `.venv/bin/pytest packages/backend-core/tests/`

### Manual Verification
- Rebuild/restart backend container.
- Query API locally using `curl` or browser agent to check if the question `"كەربەلا ۋەقەسى قانداق ۋەقە؟"` now retrieves chunks from `"ئىسلام تارىخى"` and receives a complete answer about Karbala.
