# Walkthrough — Dictionary Similarity and Fallback Fixes

This walkthrough describes the changes implemented to address the production RAG issue where dictionary intent routing resulted in a "not found" answer due to noisy similarity search matching and lack of book search fallback.

## Changes Made

### 1. Dictionary Repository
Updated all fuzzy/similarity trigram filters in [dictionary_repository.py](../../../packages/backend-core/app/db/repositories/dictionary_repository.py) to raise the similarity score threshold from `> 0.2` to `> 0.4`.
- This filters out low-similarity suffix/prefix matches (e.g. matching all events ending with `"ۋەقەسى"` (event) like `"كامېدا ۋەقەسى"`, `"رېم ۋەقەسى"`, etc. for a query about `"كەربەلا ۋەقەسى"`).
- Typo matching (e.g. `"كەربىلا ۋەقەسى"`) and variations (e.g. `"كەربەلا ۋەقە"`) still match successfully with similarity scores > 0.66.

### 2. Deterministic RAG Agent
Updated `DeterministicRAGHandler.execute_path` in [deterministic_handler.py](../../../packages/backend-core/app/services/rag/agent/deterministic_handler.py):
- Modified the `intent == "dictionary"` path to check if any dictionary entries were found after executing the selected dictionary tools.
- If no results are found (e.g., `total_found == 0`), it falls back to a global book chunk query via `search_chunks(query, book_ids=None)`. This ensures that even if a historical term/concept isn't in our history dictionary tables, the agent will look it up in library books (e.g., finding the page detailing the "Karbala event" in "‎⁨ئىسلام تارىخى").

### 3. Tests
Added `test_execute_path_dictionary_history_to_chunks_fallback` to [deterministic_router_test.py](../../../packages/backend-core/tests/app/services/deterministic_router_test.py) to verify that if dictionary lookups return 0 matches, the execution router correctly delegates to `search_chunks`.

---

## Verification Results

### 1. Verification of Noisy Matches Filtering
Running the dictionary lookup query for `"كەربەلا ۋەقەسى"` returns **0** entries from the history dictionary (filtering out `كامېدا ۋەقەسى`, `كۇتۇكۇ ۋەقەسى`, etc.), which correctly triggers the fallback:
```
Found 0 entries:
```

### 2. Unit Tests
All `backend-core` tests pass successfully:
```bash
.venv/bin/pytest packages/backend-core/tests/
```
Output:
```
====================== 269 passed, 75 warnings in 28.46s =======================
```
Specifically, all 23 tests in `deterministic_router_test.py` pass:
```bash
.venv/bin/pytest packages/backend-core/tests/app/services/deterministic_router_test.py -v
```
Output:
```
============================== 23 passed in 1.20s ==============================
```

### 3. Local Deployment
The docker compose backend service has been rebuilt and successfully restarted:
```bash
./deploy/local/rebuild-and-restart.sh backend
```
Output:
```
✅ backend rebuilt and restarted
```
