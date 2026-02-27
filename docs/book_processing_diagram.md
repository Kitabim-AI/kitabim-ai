# Book Processing Pipeline Diagram

Visual representation of the book processing pipeline, including triggers, stage transitions, admin recovery actions, and outputs. The pipeline uses the **Gemini Batch API** for high-throughput, cost-effective processing.

---

## Full Pipeline

```mermaid
flowchart TD
    %% Triggers
    subgraph Triggers [Event Triggers]
        T1[User Uploads PDF\nPOST /api/books/upload] -->|Creates Book Record| InitDB
        T2[GCS Discovery Sync\nScheduled/Manual] -->|Discovers New Books| InitDB
    end

    %% Init
    InitDB([Book: pending\nPages: pending])

    %% Phase 1: OCR Batch Submission
    subgraph OCR_Submission [Phase 1 — OCR Batch Submission]
        S1[Check pending Pages] --> S2{Pages Found?}
        S2 -->|Yes| S3[Download PDF from GCS]
        S3 --> S4[Upload PDF to Gemini File API]
        S4 --> S5[Generate JSONL with Page References]
        S5 --> S6[Submit Gemini Batch Job]
        S6 --> S7[Pages: ocr_processing\nBook: ocr_processing]
        S7 --> S8[Store Batch Metadata]
    end
    InitDB --> S1

    %% Phase 2: Polling & Results
    subgraph Polling_Cycle [Phase 2 — Polling & Result Application]
        P1[Poll Active Batch Jobs] --> P2{Job SUCCEEDED?}
        P2 -->|Yes| P3[Download JSONL Output]
        P3 --> P4[Map Results to DB]
        P4 -->|OCR type| P5[Pages: ocr_done\ntext stored]
        P4 -->|Embed type| P6[Chunks: embedding stored]
        P2 -->|Failed| PE[Page: error\nretry_count++]
        PE --> PR{retry_count\n>= max?}
        PR -->|Yes| PS[Page: ocr_done\nempty text — skipped]
        PR -->|No| P5skip[Stays error\nretried next cycle]
    end
    S8 -.->|async poll| P1

    %% Phase 3: Local Chunking
    subgraph Local_Processing [Phase 3 — Local Chunking]
        C1[Find ocr_done Pages] --> C2{Has text?}
        C2 -->|Yes| C3[Strip Markdown & Clean Text]
        C3 --> C4[Semantic Chunking]
        C4 --> C5[Save Chunks to DB]
        C5 --> C6[Pages: chunked]
        C2 -->|No — empty text| CE{retry_count\n>= max?}
        CE -->|Yes| CS[Page: indexed\nis_indexed=true\nno chunk created]
        CE -->|No| CErr[Page: error\nretry_count++]
    end
    P5 --> C1
    PS --> C1

    %% Phase 4: Embedding Submission
    subgraph Embed_Submission [Phase 4 — Embedding Batch Submission]
        E1[Collect Chunks with NULL Embedding] --> E2[Generate JSONL for Embedding]
        E2 --> E3[Submit Gemini Embedding Job]
        E3 --> E4[Track Batch Metadata]
    end
    C6 --> E1
    E4 -.->|async poll| P1

    %% Phase 5: Finalization
    subgraph Finalization [Phase 5 — Finalization]
        F1[Find chunked Pages] --> F2{All Chunks Embedded?}
        F2 -->|Yes| F3[Pages: indexed]
        F3 --> F4[Aggregate Book Progress]
        F4 --> F5{All Pages Indexed?}
        F5 -->|Yes| Ready([Book: ready])
    end
    P6 --> F1

    classDef output fill:#d4f1f4,stroke:#189ab4,stroke-width:2px,color:#05445E
    classDef trigger fill:#ffe8d6,stroke:#b5838d,stroke-width:2px,color:#6d6875
    classDef state fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef cloud fill:#f1f1f1,stroke:#333,stroke-dasharray:5 5
    classDef skip fill:#fff3cd,stroke:#856404,stroke-width:2px

    class Ready state
    class T1,T2 trigger
    class InitDB state
    class OCR_Submission,Embed_Submission,Polling_Cycle cloud
    class PS,CS skip
```

