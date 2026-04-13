# Book Processing Pipeline Diagram

Visual representation of the book processing pipeline, including triggers, stage transitions, admin recovery actions, and outputs. All processing is synchronous/realtime — no Gemini Batch API is used.

---

## Full Pipeline
```mermaid
flowchart TD
    %% Triggers
    subgraph Triggers [Event Triggers]
        T1[User Uploads PDF] -->|Creates Book| InitDB
        T2[GCS Discovery] -->|Discovers Book| InitDB
    end

    InitDB([Book: pending\nMilestones: idle])

    %% Mandatory sequential pipeline
    subgraph Pipeline [Mandatory Pipeline — OCR → Chunking → Embedding]
        S_OCR[OCR Scanner] -->|Claim idle| J_OCR[OCR Job]
        S_CH[Chunking Scanner] -->|Claim idle\ndep: ocr=succeeded| J_CH[Chunking Job]
        S_EM[Embedding Scanner] -->|Claim idle\ndep: chunking=succeeded| J_EM[Embedding Job]
    end

    InitDB --> S_OCR

    %% Event Bus / Outbox — reactive low-latency triggers
    subgraph Outbox [Transactional Outbox]
        J_OCR -->|Write Event\nocr_succeeded| OB[(Pipeline Events)]
        J_CH -->|Write Event\nchunking_succeeded| OB
        J_EM -->|Write Event\nembedding_succeeded| OB

        OB -->|Poll| ED[Event Dispatcher]

        ED -->|Immediate: dispatch chunking_job| J_CH
        ED -->|Immediate: dispatch embedding_job| J_EM
    end

    %% Book readiness — driven by PipelineDriver, not spell check
    J_EM -->|embedding terminal| PD[Pipeline Driver\nevery 1 min]
    PD -->|all pages terminal| Ready([Book: ready])

    %% Independent quality layer — runs in parallel, does NOT block readiness
    subgraph SpellCheck [Independent Quality Layer]
        S_SC[Spell Check Scanner\ndep: ocr=succeeded only] -->|Claim idle| J_SC[Spell Check Job]
    end
    InitDB -.->|ocr done| S_SC

    %% Monitoring
    Watchdog[Stale Watchdog] -.->|Reset in_progress > 30m| Pipeline
    Watchdog -.->|Reset in_progress > 30m| SpellCheck

    classDef stage fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef job fill:#d4f1f4,stroke:#189ab4,stroke-width:1px
    classDef event fill:#ffe8d6,stroke:#b5838d,stroke-dasharray: 5 5
    classDef driver fill:#fef9c3,stroke:#854d0e,stroke-width:1px

    class InitDB,Ready stage
    class J_OCR,J_CH,J_EM,J_SC job
    class OB,ED event
    class PD driver
```

---

## Admin Recovery Actions

Actions available from the admin management table when a book is stuck or failed. These actions work by resetting page-level milestones to `idle`, allowing scanners to pick them up.

```mermaid
flowchart TD
    idle([milestone: idle])
    in_proc([milestone: in_progress])
    succ([milestone: succeeded])
    fail([milestone: failed])

    %% Normal flow (Scanners)
    idle -->|Scanner claims| in_proc
    in_proc -->|Job success| succ
    in_proc -->|Job failure| fail
    fail -->|Retry count < max| idle

    %% Admin: Reprocess / Retry
    fail -->|"Reset Failed Pages\n(set milestone → idle)"| idle
    succ -->|"Reprocess Step (OCR/Chunk/Embed/...)\n(set milestone → idle at that step)"| idle
    in_proc -->|"Stale Watchdog\n(timeout: set milestone → idle)"| idle

    %% Admin: Reindex
    succ -->|"Reindex\n(set pipeline_step → chunking\nset milestone → idle)"| idle

    %% Manual Edit (Sync)
    any_state -->|"Update Page Text\n(Sync chunk/embed\nset milestone → succeeded)"| succ

    classDef state fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef errState fill:#ffcccb,stroke:#d32f2f,stroke-width:2px
    classDef succState fill:#d4f1f4,stroke:#189ab4,stroke-width:2px

    class idle,in_proc state
    class fail errState
    class succ succState
```

---

## Page Milestone Transitions

When a page repeatedly fails OCR, it is automatically marked as `failed` after `ocr_max_retry_count` attempts. Admin can then use "Reset Failed Pages" to try again if needed.

```mermaid
flowchart TD
    A[Milestone: idle] --> B[Job Picked Up]
    B --> C[Milestone: in_progress]
    C -->|Success| D[Milestone: succeeded\npipeline_step++]
    C -->|Failure| E[retry_count++]
    E --> F{retry_count\n>= max_retry?}
    F -->|No| G[Milestone: idle]
    G --> B
    F -->|Yes| H[Milestone: failed]
    H -->|Admin Reset| A
```

---

### Book Statuses

| Status | Meaning |
|---|---|
| `pending` | Waiting for processing to begin |
| `ready` | Fully processed; all pages reached final milestone |
| `error` | Terminal failure at book level (rare; usually page-level) |

### Page Milestones

| Milestone | Meaning |
|---|---|
| `idle` | Awaiting processing by the relevant scanner |
| `in_progress` | Currently being processed by a worker job |
| `succeeded` | Successfully completed current pipeline step |
| `failed` | Max retries reached; manual intervention required |

### Page Pipeline Steps

| Step | Goal | Terminal Success |
|---|---|---|
| `ocr` | Extraction of text from image/PDF | `succeeded` |
| `chunking` | Recursive character splitting of text into overlapping chunks | `succeeded` |
| `embedding` | Generation of vector embeddings | `succeeded` |
| `spell_check` | Identifying unknown words | `done` |

---

### Reprocess Step
| Field | Value |
|---|---|
| Trigger | Admin context menu step reprocess (OCR, Chunking, Embedding, or Spell Check) |
| Effect | Target step milestone → `idle`. Downstream steps reset. |
| Logic | Preserves existing data until newer results are applied page-by-page. |

### Reindex
| Field | Value |
|---|---|
| Trigger | Admin "Reindex" button (legacy) or Step Reprocess: chunking |
| Effect | Target pages → `chunking_milestone: idle`. New chunks/embeddings will be generated. |

### Reset Failed Pages
| Field | Value |
|---|---|
| Trigger | Admin "Reset Failed" button |
| Effect | Pages with `milestone: failed` → `milestone: idle`, `retry_count: 0` |

### Manual Page Update
| Field | Value |
|---|---|
| Trigger | Editor saves text changes |
| Effect | Synchronous re-chunk (always). Synchronous re-embed attempted — if it succeeds, `embedding_milestone: succeeded`; if it fails, `embedding_milestone: idle` and the worker picks it up. If text changed, stale spell issues are deleted and `spell_check_milestone` is reset to `idle`. |

---

## Key Infrastructure

| Component | Role |
|---|---|
| **ARQ Worker** | Runs the scanners and specific jobs (via Redis queue) |
| **Pipeline Driver** | Initializes pages, resets retryable failures, marks books `ready` when embedding is terminal |
| **Scanners** | Poll for `idle` pages, enforce their own upstream dependency, dispatch jobs |
| **Event Dispatcher** | Polls the outbox and immediately dispatches the next job (bypasses the 1-min cron delay) |
| **Stale Watchdog** | Recovers `in_progress` pages that timed out |
