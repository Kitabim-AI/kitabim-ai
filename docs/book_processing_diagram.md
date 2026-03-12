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

    %% State Machine / Scanners
    subgraph Pipeline [Decoupled Pipeline Scanners]
        S_OCR[OCR Scanner] -->|Claim idle| J_OCR[OCR Job]
        S_CH[Chunking Scanner] -->|Claim idle| J_CH[Chunking Job]
        S_EM[Embedding Scanner] -->|Claim idle| J_EM[Embedding Job]
    end

    InitDB --> S_OCR

    %% Event Bus / Outbox
    subgraph Outbox [Transactional Outbox]
        J_OCR -->|Write Event| OB[(Pipeline Events)]
        J_CH -->|Write Event| OB
        
        OB -->|Poll| ED[Event Dispatcher]
        
        ED -->|Immediate Trigger| S_CH
        ED -->|Immediate Trigger| S_EM
    end

    %% Terminal states
    J_EM -->|Success| Ready([Book: ready])
    
    %% Monitoring
    Watchdog[Stale Watchdog] -.->|Reset in_progress > 30m| Pipeline

    classDef stage fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef job fill:#d4f1f4,stroke:#189ab4,stroke-width:1px
    classDef event fill:#ffe8d6,stroke:#b5838d,stroke-dasharray: 5 5

    class InitDB,Ready stage
    class J_OCR,J_CH,J_EM job
    class OB,ED event
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

    %% Admin: Reprocess / Retry OCR
    fail -->|"Reset Failed Pages\n(set milestone → idle)"| idle
    succ -->|"Reprocess Book\n(set all pages ocr/idle)"| idle
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

| Step | Goal |
|---|---|
| `ocr` | Extraction of text from image/PDF |
| `chunking` | Semantic splitting of text |
| `embedding` | Generation of vector embeddings |
| `word_index` | Building per-book word frequency index |
| `spell_check` | Identifying unknown words |

---

### Reprocess Book
| Field | Value |
|---|---|
| Trigger | Admin "Reprocess" button |
| Effect | All pages → `pipeline_step: ocr`, `milestone: idle`, `status: pending` |
| Logic | Preserves text until replaced page-by-page |

### Reindex
| Field | Value |
|---|---|
| Trigger | Admin "Reindex" button |
| Effect | Post-OCR pages → `pipeline_step: chunking`, `milestone: idle`, `is_indexed: false`. Chunks deleted. |

### Reset Failed Pages
| Field | Value |
|---|---|
| Trigger | Admin "Reset Failed" button |
| Effect | Pages with `milestone: failed` → `milestone: idle`, `retry_count: 0` |

### Manual Page Update
| Field | Value |
|---|---|
| Trigger | Editor saves text changes |
| Effect | **Synchronous** re-chunk and re-embed. Sets `milestone: succeeded`. |

---

## Key Infrastructure

| Component | Role |
|---|---|
| **ARQ Worker** | Runs the scanners and specific jobs (via Redis queue) |
| **Pipeline Driver** | Periodically checks book readiness and promotes state |
| **Scanners** | Periodically poll for `idle` pages and dispatch jobs |
| **Event Dispatcher** | Polles Outbox and triggers scanners immediately for low latency |
| **Stale Watchdog** | Recovers `in_progress` pages that timed out |
