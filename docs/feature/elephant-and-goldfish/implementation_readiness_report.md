# Stage 9 Implementation Readiness Report

**Target:** `/Users/Omarjan/Projects/kitabim-ai/docs/feature/elephant-and-goldfish/2026-11-01-in-pipeline-chat-guardrails-design.md` (`Lines 190..259`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

## Severity Breakdown
- 🔴 **Blocker**: 3
- 🟡 **Major**: 5
- 🟢 **Nit**: 3

---

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. AttributeError on Nullable Guardrail Signals in Orchestrator - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 225-226 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: The implementation plan instructs the orchestrator to inspect `signals.get("guardrail", {}).get("is_refusal")`. In Python, if Gemini outputs `"guardrail": null` or if the key is present with a value of `None`, `signals.get("guardrail", {})` evaluates to `None` (the default `{}` is only returned if the key is entirely missing). Invoking `.get("is_refusal")` on `None` immediately raises an unhandled `AttributeError: 'NoneType' object has no attribute 'get'`, crashing the streaming generator.
* **Rationale & Recommendation**: Adopt safe null coalescing in `packages/backend-core/app/services/chat/orchestrator.py`:
  ```python
  guardrail = signals.get("guardrail") or {}
  if guardrail.get("is_refusal"):
      ...
  ```

---

### 2. `rag_eval_job` Enqueue Bypass Vulnerability in Orchestrator - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 229-230 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: Line 229 specifies: *"In the RAGEvaluation persistence block, explicitly set eval_status = 'skipped' when short-circuited to ensure the ARQ worker does not queue rag_eval_job."* However, in `packages/backend-core/app/services/chat/orchestrator.py` lines 830-840, the background job enqueue block checks only:
  ```python
  if judge_scoring_enabled:
      await redis_pool.enqueue_job("rag_eval_job", eval_id=eval_id, ...)
  ```
  `judge_scoring_enabled` is derived purely from the database system configuration (`rag_judge_scoring_enabled`), without checking `eval_status`. If the orchestrator executes or falls through to this block, `rag_eval_job` will still be enqueued despite `eval_status == "skipped"`, violating Goal G-6 and consuming background LLM evaluation slots.
* **Rationale & Recommendation**: Explicitly mandate that the short-circuit handler must either execute a self-contained exit that returns prior to reaching line 830, or amend line 830 to:
  ```python
  if judge_scoring_enabled and eval_status != "skipped":
  ```

---

### 3. Undefined Method `CostTracker.get_snapshot()` Runtime Crash - Severity: 🔴 Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Line 138 & Line 230 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: Section 7.2.3 (line 138) defines the final short-circuit event as `yield {"type": "done", "used_book_ids": [], "cost": ctx.cost_tracker.get_snapshot()}`. In `packages/backend-core/app/llm/cost_tracker.py`, `CostTracker` does not implement `get_snapshot()`. Calling this method causes a fatal `AttributeError: 'CostTracker' object has no attribute 'get_snapshot'`.
* **Rationale & Recommendation**: The actual dictionary serializer on `CostTracker` is `as_dict()`. Align the implementation plan with existing usage in `orchestrator.py`:
  ```python
  cost = ctx.cost_tracker.as_dict()
  ```

---

### 4. Missing `eval_id` and `conversation_id` in Short-Circuit `done` Event - Severity: 🟡 Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Line 138 & Line 230 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: The `done` event schema defined in line 138 omits `eval_id` and `conversation_id`. However, the orchestrator's synchronous facade wrapper `answer()` in `orchestrator.py` lines 893-898 explicitly extracts `done_meta.get("conversation_id")` and `done_meta.get("eval_id")`. Frontend clients and unit test fixtures also validate these fields on completion. Omitting them causes `answer()` to return `None` for both identifiers.
* **Rationale & Recommendation**: Specify the complete `done` payload contract matching standard orchestrator behavior:
  ```python
  yield {
      "type": "done",
      "eval_id": eval_id,
      "conversation_id": conv_id,
      "used_book_ids": [],
      "cost": cost,
  }
  ```

---

### 5. Ambiguous Execution Order for Stage 0.5 Regex Check - Severity: 🟡 Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Line 224 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: Line 224 states: *"At the start of stream_response (before detect_phrase_intent and detect_short_work_intent), check _HEURISTIC_PROBE_REGEX.search(request_dto.question)."* At the absolute entry point of `stream_response` (line 209), conversation get-or-create has not run, `conv_id` is unbound, and `QueryContext` (`ctx`) is not yet initialized. If short-circuiting triggers there, the turn cannot be saved to `ConversationRepository`, and `ctx.cost_tracker` cannot be queried.
* **Rationale & Recommendation**: Clarify the exact code location: Stage 0.5 must be evaluated immediately *after* conversation resolution (line 240) and `QueryContext` setup (line 291), immediately preceding `detect_phrase_intent` (line 303).

---

### 6. Answer Agent Fallback Prompt Ineffective When Context Is Populated - Severity: 🟡 Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 235-238 (`packages/backend-core/app/services/chat/answer_prompts.py`)
* **Discrepancy Description**: Lines 235-238 instruct to remove line 89 permissive guidance and add the domain fallback instruction. In `answer_prompts.py` lines 84-90, line 89 is a sub-clause inside `inst_7`, which begins: *"If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:"*. If an adversarial probe or off-topic query matches any book text (e.g., retrieving chunks matching "system", "code", or "instructions"), `graded_context` is not empty, causing the model to skip `inst_7` entirely and rendering the fallback instruction inactive.
* **Rationale & Recommendation**: Position the fallback domain guardrail as an independent, unconditional top-level rule in `instructions` in `build_answer_instructions`, rather than nesting it under `inst_7`.

---

### 7. Underspecified `<user_query>` Delimiter Sanitization in `query_signals.py` - Severity: 🟡 Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Line 208 & Line 243 (`packages/backend-core/app/services/chat/query_signals.py`)
* **Discrepancy Description**: Line 208 directs the developer to *"Wrap {question} inside <user_query> tags in the prompt template with explicit delimiter isolation instructions"*, and Line 243 specifies a unit test to *"Verify delimiter escaping in <user_query> XML tags"*. However, Section 3 provides no specification of the sanitization/escaping algorithm (e.g., replacing `</user_query>` closing tags vs escaping XML entities `&lt;` and `&gt;`).
* **Rationale & Recommendation**: Specify the concrete sanitization step in Section 3:
  ```python
  sanitized_question = question.replace("</user_query>", "&lt;/user_query&gt;")
  ```
  This provides a clear behavioral contract for the test in line 243 to validate.

---

### 8. Missing `intent` Schema Alignment in `query_signals.py` for Refusals - Severity: 🟡 Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Lines 209-215 (`packages/backend-core/app/services/chat/query_signals.py`)
* **Discrepancy Description**: In `packages/backend-core/app/services/chat/query_signals.py` line 105, `"intent"` is restricted to `"catalog" | "dictionary" | "identity" | "summary" | "relationship" | "passage" | "quran"`. When `guardrail.is_refusal` is True, `orchestrator.py` emits `planning` with `intent: "refusal"`. However, the prompt schema does not permit `"refusal"` as an intent or allow `"intent"` to be nullable. This forces Gemini to fabricate an arbitrary literary intent on refused queries.
* **Rationale & Recommendation**: Update the JSON schema in the prompt to include `"refusal"` in `"intent"`, or specify that `"intent"` should be set to `"refusal"` whenever `guardrail.is_refusal == true`.

---

### 9. Missing `import re` in File Modification List for `orchestrator.py` - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 223 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: `packages/backend-core/app/services/chat/orchestrator.py` currently does not import Python's standard `re` module. Defining module-level constant `_HEURISTIC_PROBE_REGEX` requires adding `import re`.
* **Rationale & Recommendation**: Add `import re` to the explicit modification checklist for `orchestrator.py`.

---

### 10. Non-Self-Contained Regex Definition in Plan Item 4 - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** Line 223 (`packages/backend-core/app/services/chat/orchestrator.py`)
* **Discrepancy Description**: Line 223 describes `_HEURISTIC_PROBE_REGEX` verbally without citing the pattern string from Section 7.2.1 (lines 98-100) or providing the exact compiled regular expression.
* **Rationale & Recommendation**: Include the compiled regex definition directly in Item 4 or add an explicit reference to Section 7.2.1:
  ```python
  _HEURISTIC_PROBE_REGEX = re.compile(
      r"(?i)(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt|system\s+instructions|act\s+as\s+dan|developer\s+mode|\[inst\]|<\|im_start\|>|you\s+are\s+now\s+an?|disregard\s+(all\s+)?prior)"
  )
  ```

---

### 11. Incomplete Negative Test Coverage for Agglutinative Uyghur Vocabulary - Severity: 🟢 Nit
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** Lines 247-253 (`packages/backend-core/tests/app/services/test_adk_orchestrator.py`)
* **Discrepancy Description**: Item 7 specifies orchestrator integration tests for Latin regex matching and Gemini guardrail short-circuiting, but omits a negative test verifying that legitimate historical/literary Uyghur queries containing system-like stems (e.g., `سىستېما` in *«مائارىپ سىستېمىسى»*) are not prematurely refused.
* **Rationale & Recommendation**: Add a CUJ-3 test case to `test_adk_orchestrator.py` verifying that agglutinative Uyghur queries with loanwords successfully pass Stage 0.5 and proceed to RAG execution.