---

## Admin Recovery Actions

Actions available from the admin management table when a book is stuck or failed.

```mermaid
flowchart LR
    pending([pending])
    ocr_proc([ocr_processing])
    ocr_done([ocr_done])
    indexing([indexing])
    ready([ready])
    error([error])

    %% Normal flow
    pending -->|Start OCR| ocr_proc
    ocr_proc -->|worker: all pages done| ocr_done
    ocr_done -->|worker: indexing starts| indexing
    indexing -->|worker: all indexed| ready
    ocr_proc -->|worker: failure| error
    indexing -->|worker: failure| error

    %% Admin: Retry OCR
    error -->|"Retry OCR\n(resets error+stuck pages → pending)"| ocr_proc
    ocr_proc -->|"Retry OCR\n(stale lock: resets stuck pages → pending)"| ocr_proc

    %% Admin: Force Complete
    ocr_proc -->|"Force Complete\n(ocr_processing pages → ocr_done)"| ocr_done
    indexing -->|"Force Complete\n(no remaining ocr_done pages)"| ready
    indexing -->|"Force Complete\n(ocr_done pages still pending)"| ocr_done
    error -->|"Force Complete\n(detects stage; ocr_done pages present)"| ocr_done
    error -->|"Force Complete\n(all pages indexed or indexing stage)"| ready

    %% Admin: Reindex
    ready -->|"Reindex\n(deletes chunks, resets is_indexed)"| ocr_proc
    ocr_done -->|"Reindex\n(deletes chunks, resets is_indexed)"| ocr_proc

    classDef normal fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef errState fill:#ffcccb,stroke:#d32f2f,stroke-width:2px
    classDef readyState fill:#d4f1f4,stroke:#189ab4,stroke-width:2px

    class pending,ocr_proc,ocr_done,indexing normal
    class error errState
    class ready readyState
```

---

## Page Auto-Skip on Max Retry

When a page repeatedly fails OCR, it is automatically skipped after `ocr_max_retry_count` attempts (configurable in System Configs, default `3`). This prevents a single bad page from blocking the entire book.

```mermaid
flowchart TD
    A[Page: pending] --> B[OCR attempted]
    B -->|success| C[Page: ocr_done\ntext stored]
    B -->|failure| D[retry_count++]
    D --> E{retry_count\n>= max_retry?}
    E -->|No| F[Page: error\nretried next cycle]
    F --> B
    E -->|Yes| G[Page: ocr_done\nempty text]
    G --> H[batch_service checks text]
    H -->|empty + at max| I[Page: indexed\nskipped — no chunk]
    C --> J[normal chunking pipeline]
```

---

## Status Reference

### Book Statuses

| Status | Meaning | processing_step |
|---|---|---|
| `uploading` | File upload in progress | — |
| `pending` | Awaiting Start OCR trigger | — |
| `ocr_processing` | Worker running OCR or re-embedding | `ocr` or `rag` |
| `ocr_done` | All pages OCR'd; not yet indexed | `ocr` |
| `indexing` | Embedding/indexing in progress | `rag` |
| `ready` | Fully processed and searchable | — |
| `error` | Pipeline failed at some stage | — |

### Page Statuses

| Status | Meaning |
|---|---|
| `pending` | Waiting to be OCR'd |
| `ocr_processing` | OCR running for this page |
| `ocr_done` | Text extracted; not yet chunked |
| `chunked` | Text split into chunks; awaiting embeddings |
| `indexing` | Embeddings being generated |
| `indexed` | Fully embedded and searchable |
| `error` | OCR or embedding failed; will be retried up to `ocr_max_retry_count` times |

