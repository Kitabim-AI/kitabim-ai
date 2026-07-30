# RAG Pipeline Design Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the scattered pipeline-stage coverage in `docs/main/WORKER_DESIGN.md`, `docs/main/BOOK_PROCESSING_DIAGRAM.md`, and the three chat docs with 8 standardized, current-state-only design docs — one per RAG pipeline stage.

**Architecture:** No code changes. Each task researches one pipeline stage's actual current implementation (services, repos, worker jobs/scanners, routers, tests), writes one `docs/main/<STAGE>_DESIGN.md` file following a fixed 14-section template, and verifies every factual claim against the live codebase before committing. A final cleanup task trims the two multi-stage docs down to cross-cutting content only, deletes the three now-superseded chat docs, and updates the doc indexes.

**Tech Stack:** Markdown, Mermaid `flowchart TD` diagrams. No build step — docs are plain files under `docs/main/`.

**Spec:** `docs/superpowers/specs/2026-07-29-rag-pipeline-design-docs-design.md`

## Global Constraints

- All 8 new docs go in `docs/main/`, named `SCREAMING_SNAKE_CASE.md` exactly as listed in each task below.
- Every doc follows the 14-section template in full (below). A section marked *(optional)* is omitted entirely — no heading, no "N/A" — when it doesn't apply to that stage.
- Diagrams are Mermaid `flowchart TD` only, reusing the existing color convention: `classDef idle fill:#e9edc9,stroke:#606c38`, `classDef active fill:#fff3cd,stroke:#856404`, `classDef done fill:#d4f1f4,stroke:#189ab4`, `classDef fail fill:#ffcccb,stroke:#d32f2f` (see `docs/main/WORKER_DESIGN.md`'s State Machine section for the reference pattern).
- Every fact in a doc — file path, function/class name, DB column, `system_configs`/env var key and default, endpoint route, required role — must be verified against the current repository at authoring time. Do not trust this plan's file lists as final; they are a starting point and the code may have drifted since the spec was written.
- Docs describe only current, shipped behavior. No roadmap language, no "TODO", no "planned" features.
- One commit per doc (per task) — do not batch multiple docs into a single commit.
- API Endpoints tables (Section 11) must show the actual role from the endpoint's auth dependency (e.g. `Depends(require_role("editor"))`), read directly from the router source — never inferred or guessed.

## Standard Template (all 8 docs)

```markdown
# <Stage Name> — Design

<one-line cross-link to sibling stage docs and WORKER_DESIGN.md>

## Overview
<1-2 paragraphs: what this stage does, where it sits in the pipeline, key characteristics as bullets>

## Feature Flags                (optional)
| Flag | Default | Gates |

## Schema
<one table per DB table this stage reads/writes, columns + types + description>

## Architecture
<file tree/list: service/repo/job/scanner/router files with one-line purpose each>

## Data Flow
```mermaid
flowchart TD
<scoped to this stage: trigger -> scanner claim -> job -> outbox event -> handoff to next stage>
```

## Component Responsibilities
<per scanner/job/service: numbered pseudocode steps, e.g.>
**<JobName>(<args>):**
```
1. ...
2. ...
```

## State Machine                (optional — only if this stage owns milestone states)
```mermaid
flowchart TD
<milestone states and transitions>
```

## Error Handling & Retries
| Scenario | Behavior |

## Configuration Reference
| Key | Default | Used by |
<cost/perf tradeoffs noted inline as a row note, not a separate section>

## API Endpoints                (optional — only if this stage has endpoints)
| Endpoint | Role required | Effect |

## Security Considerations      (optional — only if there's something beyond the role table above)

## Testing
<pointer(s) to the actual test file(s) covering this stage>

## Related Docs
<links to sibling stage docs, WORKER_DESIGN.md, SYSTEM_DESIGN.md as relevant>
```

---

### Task 1: Document Discovery design doc

**Files:**
- Create: `docs/main/DOCUMENT_DISCOVERY_DESIGN.md`
- Research (read, do not modify): `services/worker/scanners/gcs_discovery_scanner.py`, `packages/backend-core/app/services/storage_service.py`, `packages/backend-core/app/services/pdf_service.py`, `packages/backend-core/app/db/repositories/books_repository.py`, `services/backend/api/endpoints/books_router.py` (upload-related routes only), `docs/main/WORKER_DESIGN.md` (GcsDiscoveryScanner section), `docs/main/BOOK_PROCESSING_DIAGRAM.md` (Triggers subgraph)
- Test file to locate and cite: search `packages/backend-core/tests/` and `services/worker/tests/` for discovery/upload/GCS-related test files (exact filename discovered during research — cite what actually exists)

**Interfaces:**
- Consumes: nothing (first doc; establishes the pattern the rest follow)
- Produces: `docs/main/DOCUMENT_DISCOVERY_DESIGN.md` with top-level `##` headings matching the Standard Template exactly, so later tasks (Task 9) can link to it by heading anchor

- [ ] **Step 1: Read all research files listed above**

Read each file in full. Note: how a book enters the system (manual upload endpoint vs. `GcsDiscoveryScanner` polling `uploads/`), how duplicates are detected (filename match, content-hash match), what a newly-discovered book's initial DB row looks like (`status`, milestone columns, `Page` stub rows), and any config values (`system_configs` keys or env vars) that control scanner cadence or batch size for this stage specifically.

- [ ] **Step 2: Locate the test file(s) for this stage**

```bash
grep -rl "gcs_discovery_scanner\|GcsDiscoveryScanner" packages/backend-core/tests services/worker/tests 2>/dev/null
grep -rl "storage_service\|pdf_service" packages/backend-core/tests 2>/dev/null
```

Note the exact file path(s) returned — these go in the doc's Testing section. If none are found, write "No dedicated test file found for this stage as of <today's date>" rather than inventing a path.

- [ ] **Step 3: Draft `docs/main/DOCUMENT_DISCOVERY_DESIGN.md` following the Standard Template**

Include:
- Overview: manual upload path vs. GCS-scanner discovery path, and that both converge on the same `Book` + `Page` stub creation.
- Schema: the `books` table columns touched at creation time (`status`, `upload_date`, whichever milestone/pipeline_step defaults are set), and `pages` table stub row shape.
- Architecture: the file list above with one-line purposes.
- Data Flow: a mermaid diagram showing both entry points (manual upload endpoint, `GcsDiscoveryScanner` cron) converging on `InitDB` (book + page stubs created), matching the `Triggers` subgraph style already in `BOOK_PROCESSING_DIAGRAM.md` but scoped to discovery only (stop at the "book+pages exist" node — do not continue into OCR).
- Component Responsibilities: `GcsDiscoveryScanner` as numbered steps (already documented in `WORKER_DESIGN.md` — re-verify against current source, don't just copy), plus the manual upload endpoint's handler logic.
- API Endpoints: the upload endpoint(s) in `books_router.py`, with role required read from the actual `Depends(...)` on that route.
- Security Considerations: file-type/size validation on upload, GCS signed URL usage if present, content-hash duplicate detection as a de-dup/integrity measure.
- Testing: the file(s) found in Step 2.
- Related Docs: link to `OCR_DESIGN.md` (next stage) and `WORKER_DESIGN.md`.

- [ ] **Step 4: Verify every factual claim**

For every file path cited in the doc, confirm it exists:
```bash
for f in services/worker/scanners/gcs_discovery_scanner.py packages/backend-core/app/services/storage_service.py packages/backend-core/app/services/pdf_service.py packages/backend-core/app/db/repositories/books_repository.py services/backend/api/endpoints/books_router.py; do test -f "$f" && echo "OK: $f" || echo "MISSING: $f"; done
```
For every function/column/config-key name cited, grep the source file to confirm it's spelled and used exactly as written in the doc:
```bash
grep -n "<name>" <file>
```
Fix any doc content where a path is `MISSING` or a grep finds nothing — either the code has drifted from this plan's assumptions, or the doc has a typo.

- [ ] **Step 5: Commit**

```bash
git add docs/main/DOCUMENT_DISCOVERY_DESIGN.md
git commit -m "docs: add Document Discovery pipeline stage design doc"
```

---

### Task 2: OCR design doc

**Files:**
- Create: `docs/main/OCR_DESIGN.md`
- Research: `services/worker/jobs/ocr_job.py`, `services/worker/scanners/ocr_scanner.py`, `services/worker/scanners/batch_ocr_poller_scanner.py`, `packages/backend-core/app/services/ocr_service.py`, `packages/backend-core/app/services/batch_ocr_service.py`, `packages/backend-core/app/db/repositories/pages_repository.py`, `services/backend/api/endpoints/books_router.py` (OCR reprocess/reset endpoints), `docs/main/WORKER_DESIGN.md` (OcrScanner, OcrJob, Batch OCR sections), `docs/main/BOOK_PROCESSING_DIAGRAM.md` (Full Pipeline OCR portion + Batch OCR subgraph)
- Test file to locate: OCR-related test files under `packages/backend-core/tests/` and `services/worker/tests/`

**Interfaces:**
- Consumes: `docs/main/DOCUMENT_DISCOVERY_DESIGN.md` (link target — book/page rows already exist when this stage begins)
- Produces: `docs/main/OCR_DESIGN.md`

- [ ] **Step 1: Read all research files listed above**

Note: the `ocr_milestone` state values, the soft-skip behavior on exhausted retries (marks succeeded with empty text rather than failed), the `MultiPageLock` usage, the Gemini Vision call and its inner retry loop (`OCR_MAX_RETRIES`), the PDF page render step (PyMuPDF, `OCR_PAGE_ZOOM_FACTOR`), TOC-page detection, and the full Batch OCR submit/poll cycle (`batch_ocr_service.submit_batch_ocr_job`, `batch_ocr_poller_scanner`).

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "ocr_job\|OcrJob\|ocr_scanner\|OcrScanner\|ocr_service\|batch_ocr" packages/backend-core/tests services/worker/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/OCR_DESIGN.md` following the Standard Template**

Include:
- Feature Flags: `gemini_batch_ocr_enabled` (default, what it gates).
- Schema: `pages.ocr_milestone`, `pages.retry_count`, `pages.worker_id`/`claimed_at`, `books.ocr_milestone`, `books.pipeline_step`.
- Data Flow: scoped mermaid diagram — `OCR_IDLE` scanner claim → job → Gemini Vision call → success/soft-skip/failure → outbox `ocr_succeeded` event → handoff to Chunking. Include the batch-mode branch as a sub-flow (reuse the shape of `BOOK_PROCESSING_DIAGRAM.md`'s "Batch OCR & Batch Embedding" diagram, OCR half only).
- Component Responsibilities: `OcrScanner` and `OcrJob` as numbered pseudocode (re-verify against current `ocr_job.py`/`ocr_scanner.py` — the exhaustion/soft-skip logic is easy to get subtly wrong, read the actual exception-handling branch), plus `batch_ocr_service.submit_batch_ocr_job` and `batch_ocr_poller_scanner`.
- State Machine: `ocr_milestone` states (`idle`/`in_progress`/`succeeded` incl. soft-skip/`failed`) and transitions — mermaid diagram, reusing the `WORKER_DESIGN.md` OCR portion of the full state machine but as its own standalone diagram.
- Error Handling & Retries: distinguish "soft-skip" (never blocks book) from genuine `ocr_milestone='failed'` (only when the PDF itself can't be downloaded — this is what can push a book to `status='error'`).
- Configuration Reference: `ocr_max_retry_count`, `ocr_max_parallel_pages`, `ocr_scanner_batch_size`, `scanner_book_limit`, `gemini_ocr_timeout`, `gemini_ocr_model`, `OCR_MAX_RETRIES`, `OCR_PAGE_ZOOM_FACTOR`, `gemini_batch_ocr_enabled`, `gemini_batch_ocr_batch_size`, `gemini_batch_ocr_timeout_hours`, `gemini_batch_ocr_max_retry_count` — confirm each still exists in `packages/backend-core/app/core/config.py` or `system_configs` seeds before citing its default.
- API Endpoints: `/reprocess/ocr`, `/pages/{page_num}/reset` (role required from actual router source).
- Testing: files from Step 2.
- Related Docs: link to `DOCUMENT_DISCOVERY_DESIGN.md` (previous stage) and `CHUNKING_DESIGN.md` (next stage).

- [ ] **Step 4: Verify every factual claim**

Same procedure as Task 1 Step 4, applied to every file path, config key, and milestone value in this doc. Pay particular attention to the soft-skip vs. hard-failure distinction — verify it against the actual `except` branch in `ocr_job.py`, don't assume the spec's summary is still accurate.

- [ ] **Step 5: Commit**

```bash
git add docs/main/OCR_DESIGN.md
git commit -m "docs: add OCR pipeline stage design doc"
```

---

### Task 3: Chunking design doc

**Files:**
- Create: `docs/main/CHUNKING_DESIGN.md`
- Research: `services/worker/jobs/chunking_job.py`, `services/worker/scanners/chunking_scanner.py`, `packages/backend-core/app/services/chunking_service.py`, `packages/backend-core/app/db/repositories/chunks_repository.py`, `packages/backend-core/app/db/repositories/pages_repository.py`, `services/backend/api/endpoints/books_router.py` (reprocess/chunking endpoint), `docs/main/WORKER_DESIGN.md` (ChunkingScanner, ChunkingJob sections)
- Test file to locate: chunking-related test files

**Interfaces:**
- Consumes: `docs/main/OCR_DESIGN.md`
- Produces: `docs/main/CHUNKING_DESIGN.md`

- [ ] **Step 1: Read all research files**

Note: cross-book claiming behavior (unlike OCR's per-book grouping), the recursive character splitter and its size/overlap config, TOC-page skip behavior, the upsert-on-conflict logic (resets `embedding` to `NULL` when text changes), and why `ready` books remain eligible for re-chunking (auto-correct can reopen it).

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "chunking_job\|ChunkingJob\|chunking_scanner\|ChunkingScanner\|chunking_service" packages/backend-core/tests services/worker/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/CHUNKING_DESIGN.md` following the Standard Template**

Include:
- Schema: `pages.chunking_milestone`, `chunks` table (id, page_id, chunk_index, text, embedding columns).
- Data Flow: scoped diagram — `CHUNK_IDLE` (dependency: `ocr_milestone=succeeded`) → scanner claim (cross-book) → `ChunkingJob` → outbox `chunking_succeeded` → handoff to Embedding.
- Component Responsibilities: `ChunkingScanner` and `ChunkingJob` numbered steps, re-verified against current source (splitter config, upsert/delete-shrinking-page logic).
- State Machine: `chunking_milestone` states.
- Configuration Reference: `scanner_page_limit`, `CHUNK_SIZE`, `CHUNK_OVERLAP` — confirm these are still the actual env var names in `packages/backend-core/app/core/config.py`.
- No API Endpoints section unless a chunking-specific reprocess endpoint exists (confirm route path in `books_router.py`) — include it if found, omit if this stage has no direct endpoint beyond the generic reprocess ones already covered by OCR (do not duplicate; if `/reprocess/chunking` exists, it belongs here since it's chunking's own endpoint).
- Testing: files from Step 2.
- Related Docs: link to `OCR_DESIGN.md` and `EMBEDDING_DESIGN.md`.

- [ ] **Step 4: Verify every factual claim** (same procedure as prior tasks)

- [ ] **Step 5: Commit**

```bash
git add docs/main/CHUNKING_DESIGN.md
git commit -m "docs: add Chunking pipeline stage design doc"
```

---

### Task 4: Embedding design doc

**Files:**
- Create: `docs/main/EMBEDDING_DESIGN.md`
- Research: `services/worker/jobs/embedding_job.py`, `services/worker/scanners/embedding_scanner.py`, `services/worker/scanners/batch_embedding_poller_scanner.py`, `packages/backend-core/app/services/batch_embedding_service.py`, `packages/backend-core/app/db/repositories/chunks_repository.py`, `services/backend/api/endpoints/books_router.py` (reprocess/embedding endpoint), `docs/main/WORKER_DESIGN.md` (EmbeddingScanner, EmbeddingJob, Batch Embedding sections), `docs/main/BOOK_PROCESSING_DIAGRAM.md` (Batch OCR & Batch Embedding diagram, embedding half)
- Test file to locate: embedding-related test files

**Interfaces:**
- Consumes: `docs/main/CHUNKING_DESIGN.md`
- Produces: `docs/main/EMBEDDING_DESIGN.md`

- [ ] **Step 1: Read all research files**

Note: the embedding model config (`gemini_embedding_model`, vector dimensionality — confirm the actual `vector(N)` column width in the current schema/migration rather than assuming 3072), batch size for embedding calls, and the full batch-embedding submit/poll cycle.

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "embedding_job\|EmbeddingJob\|embedding_scanner\|EmbeddingScanner\|batch_embedding" packages/backend-core/tests services/worker/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/EMBEDDING_DESIGN.md` following the Standard Template**

Include:
- Feature Flags: `gemini_batch_embedding_enabled`.
- Schema: `chunks.embedding` (confirm exact `vector(N)` dimension from the current migration file, not from memory/plan assumption), `pages.embedding_milestone`.
- Data Flow: scoped diagram — dependency `chunking_milestone=succeeded` → scanner claim → `EmbeddingJob` (or batch submit branch) → outbox `embedding_succeeded` → handoff to book-ready evaluation (link to `WORKER_DESIGN.md`'s `PipelineDriver`, don't re-explain it here).
- Component Responsibilities: `EmbeddingScanner`/`EmbeddingJob` numbered steps, plus `batch_embedding_service.submit_batch_embedding_job` and `batch_embedding_poller_scanner`.
- State Machine: `embedding_milestone` states.
- Configuration Reference: `gemini_embedding_model`, `EMBED_BATCH_SIZE`, `gemini_batch_embedding_enabled`, `gemini_batch_embedding_max_chunks_per_job`, `gemini_batch_embedding_timeout_hours`, `gemini_batch_embedding_max_retry_count`.
- API Endpoints: `/reprocess/embedding` if it exists as its own route.
- Testing: files from Step 2.
- Related Docs: link to `CHUNKING_DESIGN.md` and `SPELLCHECK_DESIGN.md`/`SUMMARY_DESIGN.md` (embedding is the terminal mandatory step — link forward to whichever stages key off book-ready).

- [ ] **Step 4: Verify every factual claim** (same procedure — pay particular attention to the vector dimension, since it's a common source of stale-doc drift)

- [ ] **Step 5: Commit**

```bash
git add docs/main/EMBEDDING_DESIGN.md
git commit -m "docs: add Embedding pipeline stage design doc"
```

---

### Task 5: Spellcheck + Auto-Correct design doc

**Files:**
- Create: `docs/main/SPELLCHECK_DESIGN.md`
- Research: `services/worker/jobs/spell_check_job.py`, `services/worker/jobs/auto_correct_job.py`, `services/worker/scanners/spell_check_scanner.py`, `services/worker/scanners/auto_correct_scanner.py`, `packages/backend-core/app/services/spell_check_service.py`, `packages/backend-core/app/services/auto_correct_service.py`, `packages/backend-core/app/db/repositories/dictionary_repository.py`, `packages/backend-core/app/db/repositories/auto_correct_rules_repository.py`, `services/backend/api/endpoints/spell_check_router.py`, `services/backend/api/endpoints/auto_correct_rules_router.py`, `services/backend/api/endpoints/dictionary_router.py`, `docs/main/WORKER_DESIGN.md` (SpellCheckScanner, SpellCheckJob, AutoCorrectJob, AutoCorrectScanner sections)
- Test file to locate: spell-check and auto-correct test files

**Interfaces:**
- Consumes: `docs/main/EMBEDDING_DESIGN.md` (dependency is actually `ocr_milestone=succeeded`, independent of chunking/embedding — call this out explicitly since it's a common misconception)
- Produces: `docs/main/SPELLCHECK_DESIGN.md`

- [ ] **Step 1: Read all research files**

Note: spellcheck's dependency is `ocr_milestone=succeeded` only (runs in parallel with chunking/embedding, does not block book readiness), the concurrent-books-limit logic in the scanner, the `dictionary`/`page_spell_issues`/`auto_correct_rules` tables, and how auto-correct resets `chunking_milestone`/`embedding_milestone` back to `idle` on corrected pages (this is why Chunking/Embedding scanners don't exclude `ready` books).

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "spell_check\|SpellCheck\|auto_correct\|AutoCorrect" packages/backend-core/tests services/worker/tests services/backend/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/SPELLCHECK_DESIGN.md` following the Standard Template**

Include:
- Feature Flags: `spell_check_enabled`, `auto_correct_enabled`.
- Schema: `pages.spell_check_milestone`, `dictionary`, `page_spell_issues`, `auto_correct_rules` tables.
- Data Flow: one scoped diagram covering both spell-check and auto-correct as two connected subgraphs, matching the shape of `BOOK_PROCESSING_DIAGRAM.md`'s `SpellCheck`/`AutoCorrect` subgraphs.
- Component Responsibilities: `SpellCheckScanner`/`SpellCheckJob` and `AutoCorrectScanner`/`AutoCorrectJob`, all four as numbered steps.
- State Machine: `spell_check_milestone` states (note: exhaustion here never affects `book.status`, unlike chunking/embedding).
- Configuration Reference: `max_concurrent_spell_check_books`, `scanner_page_limit`, `MAX_PARALLEL_SPELL_CHECK`, `auto_correct_batch_size`, `MAX_PARALLEL_AUTO_CORRECT`.
- API Endpoints: routes in `spell_check_router.py`, `auto_correct_rules_router.py`, `dictionary_router.py`, plus `/reprocess/spell-check`, each with role required.
- Testing: files from Step 2.
- Related Docs: link to `EMBEDDING_DESIGN.md` and `SUMMARY_DESIGN.md`.

- [ ] **Step 4: Verify every factual claim** (same procedure)

- [ ] **Step 5: Commit**

```bash
git add docs/main/SPELLCHECK_DESIGN.md
git commit -m "docs: add Spellcheck and Auto-Correct pipeline stage design doc"
```

---

### Task 6: Summary Generation design doc

**Files:**
- Create: `docs/main/SUMMARY_DESIGN.md`
- Research: `services/worker/jobs/summary_job.py`, `services/worker/scanners/summary_scanner.py`, `packages/backend-core/app/services/book_milestone_service.py` (summary-enqueue hook only), `packages/backend-core/app/db/repositories/book_summaries_repository.py`, `services/backend/api/endpoints/books_router.py` (reprocess/summary endpoint), `docs/main/WORKER_DESIGN.md` (SummaryJob, PipelineDriver step 5 — summary enqueue trigger)
- Test file to locate: summary-related test files

**Interfaces:**
- Consumes: `docs/main/SPELLCHECK_DESIGN.md` (summary is triggered by book becoming `ready`, not by spellcheck directly — clarify the actual trigger is `PipelineDriver`, covered in `WORKER_DESIGN.md`)
- Produces: `docs/main/SUMMARY_DESIGN.md`

- [ ] **Step 1: Read all research files**

Note: the auto-enqueue-once-per-book trigger condition (book transitions to `ready` AND has no existing `book_summaries` row), the character-sampling cap (`SUMMARY_MAX_CHARS` or current equivalent — verify exact name/value), the structured-summary generation + embedding, and that a summary failure never blocks book availability (RAG falls back to category-based search — verify this fallback still exists in the current RAG code before citing it, or omit if it's drifted).

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "summary_job\|SummaryJob\|summary_scanner\|SummaryScanner\|book_summaries" packages/backend-core/tests services/worker/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/SUMMARY_DESIGN.md` following the Standard Template**

Include:
- Schema: `book_summaries` table columns.
- Data Flow: scoped diagram — book reaches `ready` → `PipelineDriver` auto-enqueues `SummaryJob` (once) → embed + upsert `book_summaries`; plus `SummaryScanner` as a parallel backfill/retry path.
- Component Responsibilities: `SummaryJob` and `SummaryScanner` numbered steps.
- No State Machine section — summary generation has no dedicated milestone column of its own to track states for (confirm this is still true; if a `summary_milestone` column exists now, include the section).
- Configuration Reference: the character-sampling cap constant/config, `summary_scanner_batch_size`.
- API Endpoints: `/reprocess/summary`.
- Testing: files from Step 2.
- Related Docs: link to `SPELLCHECK_DESIGN.md` and `CHAT_RAG_DESIGN.md` (summary feeds RAG book-routing).

- [ ] **Step 4: Verify every factual claim** (same procedure — the RAG fallback claim especially needs re-confirmation against current `rag_service.py`/handler code, not assumed from the spec)

- [ ] **Step 5: Commit**

```bash
git add docs/main/SUMMARY_DESIGN.md
git commit -m "docs: add Summary Generation pipeline stage design doc"
```

---

### Task 7: Chat / RAG Retrieval design doc

**Files:**
- Create: `docs/main/CHAT_RAG_DESIGN.md`
- Research: `packages/backend-core/app/services/rag_service.py`, `packages/backend-core/app/services/rag/registry.py`, `packages/backend-core/app/services/rag/base_handler.py`, `packages/backend-core/app/services/rag/retrieval.py`, `packages/backend-core/app/services/rag/answer_builder.py`, `packages/backend-core/app/services/rag/judge.py`, `packages/backend-core/app/services/rag/query_rewriter.py`, `packages/backend-core/app/services/rag/context.py`, `packages/backend-core/app/services/rag/handlers/catalog.py`, `packages/backend-core/app/services/rag/agent/adk_agent.py`, `packages/backend-core/app/services/rag/agent/deterministic_handler.py`, `packages/backend-core/app/services/rag/agent/llm_routed_handler.py`, `packages/backend-core/app/services/rag/agent/graph_router.py`, `packages/backend-core/app/services/rag/agent/reranker.py`, `packages/backend-core/app/services/rag/agent/tools.py`, `packages/backend-core/app/services/chat/orchestrator.py`, `packages/backend-core/app/services/chat/retrieval_agent.py`, `packages/backend-core/app/services/chat/answer_agent.py`, `packages/backend-core/app/services/chat/history.py`, `packages/backend-core/app/services/chat/context.py`, `packages/backend-core/app/services/chat_limit_service.py`, `services/backend/api/endpoints/chat_router.py`, `services/backend/api/endpoints/ai_router.py`, `services/backend/api/endpoints/questions_router.py`, `services/worker/jobs/rag_eval_job.py`, `docs/main/QUESTION_ANSWERING_DIAGRAM.md`, `docs/main/LLM_ROUTED_RAG_DESIGN.md`, `docs/main/RAG_DETERMINISTIC_ROUTER_DESIGN.md`
- Test file to locate: chat/RAG-related test files (likely the largest set — list all found, don't cherry-pick)

**Interfaces:**
- Consumes: `docs/main/SUMMARY_DESIGN.md` (book summaries feed RAG's book-routing step)
- Produces: `docs/main/CHAT_RAG_DESIGN.md`, replacing `docs/main/QUESTION_ANSWERING_DIAGRAM.md`, `docs/main/LLM_ROUTED_RAG_DESIGN.md`, `docs/main/RAG_DETERMINISTIC_ROUTER_DESIGN.md` (those three are deleted in Task 9, not here — this task only authors the replacement)

- [ ] **Step 1: Read all research files**

This is the largest and most architecturally complex stage — budget more time here than the other tasks. Note: the two distinct chat pipelines (`ChatOrchestrator` vs. `RAGService`/`HandlerRegistry`), what determines which one handles a given request, the deterministic vs. LLM-routed handler split within the registry path, the ADK agent tool loop, reranking, query rewriting, the judge/grading step, and `rag_eval_job`'s role as post-turn async scoring (not part of the live request path).

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "rag_service\|RAGService\|HandlerRegistry\|ChatOrchestrator\|retrieval_agent\|answer_agent" packages/backend-core/tests services/backend/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/CHAT_RAG_DESIGN.md` following the Standard Template, with two clearly labeled sub-sections under Component Responsibilities**

Structure Component Responsibilities as two `###` sub-sections: `### ChatOrchestrator Pipeline` and `### RAGService / HandlerRegistry Pipeline` (with `#### Deterministic Handler` and `#### LLM-Routed Handler` beneath the latter). Include:
- Overview: state which pipeline handles which request type/route, and that both share retrieval/context infrastructure (name the shared files).
- Data Flow: one top-level mermaid diagram showing the routing decision (which pipeline a request goes to) branching into two sub-flows — reuse and update the diagrams already in `QUESTION_ANSWERING_DIAGRAM.md` rather than inventing new ones from scratch, re-verifying each node against current code.
- Configuration Reference: `RAG_TOP_K` and any other RAG-tuning config/env vars found in the researched files — confirm current value, do not assume a stale default.
- API Endpoints: routes in `chat_router.py`, `ai_router.py`, `questions_router.py`, with roles.
- Security Considerations: per-user rate limiting (`chat_limit_service.py`), prompt-injection surface from book content flowing into LLM context.
- Testing: files from Step 2 (likely several — list all).
- Related Docs: link to `SUMMARY_DESIGN.md` and `KNOWLEDGE_GRAPH_DESIGN.md` (graph-routed retrieval, if the LLM-routed handler queries the graph).

- [ ] **Step 4: Verify every factual claim** (same procedure — this doc has the most claims, be thorough; specifically re-verify `RAG_TOP_K`'s current value against `packages/backend-core/app/core/config.py` rather than trusting the value noted elsewhere)

- [ ] **Step 5: Commit**

```bash
git add docs/main/CHAT_RAG_DESIGN.md
git commit -m "docs: add Chat/RAG Retrieval pipeline stage design doc"
```

---

### Task 8: Knowledge Graph design doc

**Files:**
- Create: `docs/main/KNOWLEDGE_GRAPH_DESIGN.md`
- Research: `packages/backend-core/app/services/knowledge_graph_service.py`, `packages/backend-core/app/services/entity_resolution_service.py`, `packages/backend-core/app/db/repositories/graph_repository.py`, `packages/backend-core/app/db/repositories/graph_resolution_repository.py`, `services/worker/jobs/knowledge_graph_job.py`, `services/worker/jobs/graph_resolution_job.py`, `services/worker/scanners/graph_scanner.py`, `services/worker/scanners/graph_resolution_scanner.py`, `services/backend/api/endpoints/graph_admin_router.py`, `docs/main/WORKER_DESIGN.md` (KnowledgeGraphJob section), `apps/frontend/src/components/graph/GraphView.tsx` (read-only, for context on how the graph is consumed — do not modify), `docs/feature/rag-retrieval-reranking-hybrid-search/knowledge-graph-entity-resolution-design-v2.md` (background context only — this is a feature-branch doc, not the source of truth; verify everything against current code)
- Test file to locate: knowledge graph and entity resolution test files, including `packages/backend-core/tests/app/db/graph_repository_test.py` (already referenced in this session's git status as recently modified)

**Interfaces:**
- Consumes: `docs/main/CHAT_RAG_DESIGN.md` (graph-routed retrieval reads what this doc documents)
- Produces: `docs/main/KNOWLEDGE_GRAPH_DESIGN.md`

- [ ] **Step 1: Read all research files**

Note: `knowledge_graph_enabled` default and its no-op behavior, the extraction batching/concurrency config, fictional-category Person-entity namespacing, the entity resolution/dedup second pass, the `graph_milestone` states, and — separately — the `graph_resolution_queue`/`graph_resolution_job`/`graph_resolution_scanner` flow (this looks like a distinct sub-system from bulk extraction; read `entity_resolution_service.py` carefully to determine whether it's a separate incremental-resolution pipeline or part of the same extraction job, and document whichever is actually true in the current code — this repo has graph-related files under active modification per the session's git status, so do not assume the spec's summary is current).

- [ ] **Step 2: Locate the test file(s)**

```bash
grep -rl "knowledge_graph\|KnowledgeGraph\|graph_repository\|entity_resolution\|graph_resolution" packages/backend-core/tests services/worker/tests services/backend/tests 2>/dev/null
```

- [ ] **Step 3: Draft `docs/main/KNOWLEDGE_GRAPH_DESIGN.md` following the Standard Template**

Include:
- Feature Flags: `knowledge_graph_enabled`.
- Schema: Neo4j `Entity` node shape and `RELATED_TO` edge shape (properties, not a relational table — describe as a labeled property graph schema instead of the usual SQL table format), plus any Postgres-side tracking tables (`graph_resolution_queue` if it exists).
- Data Flow: scoped diagram covering both bulk extraction (`KnowledgeGraphJob`) and the entity-resolution queue flow, as two connected subgraphs if they are indeed separate as determined in Step 1.
- Component Responsibilities: `KnowledgeGraphJob`, `GraphScanner`, and the entity-resolution job/scanner pair, all as numbered steps.
- State Machine: `graph_milestone` states (`idle`/`in_progress`/`complete`/`partial`/`failed`).
- Configuration Reference: `gemini_kg_extraction_model`, `kg_max_parallel_chunks`, `kg_chunk_batch_size`, `graph_scanner_batch_size`, plus any entity-resolution-specific config discovered in Step 1.
- API Endpoints: routes in `graph_admin_router.py`, `/reprocess/graph`, `books_router.py`'s `/graph/merge` endpoint (referenced in this session's git status as a modified file — verify current signature), with roles.
- Security Considerations: prompt-injection surface (entity/relation extraction runs LLM calls over OCR'd book text), admin-only graph mutation endpoints.
- Testing: files from Step 2, explicitly confirming whether `graph_repository_test.py`'s current content still matches what the doc describes (this file was modified in the session that produced this plan).
- Related Docs: link to `CHAT_RAG_DESIGN.md` and `SUMMARY_DESIGN.md`.

- [ ] **Step 4: Verify every factual claim** (same procedure — this stage has the most recent code churn of any stage per the session's git status, so treat every claim as needing fresh verification, not just a spot-check)

- [ ] **Step 5: Commit**

```bash
git add docs/main/KNOWLEDGE_GRAPH_DESIGN.md
git commit -m "docs: add Knowledge Graph pipeline stage design doc"
```

---

### Task 9: Cleanup — trim multi-stage docs, delete superseded docs, update indexes

**Files:**
- Modify: `docs/main/WORKER_DESIGN.md`
- Modify: `docs/main/BOOK_PROCESSING_DIAGRAM.md`
- Delete: `docs/main/QUESTION_ANSWERING_DIAGRAM.md`
- Delete: `docs/main/LLM_ROUTED_RAG_DESIGN.md`
- Delete: `docs/main/RAG_DETERMINISTIC_ROUTER_DESIGN.md`
- Modify: `docs/main/README.md` (doc index table)
- Modify: root `README.md` (pipeline/architecture section)

**Interfaces:**
- Consumes: all 8 docs produced by Tasks 1-8 (needs their exact filenames and heading anchors to link to)
- Produces: nothing further downstream — this is the last task

- [ ] **Step 1: Trim `docs/main/WORKER_DESIGN.md`**

Read the current file. Remove the per-step algorithm subsections that now live in the stage docs: `OcrScanner / ChunkingScanner / EmbeddingScanner / SpellCheckScanner` component-responsibility details, the `Jobs` subsection (`OcrJob`, `ChunkingJob`, `EmbeddingJob`, `SpellCheckJob`, `AutoCorrectJob`, `SummaryJob`, `KnowledgeGraphJob` bodies), `Batch OCR & Batch Embedding` detail, `AutoCorrectScanner` detail. Replace each removed subsection with a single line: `See [<STAGE>_DESIGN.md](<STAGE>_DESIGN.md) for the full <stage> algorithm.` Keep: Overview, Goals, Feature Flags (as a full cross-stage index — do not remove flags just because they're also documented per-stage), Schema (the milestone-column tables — these are inherently cross-stage), the top-level Architecture file tree (as a directory map, not per-file algorithm detail), `PipelineDriver`, `StaleWatchdog`, `EventDispatcher`, `MaintenanceScanner` (these have no single stage owner), the State Machine mermaid diagram (it's the cross-stage view — the per-stage docs have their own scoped versions), Retry Logic, Cron Schedule.

- [ ] **Step 2: Trim `docs/main/BOOK_PROCESSING_DIAGRAM.md`**

Same principle: keep the "Full Pipeline" top-level mermaid diagram (cross-stage view) and the Admin Recovery Actions / Page Milestone Transitions / Key Infrastructure sections (cross-stage). Remove the per-stage sub-diagrams that are now duplicated in each stage doc's own Data Flow section, replacing with a link, e.g. `See [OCR_DESIGN.md](OCR_DESIGN.md#data-flow) for the OCR-specific diagram.`

- [ ] **Step 3: Delete the three superseded chat docs**

```bash
git rm docs/main/QUESTION_ANSWERING_DIAGRAM.md docs/main/LLM_ROUTED_RAG_DESIGN.md docs/main/RAG_DETERMINISTIC_ROUTER_DESIGN.md
```

Before running this, grep the rest of the repo for any remaining references to these three filenames and update them to point at `CHAT_RAG_DESIGN.md` instead:

```bash
grep -rln "QUESTION_ANSWERING_DIAGRAM\|LLM_ROUTED_RAG_DESIGN\|RAG_DETERMINISTIC_ROUTER_DESIGN" --include="*.md" .
```

- [ ] **Step 4: Update `docs/main/README.md`'s doc index**

Read the current index table. Remove rows for the three deleted docs. Add rows for all 8 new docs, in pipeline order, each with a one-line description matching the pattern of existing rows.

- [ ] **Step 5: Update root `README.md`**

Read the current pipeline/architecture section (the mermaid `flowchart TD` and narrative walkthrough noted during the original research). Add links to the relevant new stage docs alongside or in place of whatever it currently references — do not remove the existing top-level diagram itself, only update the doc links.

- [ ] **Step 6: Verify no dangling links**

```bash
grep -rln "QUESTION_ANSWERING_DIAGRAM\|LLM_ROUTED_RAG_DESIGN\|RAG_DETERMINISTIC_ROUTER_DESIGN" --include="*.md" .
```

Expect: no output. If any file still references a deleted doc, fix it.

- [ ] **Step 7: Commit**

```bash
git add docs/main/WORKER_DESIGN.md docs/main/BOOK_PROCESSING_DIAGRAM.md docs/main/README.md README.md
git add -u docs/main/
git commit -m "docs: trim multi-stage docs and delete superseded chat docs after per-stage doc split"
```
