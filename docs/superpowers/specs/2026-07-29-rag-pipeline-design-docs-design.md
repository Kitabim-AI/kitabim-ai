# RAG Pipeline Design Docs — One Doc Per Stage

**Date:** 2026-07-29
**Status:** Approved

## Problem

The RAG/book-processing pipeline (discovery → OCR → chunking → embedding → spellcheck → summary → chat → knowledge graph) has its design spread thin and unevenly across a handful of docs:

- `docs/main/WORKER_DESIGN.md` and `docs/main/BOOK_PROCESSING_DIAGRAM.md` cover discovery, OCR, chunking, embedding, spellcheck, auto-correct, and summary all in one place, at a per-scanner/per-job level of detail, interleaved with pipeline-wide orchestration concerns (outbox, event dispatcher, stale watchdog, retry semantics, cron schedule).
- `docs/main/QUESTION_ANSWERING_DIAGRAM.md`, `docs/main/LLM_ROUTED_RAG_DESIGN.md`, and `docs/main/RAG_DETERMINISTIC_ROUTER_DESIGN.md` split the chat/RAG retrieval stage across three docs.
- Knowledge graph extraction and entity resolution have no `docs/main/` doc at all — the only write-up (`docs/feature/rag-retrieval-reranking-hybrid-search/knowledge-graph-entity-resolution-design-v2.md`) is a feature-branch artifact, not a maintained reference.

There's no consistent per-stage reference doc, no standard template, and no single place to look for "how does stage X work today."

## Existing state (reference material for authoring)