### Page Fields

| Field | Type | Description |
|---|---|---|
| `retry_count` | `integer` | Number of failed OCR attempts for this page. Auto-incremented on each failure. Page is skipped when this reaches `ocr_max_retry_count`. |

---

## Action Metrics

### Start OCR

| Field | Value |
|---|---|
| Trigger condition | `status === 'pending'` |
| Book status → | `ocr_processing` |
| processing_step → | `ocr` |
| Pages effect | Existing pages deleted; worker creates fresh `pending` pages |
| Worker job | `start_ocr` |

### Retry OCR

| Field | Value |
|---|---|
| Trigger condition | `(hasFailedPages OR status === 'error' OR isStale) AND NOT isActuallyProcessing` |
| Book status → | `ocr_processing` |
| processing_step → | `ocr` |
| Pages effect | Pages with `status IN ('error', 'ocr_processing')` → `pending` (text cleared, is_indexed=false) |
| Special case | `status === 'error'` + no stuck/failed pages → re-enqueues without page changes (`resumed`) |
| Worker job | `retry_failed` or `resume_error` |

> Pages that have reached `ocr_max_retry_count` are no longer in `error` status (they were
> auto-promoted to `ocr_done`), so they are not reset by Retry OCR and do not block the book.

### Reindex

| Field | Value |
|---|---|
| Trigger condition | `status === 'ready' OR status === 'ocr_done'` |
| Book status → | `ocr_processing` |
| processing_step → | `rag` |
| Pages effect | `ocr_done`, `chunked`, `indexed` pages → `ocr_done`, `is_indexed=false` |
| Chunks effect | All chunks deleted |
| Worker job | `reindex` — re-chunks and re-embeds all `ocr_done` pages |

### Force Complete

| Field | Value |
|---|---|
| Trigger condition | Editor/admin AND `(isStale OR status IN ('ocr_processing', 'indexing', 'error'))` |
| Lock cleared | Always (`processing_lock = null`, `processing_lock_expires_at = null`) |

#### Outcome by State

| Current status | Page condition | Pages → | Book status → |
|---|---|---|---|
| `ocr_processing` | — | `ocr_processing` → `ocr_done` | `ocr_done` |
| `indexing` | no remaining `ocr_done` pages | `indexing` → `indexed` (is_indexed=true) | `ready` |
| `indexing` | `ocr_done` pages still unindexed | `indexing` → `indexed` (is_indexed=true) | `ocr_done` |
| `error` | has `ocr_processing` pages | `ocr_processing` → `ocr_done` | `ocr_done` |
| `error` | has `indexing` pages, no `ocr_done` | `indexing` → `indexed` (is_indexed=true) | `ready` |
| `error` | has `indexing` pages + `ocr_done` pages | `indexing` → `indexed` (is_indexed=true) | `ocr_done` |
| `error` | has `ocr_done` pages only | none | `ocr_done` |
| `error` | has `indexed` pages only | none | `ready` |
| `error` | no surviving page states | none | `ocr_done` |

> When force-complete resolves to `ocr_done`, the indexing pipeline automatically picks up
> remaining `ocr_done` pages on the next worker cycle — no further admin action needed.

---

## Key Infrastructure

| Component | Role |
|---|---|
| **ARQ Worker** | Periodically triggers submission and polling cycles |
| **Gemini Batch API** | OCR + embeddings at 50% cost discount, outside rate limits |
| **Gemini File API** | Transient PDF/JSONL storage (deleted after job completion) |
| **Google Cloud Storage** | Persistent source for PDFs and covers |
| **PostgreSQL + pgvector** | Stores metadata, page text, chunks, and embeddings |
| **Processing Lock** | `processing_lock` + `processing_lock_expires_at` prevent duplicate jobs; used for stale detection |
| **System Configs** | Admin-configurable runtime settings (e.g. `ocr_max_retry_count`) stored in `system_configs` table |
