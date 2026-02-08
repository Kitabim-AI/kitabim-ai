# Corpus-Based Vocabulary Registry & OCR Correction System

## 1. Overview
The Kitabim AI project processes tens of thousands of pages of historic and modern Uyghur texts via OCR. While the OCR accuracy is high, the "long tail" of character-level errors (typos) impacts search quality, RAG retrieval accuracy, and the overall professional feel of the reader.

This system establishes a **dynamic vocabulary registry** that learns from the entire corpus (currently 74 books / 36,000 pages) to identify, group, and correct OCR errors at scale.

## 2. The Problem
Traditional spell-checking (using a static dictionary file) is insufficient for this project because:
1. **Agglutination**: Uyghur has millions of valid word forms; a static file cannot cover them all.
2. **Contextual Terms**: Books contain specific historical, religious, or technical terms missing from standard dictionaries.
3. **OCR Bias**: OCR engines often have predictable "visual slips" (e.g., confusing `ۆ` and `ۇ`).
4. **Scale**: Manually checking 36,000 pages is impossible.

## 3. The Solution: "The Kitabim Registry"
Instead of a pre-defined dictionary, the system uses the library itself as the "source of truth." It operates on the principle of **Statistical Consensus**: If a word appears in multiple books by different authors, it is "Verified." If it appears once and is nearly identical to a "Verified" word, it is a "Suspect."

### Key Components:
- **Registry Engine**: Tokenizes all text into a `vocabulary` collection storing `{word, frequency, book_span}`.
- **Unicode Normalization**: Every token is passed through **NFKC normalization** to ensure consistency across different encoding styles (especially for Uyghur specific characters like `ئ`).
- **Candidate Generator**: Runs high-speed fuzzy matching using **SymSpell** or **BK-tree** data structures for sub-linear lookups.
- **Bulk Rectifier**: Allows an administrator to fix hundreds of identical typos across the entire library with a single click.
- **Incremental Learner**: Updates the registry in real-time as new books are uploaded.
- **Rollback Manager**: Maintains correction history for audit and reversion capabilities.

## 4. Architecture

### 4.1 Data Model (`vocabulary` collection)
```typescript
{
  word: string,              // Unique token (NFKC Normalized)
  frequency: number,         // Global count across all pages
  bookSpan: number,          // Number of distinct books containing this word
  status: "verified" | "suspect" | "ignored" | "corrected",
  
  // Correction tracking
  correctedTo?: string,      // Target word this was corrected to
  correctedAt?: Date,        // When the correction was applied
  correctedBy?: string,      // Admin who approved the correction
  
  // Candidate suggestions (for suspect words)
  candidates?: Array<{
    word: string,
    frequency: number,
    bookSpan: number,
    confidence: number
  }>,
  
  // Override flags
  manualOverride?: boolean,  // True if admin explicitly verified/ignored
  
  lastSeen: Date
}
```

### 4.2 Data Model (`correction_jobs` collection)
For resilient bulk operations that can resume after timeouts:
```typescript
{
  _id: ObjectId,
  status: "pending" | "running" | "completed" | "failed" | "paused",
  
  // What we're correcting
  sourceWord: string,
  targetWord: string,
  
  // Progress tracking
  totalPages: number,
  processedPages: number,
  affectedBookIds: string[],
  
  // Timing
  createdAt: Date,
  startedAt?: Date,
  completedAt?: Date,
  
  // For resumability
  lastProcessedPageId?: string,
  
  // Error handling
  errorMessage?: string,
  retryCount: number
}
```

### 4.3 Data Model (`correction_history` collection)
For audit trail and rollback:
```typescript
{
  _id: ObjectId,
  jobId: ObjectId,           // Reference to correction_jobs
  pageId: ObjectId,          // Which page was modified
  bookId: ObjectId,          // Which book
  
  sourceWord: string,
  targetWord: string,
  
  // Original content snapshot for rollback
  originalContent: string,
  modifiedContent: string,
  
  appliedAt: Date,
  appliedBy: string,
  
  // Rollback tracking
  rolledBack?: boolean,
  rolledBackAt?: Date
}
```

## 5. The Correction Workflow

### 5.1 Candidate Detection Algorithm

A word is flagged as a **suspect** only if ALL of the following conditions are met:

```python
def is_suspect(word: VocabularyEntry, corpus: VocabularyCollection) -> bool:
    # 1. Low frequency (appears rarely)
    if word.frequency > 3:
        return False
    
    # 2. Limited spread (only in one book)
    if word.bookSpan > 1:
        return False  # If it appears in multiple books, it's probably intentional
    
    # 3. Not manually verified
    if word.manualOverride:
        return False
    
    # 4. Agglutination Check: Is it just a common word with a valid suffix?
    # prevents 'كىتابىمىزدا' being flagged as typo for 'كىتاب'
    if is_valid_agglutination(word.word, corpus):
        return False
    
    # 5. Has a similar verified word
    verified_match = find_similar_verified(word, corpus, max_distance=1)
    if not verified_match:
        return False
    
    # 6. The verified match is significantly more common
    if verified_match.frequency < word.frequency * 10:
        return False
    
    # 7. The verified match appears across multiple books
    if verified_match.bookSpan < 2:
        return False
    
    return True

def is_valid_agglutination(word_str: str, corpus: VocabularyCollection) -> bool:
    """
    Checks if the word is effectively a common stem + valid Uyghur suffix.
    """
    UYGHUR_SUFFIXES = ['لار', 'لەر', 'نى', 'نىڭ', 'دا', 'دە', 'دىن', 'دىن', 'ىم', 'ىڭ', 'ى', 'ىمىز']
    # If the word starts with a common verified stem and ends with a suffix
    for suffix in UYGHUR_SUFFIXES:
        if word_str.endswith(suffix):
            stem = word_str[:-len(suffix)]
            if corpus.is_verified_stem(stem):
                return True
    return False
```

### 5.2 Collision Handling (Multiple Candidates)

When a suspect word is equidistant from multiple verified words:

The Admin UI will display ALL candidates, allowing human judgment for ambiguous cases.

### 5.3 Confidence Scoring Formula

```python
def calculate_confidence(suspect: VocabularyEntry, verified: VocabularyEntry, distance: int) -> float:
    """
    Returns a confidence score between 0 and 1.
    """
    # ... previous logic ...
    # Add bonus for NFKC equivalence or common OCR visual slips
    bonus = get_ocr_confusion_score(suspect.word, verified.word)
    return base_score + bonus
```

### 5.4 Bulk Correction Workflow

1. **AUTOMATIC DETECTION**: Nightly job scans vocabulary for suspects.
2. **ADMIN REVIEW**: Admin sees grouped proposals in Registry Manager.
3. **JOB CREATION**: System creates a `correction_job`.
4. **DISTRIBUTED EXECUTION**: Worker picks up job, processes pages in batches.
5. **RAG RE-INDEXING**: Triggered after job completes (See Section 6).

## 6. RAG Synchronization Strategy

When corrections are applied, affected RAG chunks must be re-indexed.

### 6.1 Chunk Invalidation Logic (Metadata-Driven)

Instead of re-indexing arbitrarily, we use metadata filters to precisely target affected chunks:

```python
async def invalidate_affected_chunks(page_id: str, old_content: str, new_content: str):
    """
    Determines which RAG chunks need re-embedding using Vector DB metadata.
    """
    # 1. Search Vector DB for all chunks belonging to this pageId
    # Assuming metadata includes { "page_id": "...", "book_id": "..." }
    affected_chunks = await vector_db.query_metadata(filters={"page_id": page_id})
    
    # 2. Specifically identify which chunks contain the sourceWord (the typo)
    for chunk in affected_chunks:
        if sourceWord in chunk.text:
            # 3. Regenerate embedding for this specific chunk
            await rag_service.reindex_chunk(chunk.id, new_text=fix_typo(chunk.text))
```

## 7. Performance Optimizations

### 7.1 High-Speed Consensus Aggregation (Phase 1)
Instead of iterative processing, we leverage MongoDB's aggregation engine for the initial "Full Corpus Scan":

```javascript
// Aggregation pipeline to build vocabulary in bulk
db.pages.aggregate([
  { $project: { words: { $split: ["$content", " "] } } },
  { $unwind: "$words" },
  // Apply Unicode NFKC Normalization (custom JS function or pre-process in app)
  { $group: { 
      _id: "$words", 
      frequency: { $sum: 1 }, 
      bookSpan: { $addToSet: "$bookId" } 
  } },
  { $addFields: { bookSpanCount: { $size: "$bookSpan" } } },
  { $out: "vocabulary" }
])
```

### 7.2 Fuzzy Matching: SymSpell Algorithm
- Pre-compute "delete variants" for all verified words.
- Lookup suspects in O(1) average time.

## 8. API Endpoints
... (Stats, Candidates, Bulk-Rectify, etc.)

## 11. Implementation Plan

### Phase 1: Analytics & Registry (Week 1, Days 1-3)
- [ ] Create the `vocabulary` collection with NFKC mapping.
- [ ] **Consensus Scan**: Execute MongoDB aggregation pipeline to build initial frequency indices.
- [ ] Implement `VocabularyService` with tokenization + Unicode NFKC normalization.
- [ ] Implement the `Incremental Hook` in `pdf_service.py`.

### Phase 2: Identification Engine (Week 1, Days 4-5)
- [ ] Integrate SymSpell + **Agglutination/Suffix skip logic**.
- [ ] Develop the `CandidateGenerator` with confidence scoring.

... (Phase 3 & 4)

---

*Document Version: 2.1 (Refined)*
*Last Updated: 2026-02-08*