House diagram/doc style, confirmed from `docs/main/WORKER_DESIGN.md` and `docs/main/BOOK_PROCESSING_DIAGRAM.md`:
- Mermaid `flowchart TD` diagrams (with `classDef` color coding for state types), not ASCII art.
- Dense, file-anchored prose — every claim cites the actual file/function/column/config key.
- Numbered pseudocode blocks for scanner/job algorithms (e.g. `OcrJob(book_id, page_ids): 1. ... 2. ...`).
- Tables for schema columns, feature flags, config defaults, cron schedule, and (in `BOOK_PROCESSING_DIAGRAM.md`'s Admin Recovery Actions section) API endpoints with a role-required column.
- Docs describe **only current, shipped behavior** — no roadmap/TODO language, no aspirational design.

Current pipeline stage → key files (already mapped during exploration, will be re-verified per doc at authoring time since code may drift):

| Stage | Services | Repos | Worker | Router |
|---|---|---|---|---|
| Discovery | `storage_service.py`, `pdf_service.py` | `books_repository.py` | `scanners/gcs_discovery_scanner.py` | `books_router.py` |
| OCR | `ocr_service.py`, `batch_ocr_service.py` | `pages_repository.py`, `books_repository.py` | `jobs/ocr_job.py`, `scanners/ocr_scanner.py`, `scanners/batch_ocr_poller_scanner.py` | `books_router.py` |
| Chunking | `chunking_service.py` | `chunks_repository.py`, `pages_repository.py` | `jobs/chunking_job.py`, `scanners/chunking_scanner.py` | — |
| Embedding | `batch_embedding_service.py` | `chunks_repository.py` | `jobs/embedding_job.py`, `scanners/embedding_scanner.py`, `scanners/batch_embedding_poller_scanner.py` | — |
| Spellcheck + auto-correct | `spell_check_service.py`, `auto_correct_service.py` | `dictionary_repository.py`, `auto_correct_rules_repository.py`, `pages_repository.py` | `jobs/spell_check_job.py`, `jobs/auto_correct_job.py`, `scanners/spell_check_scanner.py`, `scanners/auto_correct_scanner.py` | `spell_check_router.py`, `auto_correct_rules_router.py`, `dictionary_router.py` |
| Summary | `book_milestone_service.py` (hooks) | `book_summaries_repository.py` | `jobs/summary_job.py`, `scanners/summary_scanner.py` | `books_router.py` |
| Chat / RAG | `rag_service.py`, `rag/*`, `chat/*` | `conversation_repository.py`, `chunks_repository.py`, `book_summaries_repository.py`, `rag_evaluations_repository.py` | `jobs/rag_eval_job.py` | `chat_router.py`, `ai_router.py`, `questions_router.py` |
| Knowledge graph | `knowledge_graph_service.py`, `entity_resolution_service.py` | `graph_repository.py`, `graph_resolution_repository.py` | `jobs/knowledge_graph_job.py`, `jobs/graph_resolution_job.py`, `scanners/graph_scanner.py`, `scanners/graph_resolution_scanner.py` | `graph_admin_router.py` |

This table is a starting point for authoring — each doc's author re-verifies file paths/behavior against current code rather than trusting this snapshot.

## Design

### Scope: 8 new docs, all in `docs/main/`, `SCREAMING_SNAKE_CASE.md` naming

1. `DOCUMENT_DISCOVERY_DESIGN.md`
2. `OCR_DESIGN.md`
3. `CHUNKING_DESIGN.md`
4. `EMBEDDING_DESIGN.md`
5. `SPELLCHECK_DESIGN.md` (includes auto-correct — tightly coupled: shared repo, shared feature-flag pattern, auto-correct only acts on spell-check output)
6. `SUMMARY_DESIGN.md`
7. `CHAT_RAG_DESIGN.md` (single doc covering both chat pipelines — `ChatOrchestrator` and the `RAGService`/`HandlerRegistry` with its deterministic and LLM-routed handlers — as sub-sections, since they share retrieval/context infrastructure)
8. `KNOWLEDGE_GRAPH_DESIGN.md` (extraction + entity resolution)

Each doc reflects **only the current state of the code** — no historical narrative, no planned/future work (that belongs in backlog docs like the existing `knowledge-graph-improvement-backlog.md`, which is unaffected by this work).

### Disposition of existing docs

- **`WORKER_DESIGN.md`** and **`BOOK_PROCESSING_DIAGRAM.md`** are trimmed, not deleted. They keep only what's genuinely cross-cutting and shared by every stage: the Transactional Outbox pattern, `EventDispatcher`, `MultiPageLock`, `StaleWatchdog`, the shared `retry_count` semantics, and the cron schedule table. Every per-step algorithm section (OcrJob, ChunkingJob, EmbeddingJob, SpellCheckJob, AutoCorrectJob, SummaryJob, KnowledgeGraphJob and their scanners) is removed from these two docs and replaced with a one-line link to the new stage doc.
- **`QUESTION_ANSWERING_DIAGRAM.md`, `LLM_ROUTED_RAG_DESIGN.md`, `RAG_DETERMINISTIC_ROUTER_DESIGN.md`** are fully replaced by `CHAT_RAG_DESIGN.md` and deleted.
- **`SYSTEM_DESIGN.md`** and **`PROJECT_STRUCTURE.md`** are untouched — different altitude (whole-system/repo layout, not pipeline-stage detail).
- Root **`README.md`**'s existing pipeline/architecture section is updated to link to the new stage docs instead of (or in addition to) the docs it currently references.
- `docs/main/README.md`'s doc index table is updated to list the 8 new docs and remove the 3 deleted ones.

### Standardized template (14 sections)

Sections marked *(optional)* are included only when they'd add real information for that stage — an empty/boilerplate section is worse than an omitted one.

1. **Title + cross-links** — `# <Stage> — Design`; one line linking sibling stage docs plus `WORKER_DESIGN.md`.
2. **Overview** — 1–2 paragraphs: what the stage does, where it sits in the pipeline, key characteristics as bullets.
3. **Feature Flags** *(optional)* — table: flag name, default, what it gates.
4. **Schema** — DB columns/tables this stage reads or writes, one table per table.
5. **Architecture** — file list (service/repo/job/scanner/router) with a one-line purpose per file, in the `worker/scanners/... jobs/...` tree style used today.
6. **Data Flow** — one mermaid `flowchart TD` scoped to this stage only: trigger → scanner claim → job → outbox event → handoff to the next stage. Same color-coding convention (`classDef`) as the existing diagrams.
7. **Component Responsibilities** — per scanner/job/service, numbered pseudocode steps, matching the existing `OcrJob(book_id, page_ids): 1. ... 2. ...` style.
8. **State Machine** *(optional — only if the stage has its own milestone states)* — mermaid diagram.
9. **Error Handling & Retries** — table: scenario → behavior.
10. **Configuration Reference** — table of `system_configs`/env vars used by this stage, with defaults and which component reads them; cost/performance tradeoffs (e.g. Gemini Batch API, model choice) noted inline as a row note rather than a separate section.
11. **API Endpoints** *(optional — only if the stage has public/admin endpoints)* — table: endpoint, **role required**, effect. Role is sourced from the actual auth dependency (e.g. `require_role("editor")`) on the endpoint, not inferred.
12. **Security Considerations** *(optional — only if there's something beyond the Section 11 role table)* — e.g. file upload validation and GCS signed URLs (Discovery), LLM prompt-injection surface from user-controlled or OCR'd text (Knowledge Graph, Chat), per-user rate limiting (Chat via `chat_limit_service.py`).
13. **Testing** — pointer to the actual test file(s) covering this stage's services/repos/jobs/scanners (e.g. `packages/backend-core/tests/app/services/knowledge_graph_service_test.py`), so the doc stays anchored to verifiable current coverage rather than becoming stale prose.
14. **Related Docs** — links to sibling stage docs, `WORKER_DESIGN.md`, `SYSTEM_DESIGN.md` as relevant.

### Authoring order

Discovery → OCR → Chunking → Embedding → Spellcheck → Summary → Chat/RAG → Knowledge Graph (pipeline order; Chat and Knowledge Graph last since they're the largest/most complex and most likely to surface template adjustments needed for the simpler docs). The `WORKER_DESIGN.md`/`BOOK_PROCESSING_DIAGRAM.md` trims, the deletion of the three superseded chat docs, and the `README.md`/doc-index updates happen as a final cleanup pass after all 8 stage docs exist.

### Out of scope

- No changes to `SYSTEM_DESIGN.md`, `PROJECT_STRUCTURE.md`, or any backlog/tracking doc under `docs/feature/`.
- No code changes — this is a documentation-only effort.
- No new top-level pipeline-overview doc; the pipeline map lives in the updated root `README.md` instead.
