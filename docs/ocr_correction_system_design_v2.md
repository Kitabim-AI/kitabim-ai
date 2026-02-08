# OCR Correction Registry Design v3 (Refined)

## 1. Business Requirement
Kitabim needs a scalable OCR correction system for Uyghur texts that:
- Reduces long-tail OCR typos across a large corpus (74 books / 36,000 pages).
- Improves search relevance and RAG retrieval quality.
- Preserves domain-specific vocabulary that a static dictionary would miss.
- Supports fast bulk correction with admin review, not manual page-by-page editing.
- Learns continuously as new books are ingested.

## 2. Design Goals
- **Corpus-first vocabulary model**: Use statistical consensus as the primary truth.
- **Agglutination-aware**: Avoid flagging valid suffixes as typos.
- **Reversible & Resumable**: All bulk updates must be checkpointed and undoable.
- **UTF-8 Consistency**: Enforce strict normalization for Uyghur characters.
- **High Performance**: Use database-level aggregation for massive scans.

## 3. Architecture & Data Model

### 3.1 Collections

#### `ocr_vocabulary`
Stores normalized token statistics. Crucially uses **NFKC** normalization.
```typescript
{
  _id: ObjectId,
  token: string,                // NFKC Normalized token (unique)
  rawVariants: [{ token: string, count: number }],
  frequency: number,            // global occurrences
  bookSpan: number,             // distinct books count
  pageSpan: number,             // distinct pages count
  lastSeenAt: Date,
  status: "verified" | "suspect" | "ignored" | "corrected",
  correctedTo?: string,         // Link to valid word if corrected
  manualOverride?: boolean,     // Admin explicitly verified/ignored
  flags: string[]               // e.g. ["suffix-like", "stem-like"]
}
```

#### `ocr_correction_jobs` (Resumable)
Tracks bulk apply operations with progress checkpoints.
```typescript
{
  _id: ObjectId,
  status: "pending" | "running" | "completed" | "failed" | "paused",
  sourceToken: string,
  targetToken: string,
  totalPages: number,
  processedPages: number,
  lastProcessedPageId: ObjectId, // Checkpoint for resumability
  affectedBookIds: string[],
  error?: string,
  createdAt: Date,
  startedAt?: Date
}
```

#### `ocr_correction_history` (Audit/Rollback)
Append-only log of every single word changed.
```typescript
{
  _id: ObjectId,
  jobId: ObjectId,
  pageId: ObjectId,
  bookId: ObjectId,
  sourceToken: string,
  targetToken: string,
  lineIndex: number,            // The specific line (0-indexed) where change occurred
  contextBefore: string,        // Snippet of the original line
  contextAfter: string,         // Snippet of the corrected line
  originalText: string,         // Full page snapshot for rollback
  appliedAt: Date
}
```

### 3.2 Correction Provenance (Traceability)
To answer "What was changed where?", the system provides three levels of visibility:
1. **The Job View**: High-level stats (e.g., "Corrected 450 instances across 12 books").
2. **The Page Inventory**: A list of all pages touched by a specific `jobId`.
3. **The Line-Level Diff**: For any page, specifically showing the index and the "Before/After" context of the modified line.


## 4. Core Algorithms

### 4.1 Unicode Normalization & Tokenization
Strict enforcement of **Unicode NFKC**. 
- **Rationale**: Uyghur characters like `ئ` (hamza) can be represented with different Unicode sequences. NFKC ensures `ئاب` is always the same byte sequence, preventing registry fragmentation.

### 4.2 Agglutination-Aware Detection
A word is only a **Suspect** if it has low frequency/spread AND is not a valid agglutination.

```python
def is_valid_agglutination(word, corpus):
    """Prevents 'كىتابىمىزدا' being flagged for 'كىتاب'"""
    # Standard Uyghur Suffix List
    UY_SUFFIXES = ['لار', 'لەر', 'نى', 'نىڭ', 'دا', 'دە', 'دىن', 'ىم', 'ىڭ', 'ى', 'ىمىز']
    for suffix in UY_SUFFIXES:
        if word.endswith(suffix):
            stem = word[:-len(suffix)]
            if corpus.is_verified_stem(stem):
                return True
    return False
```

### 4.3 High-Speed Consensus (Phase 1 Build)
To index 36,000 pages, we bypass Python loops and use a **MongoDB Aggregation Pipeline**. This moves the processing to the database layer, completing in minutes instead of hours.

```javascript
db.pages.aggregate([
  { $project: { words: { $split: ["$content", " "] } } },
  { $unwind: "$words" },
  { $group: { 
      _id: "$words", 
      frequency: { $sum: 1 }, 
      bookSpan: { $addToSet: "$bookId" } 
  } },
  { $out: "ocr_vocabulary" }
])
```

## 5. Correction & RAG Lifecycle

### 5.1 Bulk Apply Workflow (Distributed)
1. **Approval**: Admin approves a transformation rule.
2. **Job Staging**: `ocr_correction_job` created.
3. **Batch Execution**: Workers process pages in batches of 50.
4. **Checkpointing**: Update `lastProcessedPageId` after every batch.
5. **RAG Trigger**: Enqueue re-indexing for only the affected pages.

### 5.3 Provenance & Line Tracking Logic
When the worker applies a correction, it doesn't just do a global replace. It iterates through the lines:

```python
def apply_correction_with_provenance(page_text, source, target, job_id):
    lines = page_text.split('\n')
    modifications = []
    
    for idx, line in enumerate(lines):
        if source in line:
            new_line = line.replace(source, target)
            # Record the specific change
            modifications.append({
                "lineIndex": idx,
                "contextBefore": line,
                "contextAfter": new_line
            })
            lines[idx] = new_line
            
    return "\n".join(lines), modifications
```
Each entry in `modifications` is saved to `ocr_correction_history`, allowing the Admin UI to show a "Diff View" for every single correction.


### 5.2 Metadata-Driven RAG Sync
Instead of re-indexing whole books, we use Vector DB metadata filters to target only shards containing the typo.
```python
# Pseudo-code for targeted re-indexing
async def sync_rag(page_id, source_token):
    # Retrieve only the chunks for this page that actually contain the typo
    chunks = await vector_store.get_chunks(
        filter={"page_id": page_id}, 
        search_text=source_token
    )
    for chunk in chunks:
        await generate_new_embedding(chunk.id, chunk.text.replace(source_token, target))
```

## 6. Implementation Plan (Refined)

### Phase 1: High-Speed Registry (Week 1, Days 1-2)
- [ ] Run **MongoDB Aggregation** to build initial `ocr_vocabulary`.
- [ ] Implement **NFKC Normalization** in the ingestion pipeline.

### Phase 2: Candidate Engine (Week 1, Days 3-5)
- [ ] Implement **SymSpell** fuzzy matching.
- [ ] Add **Agglutination Check** (Suffix filter).
- [ ] Deploy `GET /api/registry/candidates`.

### Phase 3: Resumable Ops & Rollback (Week 2, Days 1-3)
- [ ] Build the **Correction Job Worker** with checkpointing.
- [ ] Implement **Audit History** and Rollback CLI/API.

### Phase 4: Precision-Gated Reader (Week 2, Days 4-5)
- [ ] Deploy **Metadata-aware RAG sync**.
- [ ] Enable Admin-only highlighting in `ReaderView.tsx`.
- [ ] Set **"Staging Period"**: Bulk fixes are reversible for 24h before final embedding commit.

## 7. Quality & Risk Controls
- **Staging Period**: All corrections are held in a "Staging" state for 24 hours. Admins can revert with one click if mass corruption is detected.
- **Recall Sampling**: Nightly job flags 5 random "Applied" corrections for manual human audit to track precision.
- **OOM Prevention**: Tokenization during registry build is done via database aggregation to keep memory footprint low in the API process.

---
*Document Version: 3.0 (Refined)*
*Reflecting feedback A, B, C, D.*
